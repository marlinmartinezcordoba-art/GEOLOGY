"""Disposición final: eliminación, selección y digitalización (Acuerdo 004 de 2019 del AGN; D-33).

Principio (heredado del motor de disposición de GEOLOGY): eliminar es irreversible. ARCA propone y documenta;
no decide. Ninguna unidad se elimina sin inventario, aprobación del Comité registrada por una persona distinta de
quien preparó el proceso, publicación del inventario por el plazo fijado y ejecución con acta.

Qué entra en cada proceso: lo clasificado y confirmado, con la retención cumplida a la fecha de corte (gestión +
central), en archivo de gestión o central, sin disposición ya aplicada y libre (no va en otra transferencia ni en
otro proceso). La disposición de la TRD/TVD manda: E → eliminación, S → selección, D → digitalización.

- **Eliminación:** borrador → aprobado (acta del comité) → publicado (inicio, plazo, enlace) → ejecutado (acta,
  método). Durante la publicación se pueden retirar unidades por observaciones, con motivo.
- **Selección:** borrador → muestreo (porcentaje y semilla: reproducible; una persona ajusta) → aprobado →
  ejecutado. Lo seleccionado queda listo para la transferencia secundaria; lo no seleccionado pasa a un proceso
  de eliminación nuevo, en borrador.
- **Digitalización:** solo se aprueba si cada unidad tiene su digitalización aprobada en ARCA. Al ejecutar se
  decide qué pasa con el físico: se conserva o pasa a un proceso de eliminación nuevo.
"""

import random
import re
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select

from arca.modelos import (
    ClasificacionUnidad,
    ElementoDisposicion,
    ElementoInstrumento,
    ElementoTransferencia,
    EstadoProyecto,
    EstadoRecurso,
    MovimientoFase,
    ProcesoDisposicion,
    Proyecto,
    RecursoDigital,
    Transferencia,
    UnidadDocumental,
)
from arca.modelos.base import ahora_utc
from arca.modelos.disposicion import TIPOS_DISPOSICION
from arca.modulos.entregables import servicios as entregables
from arca.modulos.m04_instrumentos.clasificacion import calendario
from arca.nucleo.errores import AccesoDenegado, DatosInvalidos, NoEncontrado, TransicionInvalida

ABIERTOS = ("borrador", "aprobado", "publicado")
NOMBRE = {"eliminacion": "Eliminación documental", "seleccion": "Selección documental", "digitalizacion": "Digitalización (medio técnico)"}
ACTIVOS = ("incluida", "seleccionada", "no_seleccionada")


def _natural(texto: str | None) -> list:
    """«C-2» antes que «C-10», como se archivan las cajas y las carpetas."""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.split(r"(\d+)", texto or "") if t]


def _abierto(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


def _tipo(tipo: str) -> str:
    if tipo not in TIPOS_DISPOSICION:
        raise DatosInvalidos("Tipo desconocido: use eliminacion, seleccion o digitalizacion")
    return TIPOS_DISPOSICION[tipo]


def ocupadas(ctx, proyecto: Proyecto) -> dict[uuid.UUID, str]:
    """Unidades que van en un proceso de disposición abierto o en una transferencia abierta, con dónde van."""
    salida = {uid: f"proceso de disposición n.º {n}" for uid, n in ctx.db.execute(
        select(ElementoDisposicion.unidad_id, ProcesoDisposicion.numero).join(ProcesoDisposicion, ElementoDisposicion.proceso_id == ProcesoDisposicion.id)
        .where(ProcesoDisposicion.proyecto_id == proyecto.id, ProcesoDisposicion.estado.in_(ABIERTOS), ElementoDisposicion.estado.in_(ACTIVOS)))}
    for uid, n in ctx.db.execute(
        select(ElementoTransferencia.unidad_id, Transferencia.numero).join(Transferencia, ElementoTransferencia.transferencia_id == Transferencia.id)
        .where(Transferencia.proyecto_id == proyecto.id, Transferencia.estado.in_(("borrador", "enviada", "devuelta")), ElementoTransferencia.estado != "devuelta")):
        salida.setdefault(uid, f"transferencia n.º {n}")
    return salida


def _datos(ctx, proyecto: Proyecto) -> dict[str, Any]:
    unidades = {u.id: u for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id))}
    clasif = {c.unidad_id: c for c in ctx.db.scalars(select(ClasificacionUnidad).where(ClasificacionUnidad.proyecto_id == proyecto.id, ClasificacionUnidad.estado == "confirmada"))}
    elementos = {e.id: e for e in ctx.db.scalars(select(ElementoInstrumento).where(ElementoInstrumento.id.in_({c.elemento_id for c in clasif.values()})))} if clasif else {}
    return {"unidades": unidades, "clasif": clasif, "elementos": elementos, "ocupadas": ocupadas(ctx, proyecto)}


def _evaluar(d: dict[str, Any], u: UnidadDocumental, tipo: str, corte: date) -> dict[str, Any]:
    r: dict[str, Any] = {"puede": False, "aviso": "", "clasificacion": None, "elemento": None}
    if u.fase not in ("gestion", "central"):
        r["aviso"] = "ya está en el archivo histórico o fue eliminada"
        return r
    if u.disposicion_aplicada:
        r["aviso"] = f"ya tiene disposición aplicada ({u.disposicion_aplicada})"
        return r
    c = d["clasif"].get(u.id)
    if c is None:
        r["aviso"] = "no está clasificada (o la clasificación no está confirmada)"
        return r
    e = d["elementos"][c.elemento_id]
    r["clasificacion"], r["elemento"] = c, e
    if e.disposicion != TIPOS_DISPOSICION[tipo]:
        r["aviso"] = f"su disposición en la tabla es {e.disposicion or 'desconocida'}, no {TIPOS_DISPOSICION[tipo]}"
        return r
    if u.id in d["ocupadas"]:
        r["aviso"] = f"ya va en la {d['ocupadas'][u.id]}"
        return r
    cal = calendario(u, e, corte)
    fin = cal["fin_central"]
    if fin is None and e.retencion_gestion is None and u.fecha_final:  # TVD sin tiempos: la disposición se aplica desde que se valoró
        fin = u.fecha_final
    if fin is None:
        r["aviso"] = "sin fecha final o sin tiempos de retención: no se puede saber si cumplió"
        return r
    if fin > corte:
        r["aviso"] = f"su retención termina el {fin.isoformat()}"
        return r
    r["puede"] = True
    return r


def plan(ctx, proyecto: Proyecto, corte: date) -> dict[str, Any]:
    d = _datos(ctx, proyecto)
    salida: dict[str, Any] = {"fecha_corte": corte, "tipos": {}}
    for tipo, letra in TIPOS_DISPOSICION.items():
        g = {"elegibles": 0, "folios": 0, "por_cumplir": 0, "sin_calendario": 0, "por_serie": {}}
        for u in d["unidades"].values():
            ev = _evaluar(d, u, tipo, corte)
            if ev["puede"]:
                g["elegibles"] += 1
                g["folios"] += u.folios or 0
                e = ev["elemento"]
                s = g["por_serie"].setdefault(e.codigo, {"codigo": e.codigo, "nombre": e.nombre, "unidades": 0, "procedimiento": e.procedimiento})
                s["unidades"] += 1
            elif ev["elemento"] is not None and ev["elemento"].disposicion == letra and not u.disposicion_aplicada and u.id not in d["ocupadas"]:
                g["sin_calendario" if "sin fecha" in ev["aviso"] else "por_cumplir"] += 1
        g["por_serie"] = sorted(g["por_serie"].values(), key=lambda x: x["codigo"])
        salida["tipos"][tipo] = g
    fases = dict(ctx.db.execute(select(UnidadDocumental.fase, func.count()).where(UnidadDocumental.proyecto_id == proyecto.id).group_by(UnidadDocumental.fase)).all())
    salida["eliminadas"] = fases.get("eliminada", 0)
    salida["seleccionadas"] = sum(1 for u in d["unidades"].values() if u.disposicion_aplicada == "seleccionada")
    salida["digitalizadas"] = sum(1 for u in d["unidades"].values() if u.disposicion_aplicada == "digitalizada")
    return salida


def listar(ctx, proyecto: Proyecto) -> list[ProcesoDisposicion]:
    return list(ctx.db.scalars(select(ProcesoDisposicion).where(ProcesoDisposicion.proyecto_id == proyecto.id).order_by(ProcesoDisposicion.numero.desc())))


def obtener(ctx, proyecto: Proyecto, proceso_id: uuid.UUID) -> ProcesoDisposicion:
    p = ctx.db.get(ProcesoDisposicion, proceso_id)
    if p is None or p.proyecto_id != proyecto.id:
        raise NoEncontrado("El proceso de disposición no existe")
    return p


def elementos(ctx, p: ProcesoDisposicion) -> list[tuple[ElementoDisposicion, UnidadDocumental]]:
    filas = ctx.db.execute(select(ElementoDisposicion, UnidadDocumental).join(UnidadDocumental, ElementoDisposicion.unidad_id == UnidadDocumental.id)
                           .where(ElementoDisposicion.proceso_id == p.id)).all()
    return sorted(((e, u) for e, u in filas), key=lambda x: (_natural(x[1].caja), _natural(x[1].carpeta), _natural(x[1].identificador)))


def _nuevo(ctx, proyecto: Proyecto, tipo: str, corte: date, observaciones: str, origen: ProcesoDisposicion | None = None) -> ProcesoDisposicion:
    numero = (ctx.db.scalar(select(func.max(ProcesoDisposicion.numero)).where(ProcesoDisposicion.proyecto_id == proyecto.id)) or 0) + 1
    p = ProcesoDisposicion(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, numero=numero, tipo=tipo, estado="borrador", fecha_corte=corte, observaciones=observaciones.strip(),
                           origen_id=origen.id if origen else None, creado_en=ahora_utc(), creado_por=ctx.usuario.id)
    ctx.db.add(p)
    ctx.db.flush()
    return p


def crear(ctx, proyecto: Proyecto, tipo: str, corte: date, serie: str, observaciones: str) -> ProcesoDisposicion:
    """Crea el borrador con todo lo que cumple, de una serie o subserie o de todas."""
    _abierto(proyecto)
    _tipo(tipo)
    d = _datos(ctx, proyecto)
    p = _nuevo(ctx, proyecto, tipo, corte, observaciones)
    n = 0
    for u in d["unidades"].values():
        ev = _evaluar(d, u, tipo, corte)
        if ev["puede"] and (not serie or ev["elemento"].codigo == serie):
            ctx.db.add(ElementoDisposicion(tenant_id=ctx.tenant_id, proceso_id=p.id, unidad_id=u.id, clasificacion_id=ev["clasificacion"].id))
            n += 1
    if not n:
        raise DatosInvalidos("No hay unidades que cumplan para este proceso a esa fecha de corte")
    ctx.auditar(accion="CREAR_DISPOSICION", objeto="ProcesoDisposicion", objeto_id=p.id,
                detalle=f"{proyecto.codigo} · {NOMBRE[tipo]} n.º {p.numero} · corte {corte.isoformat()} · {n} unidades{' · serie ' + serie if serie else ''}")
    ctx.db.commit()
    return p


def retirar(ctx, proyecto: Proyecto, p: ProcesoDisposicion, unidad_ids: list[uuid.UUID], motivo: str) -> int:
    """Saca unidades del proceso (por ejemplo, por una observación recibida durante la publicación). Queda la constancia."""
    _abierto(proyecto)
    if p.estado not in ("borrador", "publicado"):
        raise TransicionInvalida("Solo se retiran unidades en borrador o durante la publicación")
    if len(motivo.strip()) < 5:
        raise DatosInvalidos("Escriba el motivo del retiro")
    filas = [e for e, u in elementos(ctx, p) if u.id in set(unidad_ids) and e.estado in ACTIVOS]
    for e in filas:
        e.estado, e.observacion = "retirada", motivo.strip()
    if filas and not any(e.estado in ACTIVOS for e, _ in elementos(ctx, p)):
        raise TransicionInvalida("No puede retirar todas las unidades: anule el proceso")
    ctx.auditar(accion="RETIRAR_DE_DISPOSICION", objeto="ProcesoDisposicion", objeto_id=p.id, motivo=motivo, detalle=f"n.º {p.numero} · {len(filas)} unidades")
    ctx.db.commit()
    return len(filas)


def muestrear(ctx, proyecto: Proyecto, p: ProcesoDisposicion, porcentaje: float, semilla: int | None, criterio: str) -> dict[str, Any]:
    """Propone la muestra: aleatoria con semilla registrada (la misma semilla da la misma muestra). Una persona la ajusta."""
    _abierto(proyecto)
    if p.tipo != "seleccion" or p.estado != "borrador":
        raise TransicionInvalida("El muestreo se hace en un proceso de selección en borrador")
    if not 0 < porcentaje <= 100:
        raise DatosInvalidos("El porcentaje va de 0 a 100")
    filas = [e for e, _ in elementos(ctx, p) if e.estado in ACTIVOS]
    semilla = semilla if semilla is not None else random.SystemRandom().randint(1, 999_999)
    cuantas = max(1, round(len(filas) * porcentaje / 100))
    elegidas = set(random.Random(semilla).sample(range(len(filas)), cuantas))
    for i, e in enumerate(filas):
        e.estado = "seleccionada" if i in elegidas else "no_seleccionada"
    p.muestreo = {"metodo": "aleatorio con semilla", "porcentaje": porcentaje, "semilla": semilla, "criterio": criterio.strip(), "propuestas": cuantas, "universo": len(filas)}
    ctx.auditar(accion="MUESTREAR", objeto="ProcesoDisposicion", objeto_id=p.id, detalle=f"n.º {p.numero} · {cuantas} de {len(filas)} ({porcentaje} %) · semilla {semilla}")
    ctx.db.commit()
    return p.muestreo


def marcar(ctx, proyecto: Proyecto, p: ProcesoDisposicion, unidad_ids: list[uuid.UUID], seleccionada: bool) -> int:
    """Ajuste de la muestra por criterio cualitativo: la persona agrega o quita unidades de la selección."""
    _abierto(proyecto)
    if p.tipo != "seleccion" or p.estado != "borrador":
        raise TransicionInvalida("La muestra se ajusta en un proceso de selección en borrador")
    n = 0
    for e, u in elementos(ctx, p):
        if u.id in set(unidad_ids) and e.estado in ACTIVOS:
            e.estado = "seleccionada" if seleccionada else "no_seleccionada"
            n += 1
    p.muestreo = {**(p.muestreo or {}), "ajustada": True}
    ctx.db.commit()
    return n


def _digitalizacion_completa(ctx, unidad_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Faltantes por unidad: sin imágenes, con recaptura o con imágenes por revisar."""
    estados: dict[uuid.UUID, set[str]] = {}
    for uid, estado in ctx.db.execute(select(RecursoDigital.unidad_id, RecursoDigital.estado).where(RecursoDigital.unidad_id.in_(unidad_ids))):
        if estado != EstadoRecurso.REEMPLAZADO.value:
            estados.setdefault(uid, set()).add(estado)
    faltan = {}
    for uid in unidad_ids:
        e = estados.get(uid)
        if not e:
            faltan[uid] = "no tiene imágenes digitalizadas"
        elif e != {EstadoRecurso.APROBADO.value}:
            faltan[uid] = "su digitalización no está aprobada (hay imágenes por revisar o en recaptura)"
    return faltan


def avisos(ctx, p: ProcesoDisposicion) -> dict[uuid.UUID, str]:
    if p.tipo != "digitalizacion":
        return {}
    return _digitalizacion_completa(ctx, {u.id for e, u in elementos(ctx, p) if e.estado in ACTIVOS})


def aprobar(ctx, proyecto: Proyecto, p: ProcesoDisposicion, acta: str, fecha_acta: date, motivo: str) -> ProcesoDisposicion:
    """Registra la aprobación del Comité. La registra alguien distinto de quien preparó el proceso."""
    _abierto(proyecto)
    if p.estado != "borrador":
        raise TransicionInvalida("Solo se aprueba un proceso en borrador")
    if p.creado_por == ctx.usuario.id:
        raise AccesoDenegado("Quien preparó el proceso no registra su aprobación (segregación de funciones)")
    if fecha_acta > date.today():
        raise DatosInvalidos("La fecha del acta del comité no puede ser futura")
    activos = [e for e, _ in elementos(ctx, p) if e.estado in ACTIVOS]
    if not activos:
        raise TransicionInvalida("El proceso no tiene unidades")
    if p.tipo == "seleccion" and not any(e.estado == "seleccionada" for e in activos):
        raise TransicionInvalida("Haga el muestreo antes de aprobar: no hay unidades seleccionadas")
    if p.tipo == "seleccion" and any(e.estado == "incluida" for e in activos):
        raise TransicionInvalida("Hay unidades sin decidir en la muestra")
    if faltan := avisos(ctx, p):
        raise TransicionInvalida(f"{len(faltan)} unidades no tienen la digitalización completa: retírelas o termine de digitalizarlas")
    p.estado, p.comite_acta, p.comite_fecha, p.aprobado_en, p.aprobado_por = "aprobado", acta.strip(), fecha_acta, ahora_utc(), ctx.usuario.id
    ctx.auditar(accion="APROBAR_DISPOSICION", objeto="ProcesoDisposicion", objeto_id=p.id, motivo=motivo,
                detalle=f"{NOMBRE[p.tipo]} n.º {p.numero} · {acta} del {fecha_acta.isoformat()} · {len(activos)} unidades")
    ctx.db.commit()
    return p


def publicar(ctx, proyecto: Proyecto, p: ProcesoDisposicion, inicio: date, dias: int, enlace: str) -> ProcesoDisposicion:
    """La publicación del inventario de eliminación: desde cuándo, por cuántos días y dónde. El plazo lo fija la entidad según la norma vigente."""
    _abierto(proyecto)
    if p.tipo != "eliminacion" or p.estado != "aprobado":
        raise TransicionInvalida("Se publica un proceso de eliminación aprobado")
    if dias < 1:
        raise DatosInvalidos("El plazo de publicación debe ser de al menos un día")
    if inicio > date.today():
        raise DatosInvalidos("Registre la publicación cuando ya esté publicada (la fecha de inicio no puede ser futura)")
    p.estado, p.publicacion_inicio, p.publicacion_dias, p.publicacion_enlace = "publicado", inicio, dias, enlace.strip()
    ctx.auditar(accion="PUBLICAR_ELIMINACION", objeto="ProcesoDisposicion", objeto_id=p.id,
                detalle=f"n.º {p.numero} · desde {inicio.isoformat()} por {dias} días · {enlace.strip()}")
    ctx.db.commit()
    return p


def fin_publicacion(p: ProcesoDisposicion) -> date | None:
    return p.publicacion_inicio + timedelta(days=p.publicacion_dias) if p.publicacion_inicio and p.publicacion_dias else None


def _mover(ctx, proyecto, u: UnidadDocumental, hasta: str, motivo: str) -> None:
    ctx.db.add(MovimientoFase(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, unidad_id=u.id, desde=u.fase, hasta=hasta, motivo=motivo, creado_en=ahora_utc(), creado_por=ctx.usuario.id))
    u.fase = hasta


def ejecutar(ctx, proyecto: Proyecto, p: ProcesoDisposicion, acta_numero: str, metodo: str, destino_fisico: str | None) -> dict[str, Any]:
    _abierto(proyecto)
    filas = [(e, u) for e, u in elementos(ctx, p) if e.estado in ACTIVOS]
    if p.tipo == "eliminacion":
        if p.estado != "publicado":
            raise TransicionInvalida("La eliminación se ejecuta después de aprobada y publicada")
        fin = fin_publicacion(p)
        if fin and date.today() < fin:
            raise TransicionInvalida(f"El inventario está publicado hasta el {fin.isoformat()}: todavía pueden llegar observaciones")
        if len(acta_numero.strip()) < 1 or len(metodo.strip()) < 3:
            raise DatosInvalidos("Registre el número del acta de eliminación y el método")
    elif p.estado != "aprobado":
        raise TransicionInvalida("El proceso se ejecuta después de aprobado")
    if p.tipo == "digitalizacion" and destino_fisico not in ("conservar", "eliminar"):
        raise DatosInvalidos("Diga qué pasa con el físico después de digitalizar: conservar o eliminar")
    if p.tipo == "digitalizacion" and (faltan := _digitalizacion_completa(ctx, {u.id for _, u in filas})):
        raise TransicionInvalida(f"{len(faltan)} unidades ya no tienen la digitalización completa")
    resultado: dict[str, Any] = {"ejecutadas": 0, "nuevo_proceso": None}
    para_eliminar: list[tuple[ElementoDisposicion, UnidadDocumental]] = []
    for e, u in filas:
        if p.tipo == "eliminacion":
            e.estado = "ejecutada"
            u.disposicion_aplicada = "eliminada"
            _mover(ctx, proyecto, u, "eliminada", f"Eliminación documental · acta {acta_numero.strip()}")
        elif p.tipo == "seleccion":
            if e.estado == "seleccionada":
                u.disposicion_aplicada = "seleccionada"
            else:
                para_eliminar.append((e, u))
        else:
            e.estado = "ejecutada"
            u.disposicion_aplicada = "digitalizada"
            if destino_fisico == "eliminar":
                para_eliminar.append((e, u))
        resultado["ejecutadas"] += 1
    p.estado, p.ejecutado_en, p.ejecutado_por = "ejecutado", ahora_utc(), ctx.usuario.id
    p.acta_numero, p.metodo, p.destino_fisico = acta_numero.strip() or None, metodo.strip() or None, destino_fisico
    ctx.db.flush()
    if para_eliminar:
        nuevo = _nuevo(ctx, proyecto, "eliminacion", date.today(), f"Viene del proceso n.º {p.numero} ({NOMBRE[p.tipo].lower()})", origen=p)
        for e, u in para_eliminar:
            ctx.db.add(ElementoDisposicion(tenant_id=ctx.tenant_id, proceso_id=nuevo.id, unidad_id=u.id, clasificacion_id=e.clasificacion_id,
                                           aviso="no quedó en la muestra" if p.tipo == "seleccion" else "físico digitalizado con medio técnico"))
        resultado["nuevo_proceso"] = {"id": nuevo.id, "numero": nuevo.numero, "unidades": len(para_eliminar)}
    ctx.auditar(accion="EJECUTAR_DISPOSICION", objeto="ProcesoDisposicion", objeto_id=p.id,
                detalle=f"{NOMBRE[p.tipo]} n.º {p.numero} · {resultado['ejecutadas']} unidades"
                        + (f" · {len(para_eliminar)} pasan a la eliminación n.º {resultado['nuevo_proceso']['numero']}" if para_eliminar else ""))
    ctx.db.commit()
    return resultado


def anular(ctx, proyecto: Proyecto, p: ProcesoDisposicion, motivo: str) -> ProcesoDisposicion:
    _abierto(proyecto)
    if p.estado not in ABIERTOS:
        raise TransicionInvalida("Solo se anula un proceso que no se ha ejecutado")
    p.estado, p.novedad = "anulado", motivo.strip()
    ctx.auditar(accion="ANULAR_DISPOSICION", objeto="ProcesoDisposicion", objeto_id=p.id, motivo=motivo, detalle=f"n.º {p.numero}")
    ctx.db.commit()
    return p


def _series(ctx, filas) -> str:
    codigos = {}
    for e, _ in filas:
        if e.clasificacion_id:
            c = ctx.db.get(ClasificacionUnidad, e.clasificacion_id)
            el = ctx.db.get(ElementoInstrumento, c.elemento_id)
            codigos[el.codigo] = f"{el.codigo} {el.nombre}"
    return "; ".join(codigos[k] for k in sorted(codigos))


def _dependencias(ctx, filas) -> str:
    """«120 Gestión documental, 130 …»: código y nombre de cada dependencia, según la versión con que se clasificó."""
    salida = {}
    for e, _ in filas:
        if not e.clasificacion_id:
            continue
        c = ctx.db.get(ClasificacionUnidad, e.clasificacion_id)
        codigo = ctx.db.get(ElementoInstrumento, c.elemento_id).codigo_dependencia
        nombre = ctx.db.scalar(select(ElementoInstrumento.nombre).where(ElementoInstrumento.version_id == c.version_id, ElementoInstrumento.nivel == "dependencia",
                                                                         ElementoInstrumento.codigo == codigo))
        salida[codigo] = f"{codigo} {nombre}" if nombre else codigo
    return ", ".join(salida[k] for k in sorted(salida))


def documento(ctx, proyecto: Proyecto, p: ProcesoDisposicion, cual: str):
    """«inventario» (FUID de la entidad) o «acta» (acta de eliminación de la entidad), sobre la plantilla vigente."""
    estados = ("ejecutada",) if cual == "acta" else ACTIVOS + ("ejecutada",)
    filas = [(e, u) for e, u in elementos(ctx, p) if e.estado in estados]
    if not filas:
        raise TransicionInvalida("El proceso no tiene unidades para ese documento")
    if cual == "acta":
        if p.tipo != "eliminacion" or p.estado != "ejecutado":
            raise TransicionInvalida("El acta de eliminación se expide cuando la eliminación está ejecutada")
        fechas_i = [u.fecha_inicial for _, u in filas if u.fecha_inicial]
        fechas_f = [u.fecha_final for _, u in filas if u.fecha_final]
        extra = {"numero_acta": p.acta_numero, "numero_proceso": p.numero, "acta_comite": p.comite_acta, "fecha_comite": p.comite_fecha,
                 "publicacion_inicio": p.publicacion_inicio, "publicacion_fin": fin_publicacion(p), "publicacion_enlace": p.publicacion_enlace or "",
                 "metodo": p.metodo or "", "fecha_ejecucion": p.ejecutado_en.date() if p.ejecutado_en else None, "series": _series(ctx, filas),
                 "dependencias": _dependencias(ctx, filas),
                 "fecha_inicial": min(fechas_i) if fechas_i else None, "fecha_final": max(fechas_f) if fechas_f else None,
                 "total_cajas": len({u.caja for _, u in filas if u.caja})}
        return entregables.expedir(ctx, proyecto, "acta_eliminacion", None, None, None, unidad_ids=[u.id for _, u in filas], encabezado_extra=extra,
                                   filtro_extra={"disposicion": p.numero})
    extra = {"objeto": NOMBRE[p.tipo], "numero_transferencia": "", "oficina_productora": "", "fecha_corte": p.fecha_corte}
    return entregables.expedir(ctx, proyecto, "fuid", None, None, None, unidad_ids=[u.id for _, u in filas], encabezado_extra=extra, filtro_extra={"disposicion": p.numero})


def resumen(ctx, p: ProcesoDisposicion) -> dict[str, Any]:
    filas = elementos(ctx, p)
    cuenta = {k: sum(1 for e, _ in filas if e.estado == k) for k in ("incluida", "retirada", "seleccionada", "no_seleccionada", "ejecutada")}
    activas = [(e, u) for e, u in filas if e.estado in ACTIVOS + ("ejecutada",)]
    return {"unidades": len(activas), "folios": sum(u.folios or 0 for _, u in activas), "cajas": len({u.caja for _, u in activas if u.caja}), **cuenta}
