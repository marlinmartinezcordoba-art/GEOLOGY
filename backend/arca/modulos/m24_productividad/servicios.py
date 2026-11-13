"""M24 Productividad: configuración con el diseño de Power BI, registros diarios, tablero en tiempo real,
base de cajas del proyecto (qué está procesado y qué falta) y llaves de lectura para Power BI.

El tablero calcula exactamente lo que calculaban las fórmulas del diseño:
- Acumulado y producido en la fecha de corte: suma de la actividad que cuenta el avance del frente.
- Meta diaria: suma de las metas por turno de esa actividad.
- Días operativos restantes: días del calendario marcados como operativos, después del corte y hasta el fin.
- Ritmo requerido: lo que falta dividido entre los días restantes.
- Estado: Terminado · Por iniciar · En ritmo (ritmo ≤ meta) · Atención (hasta 15 % por encima) · En riesgo.

Lo que ARCA produce por sí misma (imágenes recibidas o aprobadas, expedientes inventariados) se cuenta
solo, en las actividades que lo indiquen en «Fuente_Automatica». Lo físico se registra a mano o se importa.
"""

import hashlib
import io
import re
import secrets
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import openpyxl
from openpyxl.styles import Font, PatternFill
from sqlalchemy import delete, func, select

from arca.modelos import (
    Actividad,
    CajaProyecto,
    ClaveReporte,
    DiaCalendario,
    EstadoRecurso,
    Frente,
    MetaTurno,
    Novedad,
    Proyecto,
    RecursoDigital,
    RegistroCalidad,
    RegistroProduccion,
    Turno,
    UnidadDocumental,
)
from arca.modelos.base import ahora_utc
from arca.modulos.m08_inventarios.fuid import clave_de
from arca.modulos.m24_productividad import diseno
from arca.modulos.m24_productividad.diseno import ENTERO, FECHA, NUMERO, SINO, TABLAS, Tabla
from arca.nucleo.errores import DatosInvalidos, NoEncontrado

MAX_FILAS = 100_000
PREFIJO_CLAVE = "arca_pbi_"


# --- Conversión de celdas ------------------------------------------------------------------------


def _convertir(valor: Any, tipo: str) -> Any:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if tipo == FECHA:
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, date):
            return valor
        texto = str(valor).strip()
        for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(texto, formato).date()
            except ValueError:
                continue
        raise ValueError(f"fecha «{texto}» no reconocida")
    if tipo == SINO:
        return str(valor).strip().lower() in ("sí", "si", "s", "true", "1", "x", "yes")
    if tipo in (NUMERO, ENTERO):
        try:
            numero = float(str(valor).replace(",", ".")) if isinstance(valor, str) else float(valor)
        except ValueError as e:
            raise ValueError(f"«{valor}» no es un número") from e
        return int(round(numero)) if tipo == ENTERO else numero
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    return str(valor).strip()


def _filas_hoja(hoja) -> tuple[list[str], list[tuple[int, list[Any]]]]:
    filas = list(hoja.iter_rows(values_only=True))
    if not filas:
        return [], []
    encabezado = [str(c).strip() if c is not None else "" for c in filas[0]]
    return encabezado, [(i + 2, list(f)) for i, f in enumerate(filas[1:]) if any(c not in (None, "") for c in f)]


def _modelo_desde_fila(tabla: Tabla, encabezado: list[str], celdas: list[Any]) -> dict[str, Any]:
    valores: dict[str, Any] = {}
    for c in tabla.columnas:
        if c.atributo is None or c.nombre not in encabezado:
            continue
        i = encabezado.index(c.nombre)
        bruto = celdas[i] if i < len(celdas) else None
        try:
            valores[c.atributo] = _convertir(bruto, c.tipo)
        except ValueError as e:
            raise ValueError(f"{c.nombre}: {e}") from e
        if c.obligatoria and valores[c.atributo] in (None, ""):
            raise ValueError(f"falta «{c.nombre}»")
    return valores


# --- Validación de referencias -------------------------------------------------------------------


class _Catalogo:
    def __init__(self, ctx, proyecto: Proyecto):
        q = lambda m, campo: set(ctx.db.scalars(select(getattr(m, campo)).where(m.proyecto_id == proyecto.id)))  # noqa: E731
        self.frentes, self.actividades, self.turnos = q(Frente, "codigo"), q(Actividad, "clave"), q(Turno, "codigo")


def _validar(tabla: str, v: dict[str, Any], cat: _Catalogo) -> None:
    if "frente" in v and tabla != "dPersonal" and cat.frentes and v["frente"] not in cat.frentes:
        raise ValueError(f"el frente «{v['frente']}» no está configurado")
    if tabla == "fProduccion":
        if v["actividad"] not in cat.actividades:
            raise ValueError(f"la actividad «{v['actividad']}» no está configurada")
        if cat.turnos and v["turno"] not in cat.turnos:
            raise ValueError(f"el turno «{v['turno']}» no está configurado")
        if v["cantidad"] < 0:
            raise ValueError("la cantidad no puede ser negativa")
    if tabla == "dMetas" and cat.actividades and v["actividad"] not in cat.actividades:
        raise ValueError(f"la actividad «{v['actividad']}» no está configurada")
    if tabla == "dActividades" and v.get("fuente_automatica") and v["fuente_automatica"] not in diseno.FUENTES_AUTOMATICAS:
        raise ValueError(f"fuente automática desconocida: {v['fuente_automatica']}")
    if tabla == "fCalidad" and v["resultado"] not in diseno.RESULTADOS_CALIDAD:
        raise ValueError(f"resultado «{v['resultado']}» no válido ({', '.join(diseno.RESULTADOS_CALIDAD)})")
    if tabla == "fNovedades" and v.get("estado") and v["estado"] not in diseno.ESTADOS_NOVEDAD:
        raise ValueError(f"estado «{v['estado']}» no válido")
    if tabla == "fEntregas" and v.get("estado") and v["estado"] not in diseno.ESTADOS_ENTREGA:
        raise ValueError(f"estado de entrega «{v['estado']}» no válido")


def _limpiar(v: dict[str, Any], tabla: Tabla) -> dict[str, Any]:
    """Los campos de texto no admiten nulos en el modelo: van vacíos."""
    textos = {c.atributo for c in tabla.columnas if c.atributo and c.tipo == diseno.TEXTO}
    return {k: ("" if (val is None and k in textos and k not in ("actividad_avance", "fuente_automatica", "unidad")) else val) for k, val in v.items()}


# --- Importar el libro con el diseño -----------------------------------------------------------


def importar_libro(ctx, proyecto: Proyecto, contenido: bytes) -> list[dict[str, Any]]:
    """Las hojas de configuración reemplazan a las anteriores; las de registro se agregan sin duplicar."""
    try:
        libro = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    except Exception as e:  # noqa: BLE001
        raise DatosInvalidos("El archivo no es un libro de Excel (.xlsx) legible") from e
    hojas = {h.title: h for h in libro.worksheets}
    reporte: list[dict[str, Any]] = []
    # Primero la configuración (para validar los registros contra ella), en el orden del diseño.
    for tabla in sorted((t for t in TABLAS if t.hoja in hojas), key=lambda t: t.es_registro):
        encabezado, filas = _filas_hoja(hojas[tabla.hoja])
        faltan = [c.nombre for c in tabla.columnas if c.obligatoria and c.nombre not in encabezado]
        if faltan:
            reporte.append({"hoja": tabla.hoja, "accion": "omitida", "filas": 0, "errores": [f"faltan columnas: {', '.join(faltan)}"]})
            continue
        if len(filas) > MAX_FILAS:
            raise DatosInvalidos(f"La hoja {tabla.hoja} supera {MAX_FILAS} filas")
        cat = _Catalogo(ctx, proyecto)
        nuevos, errores, omitidas = [], [], 0
        for numero, celdas in filas:
            texto_fila = " ".join(str(c) for c in celdas if c is not None).upper()
            if "FILA DE EJEMPLO" in texto_fila:
                omitidas += 1
                continue
            try:
                v = _modelo_desde_fila(tabla, encabezado, celdas)
                _validar(tabla.nombre, v, cat)
                nuevos.append(_limpiar(v, tabla))
            except ValueError as e:
                errores.append(f"fila {numero}: {e}")
        if tabla.es_registro:
            existentes = {_huella_registro(r) for r in ctx.db.scalars(select(tabla.modelo).where(tabla.modelo.proyecto_id == proyecto.id))}
            agregadas = 0
            for v in nuevos:
                registro = tabla.modelo(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, origen="importado", creado_en=ahora_utc(), creado_por=ctx.usuario.id, **v)
                if _huella_registro(registro) in existentes:
                    omitidas += 1
                    continue
                existentes.add(_huella_registro(registro))
                ctx.db.add(registro)
                agregadas += 1
            reporte.append({"hoja": tabla.hoja, "accion": "agregadas", "filas": agregadas, "omitidas": omitidas, "errores": errores[:50]})
        elif nuevos and not errores:
            ctx.db.execute(delete(tabla.modelo).where(tabla.modelo.proyecto_id == proyecto.id))
            for v in nuevos:
                ctx.db.add(tabla.modelo(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, **v))
            ctx.db.flush()
            reporte.append({"hoja": tabla.hoja, "accion": "reemplazada", "filas": len(nuevos), "omitidas": omitidas, "errores": []})
        else:
            reporte.append({"hoja": tabla.hoja, "accion": "sin cambios", "filas": 0, "omitidas": omitidas,
                            "errores": errores[:50] or ["la hoja no tiene filas"]})
    if not reporte:
        raise DatosInvalidos("El libro no tiene ninguna hoja del diseño (dFrentes, dActividades, Registro_Produccion…)")
    ctx.auditar(accion="IMPORTAR_PRODUCTIVIDAD", objeto="Proyecto", objeto_id=proyecto.id,
                detalle=" · ".join(f"{r['hoja']}: {r['accion']} {r['filas']}" for r in reporte))
    ctx.db.commit()
    return reporte


def _huella_registro(r: Any) -> tuple:
    tabla = next(t for t in TABLAS if t.modelo is type(r))
    return tuple(getattr(r, c.atributo) for c in tabla.columnas if c.atributo and c.atributo != "origen")


# --- Registrar desde el formulario ---------------------------------------------------------------


def registrar(ctx, proyecto: Proyecto, nombre_tabla: str, valores: dict[str, Any]) -> Any:
    tabla = diseno.POR_NOMBRE.get(nombre_tabla)
    if tabla is None or not tabla.es_registro:
        raise NoEncontrado("Tabla de registro desconocida")
    try:
        v = {c.atributo: _convertir(valores.get(c.nombre), c.tipo) for c in tabla.columnas if c.atributo and c.atributo != "origen"}
        for c in tabla.columnas:
            if c.obligatoria and v.get(c.atributo) in (None, ""):
                raise ValueError(f"falta «{c.nombre}»")
        _validar(tabla.nombre, v, _Catalogo(ctx, proyecto))
    except ValueError as e:
        raise DatosInvalidos(str(e)) from e
    registro = tabla.modelo(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, origen="formulario", creado_en=ahora_utc(), creado_por=ctx.usuario.id, **_limpiar(v, tabla))
    ctx.db.add(registro)
    ctx.db.flush()
    ctx.auditar(accion="REGISTRAR_PRODUCTIVIDAD", objeto=tabla.nombre, objeto_id=registro.id, detalle=f"{proyecto.codigo} · {diseno.fila_a_dict(tabla, registro)}")
    ctx.db.commit()
    return registro


# --- Producción automática (lo que ARCA hace sola) -----------------------------------------------


def _turno_por_hora(turnos: list[Turno], instante: datetime) -> str:
    hora = instante.time()
    for t in turnos:
        m = re.findall(r"(\d{1,2}):(\d{2})", t.horario or "")
        if len(m) != 2:
            continue
        ini, fin = time(int(m[0][0]) % 24, int(m[0][1])), time(int(m[1][0]) % 24, int(m[1][1]))
        if (ini <= hora < fin) if ini < fin else (hora >= ini or hora < fin):
            return t.codigo
    return turnos[0].codigo if turnos else ""


def _eventos_automaticos(ctx, proyecto: Proyecto, fuente: str) -> list[tuple[Any, float]]:
    """(cuándo, cuánto) de lo que hizo ARCA o se validó en ella: lo cuenta el sistema, no una persona."""
    from sqlalchemy import func  # noqa: PLC0415

    from arca.modelos import DescripcionUnidad, HojaControl, TextoPagina, TramiteHoja  # noqa: PLC0415

    pid = proyecto.id
    if fuente == "paginas_ocr":
        return [(t, 1) for t in ctx.db.scalars(select(TextoPagina.creado_en).where(TextoPagina.proyecto_id == pid, TextoPagina.estado != "error"))]
    if fuente == "descripciones_aprobadas":
        return [(t, 1) for t in ctx.db.scalars(select(DescripcionUnidad.aprobada_en).where(DescripcionUnidad.proyecto_id == pid, DescripcionUnidad.estado == "aprobada"))]
    hojas = ctx.db.execute(select(HojaControl.id, HojaControl.verificada_en, HojaControl.total_folios).where(HojaControl.proyecto_id == pid, HojaControl.estado == "verificada")).all()
    if fuente == "hojas_verificadas":
        return [(v, 1) for _, v, _ in hojas]
    if fuente == "folios_verificados":
        return [(v, f or 0) for _, v, f in hojas]
    tramites = dict(ctx.db.execute(select(TramiteHoja.hoja_id, func.count()).where(TramiteHoja.hoja_id.in_([h for h, _, _ in hojas])).group_by(TramiteHoja.hoja_id)).all()) if hojas else {}
    return [(v, tramites.get(h, 0)) for h, v, _ in hojas]


def produccion_automatica(ctx, proyecto: Proyecto) -> list[dict[str, Any]]:
    actividades = [a for a in ctx.db.scalars(select(Actividad).where(Actividad.proyecto_id == proyecto.id, Actividad.fuente_automatica.is_not(None))) if a.fuente_automatica]
    if not actividades:
        return []
    zona = ZoneInfo(ctx.organizacion.zona_horaria)
    turnos = list(ctx.db.scalars(select(Turno).where(Turno.proyecto_id == proyecto.id).order_by(Turno.codigo)))
    filas: list[dict[str, Any]] = []
    for a in actividades:
        if a.fuente_automatica == "expedientes_inventariados":
            eventos = [(u.creado_en, 1) for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id))]
        elif a.fuente_automatica in ("paginas_ocr", "hojas_verificadas", "folios_verificados", "documentos_hoja", "descripciones_aprobadas"):
            eventos = _eventos_automaticos(ctx, proyecto, a.fuente_automatica)
        else:
            consulta = select(RecursoDigital.creado_en, RecursoDigital.paginas).where(RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.unidad_id.is_not(None))
            if a.fuente_automatica == "imagenes_aprobadas":
                consulta = consulta.where(RecursoDigital.estado == EstadoRecurso.APROBADO.value)
            else:
                consulta = consulta.where(RecursoDigital.estado != EstadoRecurso.REEMPLAZADO.value)
            eventos = list(ctx.db.execute(consulta).all())
        suma: dict[tuple[date, str], float] = defaultdict(float)
        for instante, cantidad in eventos:
            if instante is None:
                continue
            local = (instante if instante.tzinfo else instante.replace(tzinfo=ZoneInfo("UTC"))).astimezone(zona)
            suma[(local.date(), _turno_por_hora(turnos, local))] += cantidad or 0
        for (dia, turno), cantidad in sorted(suma.items()):
            filas.append({"Fecha": dia.isoformat(), "Turno": turno, "Actividad": a.clave, "Lote": "", "Caja_Desde": "", "Caja_Hasta": "", "Cantidad": cantidad,
                          "Personas_Presentes": None, "Horas_Efectivas": None, "Supervisor": "", "Observaciones": "Contado por ARCA", "Origen": "automatico"})
    return filas


# --- Tablas para Power BI y para el libro ------------------------------------------------------


def filas_tabla(ctx, proyecto: Proyecto, nombre: str) -> list[dict[str, Any]]:
    if nombre == "Tablero":
        return tablero(ctx, proyecto)["frentes"]
    if nombre == "dCajas":
        return avance_cajas(ctx, proyecto)["cajas"]
    tabla = diseno.POR_NOMBRE.get(nombre)
    if tabla is None:
        raise NoEncontrado(f"Tabla «{nombre}» desconocida")
    filas = [diseno.fila_a_dict(tabla, r) for r in ctx.db.scalars(select(tabla.modelo).where(tabla.modelo.proyecto_id == proyecto.id))]
    if nombre == "fProduccion":
        filas += produccion_automatica(ctx, proyecto)
    return filas


NOMBRES_TABLAS = [t.nombre for t in TABLAS] + ["dCajas", "Tablero"]


def libro_vacio() -> bytes:
    return _libro({t.hoja: (t, []) for t in TABLAS})


def libro_lleno(ctx, proyecto: Proyecto) -> bytes:
    return _libro({t.hoja: (t, filas_tabla(ctx, proyecto, t.nombre)) for t in TABLAS})


def _libro(hojas: dict[str, tuple[Tabla, list[dict[str, Any]]]]) -> bytes:
    libro = openpyxl.Workbook()
    libro.remove(libro.active)
    titulo = Font(bold=True, color="FFFFFF")
    relleno = PatternFill("solid", fgColor="17324D")
    for nombre_hoja, (tabla, filas) in hojas.items():
        hoja = libro.create_sheet(nombre_hoja)
        hoja.append([c.nombre for c in tabla.columnas])
        for celda in hoja[1]:
            celda.font, celda.fill = titulo, relleno
        for f in filas:
            hoja.append([f.get(c.nombre) for c in tabla.columnas])
        hoja.freeze_panes = "A2"
    listas = libro.create_sheet("Listas")
    columnas = {"Resultado": diseno.RESULTADOS_CALIDAD, "Tipo_Novedad": diseno.TIPOS_NOVEDAD, "Estado_Novedad": diseno.ESTADOS_NOVEDAD,
                "Estado_Entrega": diseno.ESTADOS_ENTREGA, "Unidad": diseno.UNIDADES, "Fuente_Automatica": list(diseno.FUENTES_AUTOMATICAS)}
    listas.append(list(columnas))
    for i in range(max(len(v) for v in columnas.values())):
        listas.append([v[i] if i < len(v) else None for v in columnas.values()])
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


# --- Tablero -------------------------------------------------------------------------------------


def _sumar_produccion(ctx, proyecto: Proyecto) -> dict[tuple[str, date, str], float]:
    """(actividad, fecha, turno) → cantidad, sumando lo registrado y lo que ARCA cuenta sola."""
    suma: dict[tuple[str, date, str], float] = defaultdict(float)
    consulta = (
        select(RegistroProduccion.actividad, RegistroProduccion.fecha, RegistroProduccion.turno, func.sum(RegistroProduccion.cantidad))
        .where(RegistroProduccion.proyecto_id == proyecto.id)
        .group_by(RegistroProduccion.actividad, RegistroProduccion.fecha, RegistroProduccion.turno)
    )
    for actividad, dia, turno, cantidad in ctx.db.execute(consulta):
        suma[(actividad, dia, turno)] += cantidad or 0
    for f in produccion_automatica(ctx, proyecto):
        suma[(f["Actividad"], date.fromisoformat(f["Fecha"]), f["Turno"])] += f["Cantidad"]
    return suma


def tablero(ctx, proyecto: Proyecto, fecha_corte: date | None = None) -> dict[str, Any]:
    frentes = list(ctx.db.scalars(select(Frente).where(Frente.proyecto_id == proyecto.id).order_by(Frente.codigo)))
    metas = list(ctx.db.scalars(select(MetaTurno).where(MetaTurno.proyecto_id == proyecto.id)))
    turnos = [t.codigo for t in ctx.db.scalars(select(Turno).where(Turno.proyecto_id == proyecto.id).order_by(Turno.codigo))]
    calendario = list(ctx.db.scalars(select(DiaCalendario).where(DiaCalendario.proyecto_id == proyecto.id)))
    produccion = _sumar_produccion(ctx, proyecto)
    if fecha_corte is None:
        fechas = [d for (_, d, _) in produccion]
        fecha_corte = max(fechas) if fechas else (proyecto.fecha_inicio or date.today())
    operativos = sorted(d.fecha for d in calendario if d.operativo)

    def dias_restantes(fin: date | None) -> int:
        if fin is None:
            return 0
        if calendario:
            return sum(1 for d in operativos if fecha_corte < d <= fin)
        return max(0, (fin - fecha_corte).days)

    filas, calidad, por_turno = [], [], []
    registros_calidad = list(ctx.db.scalars(select(RegistroCalidad).where(RegistroCalidad.proyecto_id == proyecto.id)))
    novedades = list(ctx.db.scalars(select(Novedad).where(Novedad.proyecto_id == proyecto.id)))
    from arca.modelos import Entrega  # noqa: PLC0415

    entregas = list(ctx.db.scalars(select(Entrega).where(Entrega.proyecto_id == proyecto.id)))
    for f in frentes:
        act = f.actividad_avance
        acumulado = sum(c for (a, d, _), c in produccion.items() if a == act and d <= fecha_corte)
        producido = sum(c for (a, d, _), c in produccion.items() if a == act and d == fecha_corte)
        meta = sum(m.meta_turno for m in metas if m.actividad == act)
        restantes = dias_restantes(f.fecha_fin)
        falta = max(0.0, (f.volumen_total or 0) - acumulado)
        ritmo = falta / restantes if restantes else falta
        if acumulado >= (f.volumen_total or 0) and f.volumen_total:
            estado = "Terminado"
        elif f.fecha_inicio and fecha_corte < f.fecha_inicio:
            estado = "Por iniciar"
        elif ritmo <= meta:
            estado = "En ritmo"
        elif ritmo <= meta * 1.15:
            estado = "Atención"
        else:
            estado = "En riesgo"
        filas.append({
            "Fecha_Corte": fecha_corte.isoformat(), "Frente": f.codigo, "Nombre": f.nombre, "Sede": f.sede, "Unidad": f.unidad,
            "Volumen_Total": f.volumen_total, "Acumulado": acumulado, "Pct_Avance": (acumulado / f.volumen_total) if f.volumen_total else 0,
            "Meta_Diaria": meta, "Producido_Fecha_Corte": producido, "Pct_Cumplimiento_Dia": (producido / meta) if meta else 0,
            "Dias_Operativos_Restantes": restantes, "Ritmo_Requerido_Dia": ritmo, "Estado": estado,
        })
        rc = [r for r in registros_calidad if r.frente == f.codigo]
        rechazados = sum(1 for r in rc if r.resultado == "Rechazado")
        aceptado = sum(e.cantidad for e in entregas if e.frente == f.codigo and e.estado == "Aceptado")
        calidad.append({
            "Frente": f.codigo, "Lotes_Inspeccionados": len(rc), "Lotes_Rechazados": rechazados, "Pct_Rechazo": (rechazados / len(rc)) if rc else 0,
            "Defectos_Criticos": sum(r.criticos for r in rc), "Novedades_Abiertas": sum(1 for n in novedades if n.frente == f.codigo and n.estado == "Abierta"),
            "Novedades_Totales": sum(1 for n in novedades if n.frente == f.codigo), "Cantidad_Aceptada": aceptado,
            "Pct_Volumen_Aceptado": (aceptado / f.volumen_total) if f.volumen_total else 0,
        })
        por_turno.append({"Frente": f.codigo, "turnos": [
            {"Turno": t, "Producido": sum(c for (a, d, tt), c in produccion.items() if a == act and d == fecha_corte and tt == t),
             "Meta": sum(m.meta_turno for m in metas if m.actividad == act and m.turno == t)} for t in turnos]})
    return {"fecha_corte": fecha_corte.isoformat(), "frentes": filas, "calidad": calidad, "por_turno": por_turno, "turnos": turnos,
            "calculado_en": ahora_utc().isoformat()}


# --- Base de cajas: qué está procesado y qué falta ----------------------------------------------


def _numero_y_prefijo(clave: str) -> tuple[str, int | None]:
    m = re.match(r"^(.*?)(\d+)$", clave or "")
    return (m.group(1), int(m.group(2))) if m else (clave, None)


def importar_cajas(ctx, proyecto: Proyecto, contenido: bytes, nombre: str) -> dict[str, Any]:
    """Listado de cajas en Excel o CSV. Columnas: Caja (obligatoria), Carpetas, Cod_Frente, Lote, Sede, Ubicacion, Notas."""
    from arca.modulos.m08_inventarios.fuid import _filas_csv, plano  # noqa: PLC0415

    if nombre.lower().endswith((".csv", ".txt")):
        filas = _filas_csv(contenido)
    else:
        try:
            libro = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
        except Exception as e:  # noqa: BLE001
            raise DatosInvalidos("El archivo no es un Excel (.xlsx) o CSV legible") from e
        filas = [list(f) for f in libro.worksheets[0].iter_rows(values_only=True)]
    encabezado_i = next((i for i, f in enumerate(filas[:30]) if any(plano(c) in ("caja", "no caja", "numero de caja", "cod caja", "codigo caja") for c in f)), None)
    if encabezado_i is None:
        raise DatosInvalidos("No se encontró la columna «Caja» en el listado")
    encabezado = [plano(c) for c in filas[encabezado_i]]

    def col(*nombres: str) -> int | None:
        return next((i for i, h in enumerate(encabezado) if h in nombres), None)

    i_caja = col("caja", "no caja", "numero de caja", "cod caja", "codigo caja")
    i_carpetas, i_frente, i_lote = col("carpetas", "no carpetas", "numero de carpetas", "cantidad de carpetas"), col("cod frente", "frente"), col("lote")
    i_sede, i_ubicacion, i_notas = col("sede"), col("ubicacion", "ubicacion fisica"), col("notas", "observaciones")
    frentes = {f for f in ctx.db.scalars(select(Frente.codigo).where(Frente.proyecto_id == proyecto.id))}
    existentes = {c.clave: c for c in ctx.db.scalars(select(CajaProyecto).where(CajaProyecto.proyecto_id == proyecto.id))}
    nuevas = actualizadas = 0
    errores: list[str] = []
    for n, fila in enumerate(filas[encabezado_i + 1 :], start=encabezado_i + 2):
        valor = lambda i: (str(fila[i]).strip() if i is not None and i < len(fila) and fila[i] is not None else "")  # noqa: E731,B023
        codigo = valor(i_caja)
        if not codigo:
            continue
        if isinstance(fila[i_caja], float) and fila[i_caja].is_integer():
            codigo = str(int(fila[i_caja]))
        frente = valor(i_frente) or None
        if frente and frentes and frente not in frentes:
            errores.append(f"fila {n}: el frente «{frente}» no está configurado")
            continue
        carpetas_txt = valor(i_carpetas)
        try:
            carpetas = int(float(carpetas_txt)) if carpetas_txt else None
        except ValueError:
            errores.append(f"fila {n}: carpetas «{carpetas_txt}» no es un número")
            continue
        clave = clave_de(codigo)
        datos = {"codigo": codigo, "frente": frente, "lote": valor(i_lote), "sede": valor(i_sede), "ubicacion": valor(i_ubicacion), "carpetas": carpetas, "notas": valor(i_notas)}
        if clave in existentes:
            for k, v in datos.items():
                setattr(existentes[clave], k, v)
            actualizadas += 1
        else:
            caja = CajaProyecto(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, clave=clave, origen="listado", creado_en=ahora_utc(), creado_por=ctx.usuario.id, **datos)
            ctx.db.add(caja)
            existentes[clave] = caja
            nuevas += 1
    ctx.auditar(accion="IMPORTAR_CAJAS", objeto="Proyecto", objeto_id=proyecto.id, detalle=f"{nombre} · {nuevas} nuevas, {actualizadas} actualizadas, {len(errores)} con error")
    ctx.db.commit()
    return {"nuevas": nuevas, "actualizadas": actualizadas, "errores": errores[:100]}


def cajas_desde_fuid(ctx, proyecto: Proyecto, frente: str | None) -> dict[str, Any]:
    """Arma la base de cajas desde el FUID integrado: una caja por cada valor de «Caja», con sus carpetas contadas."""
    if frente and not ctx.db.scalar(select(Frente.id).where(Frente.proyecto_id == proyecto.id, Frente.codigo == frente)):
        raise DatosInvalidos(f"El frente «{frente}» no está configurado")
    conteo = dict(ctx.db.execute(
        select(UnidadDocumental.caja, func.count()).where(UnidadDocumental.proyecto_id == proyecto.id, UnidadDocumental.caja.is_not(None), UnidadDocumental.caja != "")
        .group_by(UnidadDocumental.caja)
    ).all())
    if not conteo:
        raise DatosInvalidos("El FUID integrado no trae la columna «Caja» diligenciada")
    existentes = {c.clave: c for c in ctx.db.scalars(select(CajaProyecto).where(CajaProyecto.proyecto_id == proyecto.id))}
    nuevas = actualizadas = 0
    for codigo, carpetas in conteo.items():
        clave = clave_de(codigo)
        if clave in existentes:
            existentes[clave].carpetas = carpetas
            actualizadas += 1
        else:
            ctx.db.add(CajaProyecto(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, codigo=codigo, clave=clave, frente=frente, carpetas=carpetas,
                                    origen="fuid", creado_en=ahora_utc(), creado_por=ctx.usuario.id))
            nuevas += 1
    ctx.auditar(accion="CAJAS_DESDE_FUID", objeto="Proyecto", objeto_id=proyecto.id, detalle=f"{nuevas} nuevas, {actualizadas} actualizadas")
    ctx.db.commit()
    return {"nuevas": nuevas, "actualizadas": actualizadas, "errores": []}


def _cobertura(ctx, proyecto: Proyecto, claves_cajas: list[str]) -> dict[str, dict[str, date]]:
    """caja → {actividad: primera fecha en que se registró}, a partir de los rangos Caja_Desde / Caja_Hasta."""
    por_prefijo: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for clave in claves_cajas:
        prefijo, numero = _numero_y_prefijo(clave)
        if numero is not None:
            por_prefijo[prefijo].append((numero, clave))
    hechas: dict[str, dict[str, date]] = defaultdict(dict)
    for r in ctx.db.scalars(select(RegistroProduccion).where(RegistroProduccion.proyecto_id == proyecto.id, RegistroProduccion.caja_desde != "")):
        desde, hasta = clave_de(r.caja_desde), clave_de(r.caja_hasta or r.caja_desde)
        (p1, n1), (p2, n2) = _numero_y_prefijo(desde), _numero_y_prefijo(hasta)
        if n1 is None or n2 is None or p1 != p2:
            cubiertas = [c for c in (desde, hasta) if c in claves_cajas]
        else:
            bajo, alto = min(n1, n2), max(n1, n2)
            cubiertas = [c for n, c in por_prefijo.get(p1, []) if bajo <= n <= alto]
        for c in cubiertas:
            anterior = hechas[c].get(r.actividad)
            hechas[c][r.actividad] = min(anterior, r.fecha) if anterior else r.fecha
    return hechas


def avance_cajas(ctx, proyecto: Proyecto, frente: str | None = None, estado: str | None = None, texto: str | None = None) -> dict[str, Any]:
    cajas = sorted(ctx.db.scalars(select(CajaProyecto).where(CajaProyecto.proyecto_id == proyecto.id)), key=lambda c: (_numero_y_prefijo(c.clave)[0], _numero_y_prefijo(c.clave)[1] or 0, c.clave))
    frentes = {f.codigo: f for f in ctx.db.scalars(select(Frente).where(Frente.proyecto_id == proyecto.id))}
    actividades = list(ctx.db.scalars(select(Actividad).where(Actividad.proyecto_id == proyecto.id).order_by(Actividad.frente, Actividad.orden)))
    hechas = _cobertura(ctx, proyecto, [c.clave for c in cajas])
    avance_global = {f.actividad_avance for f in frentes.values() if f.actividad_avance}
    filas, resumen = [], defaultdict(lambda: {"total": 0, "procesada": 0, "en_proceso": 0, "pendiente": 0, "carpetas": 0, "carpetas_procesadas": 0})
    for c in cajas:
        hechas_caja = hechas.get(c.clave, {})
        del_frente = [a.clave for a in actividades if c.frente is None or a.frente == c.frente]
        avance = {frentes[c.frente].actividad_avance} if c.frente in frentes and frentes[c.frente].actividad_avance else avance_global
        if avance and avance & set(hechas_caja):
            situacion = "procesada"
        elif set(hechas_caja) & set(del_frente):
            situacion = "en_proceso"
        else:
            situacion = "pendiente"
        r = resumen[c.frente or "Sin frente"]
        r["total"] += 1
        r[situacion] += 1
        r["carpetas"] += c.carpetas or 0
        r["carpetas_procesadas"] += (c.carpetas or 0) if situacion == "procesada" else 0
        fila = {"Caja": c.codigo, "Cod_Frente": c.frente, "Lote": c.lote, "Sede": c.sede, "Ubicacion": c.ubicacion, "Carpetas": c.carpetas, "Origen": c.origen,
                "Estado": situacion, "Actividades_Hechas": sorted(hechas_caja), "Ultima_Fecha": max(hechas_caja.values()).isoformat() if hechas_caja else None,
                "Actividades_Pendientes": [a for a in del_frente if a not in hechas_caja]}
        if (frente is None or c.frente == frente) and (estado is None or situacion == estado) and (not texto or clave_de(texto) in c.clave):
            filas.append(fila)
    return {"cajas": filas, "resumen": [{"Cod_Frente": k, **v} for k, v in sorted(resumen.items())]}


# --- Llaves de lectura para Power BI ------------------------------------------------------------


def _huella(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_clave(ctx, proyecto: Proyecto, nombre: str) -> tuple[ClaveReporte, str]:
    token = PREFIJO_CLAVE + secrets.token_urlsafe(32)
    clave = ClaveReporte(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, nombre=nombre.strip(), prefijo=token[:14], huella=_huella(token),
                         creado_en=ahora_utc(), creado_por=ctx.usuario.id)
    ctx.db.add(clave)
    ctx.db.flush()
    ctx.auditar(accion="CREAR_LLAVE_REPORTE", objeto="ClaveReporte", objeto_id=clave.id, detalle=f"{proyecto.codigo} · {clave.nombre} · {clave.prefijo}…")
    ctx.db.commit()
    return clave, token


def revocar_clave(ctx, proyecto: Proyecto, clave_id: uuid.UUID, motivo: str) -> ClaveReporte:
    clave = ctx.db.get(ClaveReporte, clave_id)
    if clave is None or clave.proyecto_id != proyecto.id:
        raise NoEncontrado("La llave no existe")
    clave.activa = False
    ctx.auditar(accion="REVOCAR_LLAVE_REPORTE", objeto="ClaveReporte", objeto_id=clave.id, motivo=motivo, detalle=clave.prefijo)
    ctx.db.commit()
    return clave


def autenticar_clave(db, token: str) -> ClaveReporte | None:
    if not token.startswith(PREFIJO_CLAVE):
        return None
    clave = db.scalar(select(ClaveReporte).where(ClaveReporte.huella == _huella(token), ClaveReporte.activa.is_(True)))
    if clave is not None and (clave.ultimo_uso is None or ahora_utc() - _utc(clave.ultimo_uso) > timedelta(minutes=5)):
        clave.ultimo_uso = ahora_utc()
        db.commit()
    return clave


def _utc(fecha: datetime) -> datetime:
    from arca.modelos.base import en_utc  # noqa: PLC0415

    return en_utc(fecha)
