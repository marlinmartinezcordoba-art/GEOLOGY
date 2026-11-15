"""Hoja de control del expediente: elaborarla sobre lo digitalizado, verificarla viendo los documentos y expedirla.

Reglas (Acuerdo 002 de 2014 del AGN; D-25):
- Un trámite por documento, en el orden en que está en el expediente, con fecha, tipo documental, folios y
  las páginas digitalizadas que le corresponden. Los folios se calculan desde las páginas, con el número de
  imágenes por folio de la hoja (1, o 2 si se digitalizó recto y verso), y la continuidad se verifica con las
  reglas del motor de GEOLOGY (R10 a R15).
- Ningún dato aparece sin su origen: quién o qué lo puso y de dónde lo tomó (persona, cálculo desde las
  páginas, lista de la TRD, FUID con su archivo y fila, libro de cálculo importado con su pestaña y fila).
- Una fecha parcial vale más que una inventada: «1931-07» o «S. F.» se registran tal cual.
- La elabora una persona y la verifica otra, trámite por trámite, con los documentos a la vista.
- Si los folios contados no coinciden con el FUID, manda lo contado y queda la constancia.
"""

import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from arca.modelos import (
    ClasificacionUnidad,
    ElementoInstrumento,
    EstadoProyecto,
    EstadoRecurso,
    FilaInventario,
    HojaControl,
    Instrumento,
    LoteInventario,
    Proyecto,
    RecursoDigital,
    TramiteHoja,
    UnidadDocumental,
    Usuario,
    VersionInstrumento,
)
from arca.modelos.base import ahora_utc
from arca.modulos.entregables import servicios as entregables
from arca.modulos.flujo.cola import encolar_ctx
from arca.modulos.m08_inventarios.fuid import clave_de
from arca.modulos.m08_inventarios.servicios import guardar_archivo
from arca.modulos.m10_digitalizacion.paginas import NO_CUENTAN, paginas
from arca.motor import tipologias
from arca.motor.fechas import normalizar_fecha
from arca.motor.folios import Tramite, verificar_folios
from arca.motor.importar_hoja import leer_libro
from arca.nucleo.errores import AccesoDenegado, Conflicto, DatosInvalidos, NoEncontrado, TransicionInvalida

EDITABLES = ("borrador", "devuelta")


def _abierto(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


def _origen(fuente: str, detalle: str) -> dict[str, str]:
    return {"fuente": fuente, "detalle": detalle}


# --- Lo que ARCA sabe del expediente, con su origen ---------------------------------------------


def _clasificacion(ctx, unidad: UnidadDocumental) -> dict[str, Any] | None:
    c = ctx.db.scalar(select(ClasificacionUnidad).where(ClasificacionUnidad.unidad_id == unidad.id, ClasificacionUnidad.estado == "confirmada"))
    if c is None:
        return None
    e = ctx.db.get(ElementoInstrumento, c.elemento_id)
    v = ctx.db.get(VersionInstrumento, c.version_id)
    i = ctx.db.get(Instrumento, v.instrumento_id)
    def nombre(nivel, codigo):
        return ctx.db.scalar(select(ElementoInstrumento.nombre).where(ElementoInstrumento.version_id == v.id, ElementoInstrumento.nivel == nivel, ElementoInstrumento.codigo == codigo))
    serie = (e.padre, nombre("serie", e.padre)) if e.nivel == "subserie" else (e.codigo, e.nombre)
    return {"elemento": e, "version": v, "instrumento": i, "serie": serie, "subserie": (e.codigo, e.nombre) if e.nivel == "subserie" else None,
            "dependencia": (e.codigo_dependencia, nombre("dependencia", e.codigo_dependencia)), "tipos": list(e.tipos_documentales or []),
            "fuente": f"clasificación confirmada con la {i.tipo} «{i.nombre}» v{v.version}" + (f" ({v.acto_administrativo})" if v.acto_administrativo else "")}


def _fila_fuid(ctx, unidad: UnidadDocumental) -> str:
    fila = ctx.db.scalar(select(FilaInventario.numero_fila).where(FilaInventario.unidad_id == unidad.id))
    lote = ctx.db.get(LoteInventario, unidad.lote_id)
    return f"FUID «{lote.nombre_archivo}», fila {fila}" if lote and fila else "FUID del proyecto"


def tipos_sugeridos(clasif: dict[str, Any] | None) -> list[str]:
    """La lista cerrada de tipos documentales de la subserie. Si la TRD no los trae, el que corresponde al nombre de la subserie."""
    if not clasif:
        return []
    if clasif["tipos"]:
        return clasif["tipos"]
    derivado = tipologias.desde_la_subserie(clasif["elemento"].nombre)
    return [derivado] if derivado else []


# --- Hoja y trámites ---------------------------------------------------------------------------


def unidad_de(ctx, proyecto: Proyecto, unidad_id: uuid.UUID) -> UnidadDocumental:
    u = ctx.db.get(UnidadDocumental, unidad_id)
    if u is None or u.proyecto_id != proyecto.id:
        raise NoEncontrado("La unidad no existe en el proyecto")
    return u


def hoja_de(ctx, unidad: UnidadDocumental) -> HojaControl | None:
    return ctx.db.scalar(select(HojaControl).where(HojaControl.unidad_id == unidad.id))


def tramites(ctx, h: HojaControl) -> list[TramiteHoja]:
    return list(ctx.db.scalars(select(TramiteHoja).where(TramiteHoja.hoja_id == h.id).order_by(TramiteHoja.orden)))


def _editable(h: HojaControl) -> None:
    if h.estado not in EDITABLES:
        raise TransicionInvalida("La hoja solo se edita en borrador o cuando la devuelven")


def _recalcular(ctx, h: HojaControl) -> None:
    """Renumera los trámites y, si tienen páginas, recalcula los folios desde ellas."""
    lista = sorted(tramites(ctx, h), key=lambda t: (t.pagina_desde if t.pagina_desde is not None else 10**9, t.orden))
    ipf = h.imagenes_por_folio or 1
    for i, t in enumerate(lista, start=1):
        t.orden = i
        if t.pagina_desde is not None and t.pagina_hasta is not None:
            t.folio_desde, t.folio_hasta = (t.pagina_desde - 1) // ipf + 1, (t.pagina_hasta - 1) // ipf + 1
            imagenes = "1 imagen por folio" if ipf == 1 else f"{ipf} imágenes por folio (recto y verso)"
            t.origen = {**(t.origen or {}), "folios": _origen("calculado", f"de las páginas {t.pagina_desde} a {t.pagina_hasta} del expediente digitalizado, {imagenes}")}
    ctx.db.flush()


def _tipo_inicial(clasif) -> tuple[str, dict[str, str] | None]:
    sugeridos = tipos_sugeridos(clasif)
    if len(sugeridos) == 1:
        detalle = "único tipo documental de la subserie" if clasif["tipos"] else "derivado del nombre de la subserie (la TRD no trae tipos documentales)"
        return sugeridos[0], _origen("trd", f"{detalle} en la {clasif['fuente'].removeprefix('clasificación confirmada con la ')}")
    return "", None


def crear(ctx, proyecto: Proyecto, unidad: UnidadDocumental, imagenes_por_folio: int) -> HojaControl:
    """Crea la hoja. Si el expediente está digitalizado, arranca con un solo trámite que cubre todas las páginas."""
    _abierto(proyecto)
    if imagenes_por_folio not in (1, 2):
        raise DatosInvalidos("Imágenes por folio: 1 (cada imagen es un folio) o 2 (recto y verso)")
    from arca.modulos.procesos.servicios import procesos_de  # noqa: PLC0415

    procesos = procesos_de(ctx, proyecto, unidad)
    if not procesos["hoja_control"]:
        raise TransicionInvalida(f"La unidad no lleva hoja de control según la {procesos['origen']}. Cámbielo en la configuración por lote")
    if hoja_de(ctx, unidad):
        raise Conflicto("La unidad ya tiene hoja de control")
    lista = paginas(ctx, unidad)
    h = HojaControl(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, unidad_id=unidad.id, estado="borrador", imagenes_por_folio=imagenes_por_folio,
                    origen="digitalizacion" if lista else "manual", creado_en=ahora_utc(), creado_por=ctx.usuario.id)
    ctx.db.add(h)
    ctx.db.flush()
    if lista:
        tipo, origen_tipo = _tipo_inicial(_clasificacion(ctx, unidad))
        ctx.db.add(TramiteHoja(tenant_id=ctx.tenant_id, hoja_id=h.id, orden=1, pagina_desde=1, pagina_hasta=len(lista), tipo_documental=tipo,
                               origen={"tipo_documental": origen_tipo} if origen_tipo else {}))
        ctx.db.flush()
        _recalcular(ctx, h)
    ctx.auditar(accion="CREAR_HOJA_CONTROL", objeto="HojaControl", objeto_id=h.id, detalle=f"{proyecto.codigo} · {unidad.identificador} · {len(lista)} páginas digitalizadas")
    ctx.db.commit()
    return h


def _tramite(ctx, h: HojaControl, tramite_id: uuid.UUID) -> TramiteHoja:
    t = ctx.db.get(TramiteHoja, tramite_id)
    if t is None or t.hoja_id != h.id:
        raise NoEncontrado("El trámite no existe en la hoja")
    return t


def dividir(ctx, proyecto: Proyecto, h: HojaControl, tramite_id: uuid.UUID, pagina: int) -> TramiteHoja:
    """«Aquí empieza otro documento»: el trámite se parte en la página indicada."""
    _abierto(proyecto)
    _editable(h)
    t = _tramite(ctx, h, tramite_id)
    if t.pagina_desde is None or not t.pagina_desde < pagina <= t.pagina_hasta:
        raise DatosInvalidos(f"La página debe estar entre {(t.pagina_desde or 0) + 1} y {t.pagina_hasta} para partir este trámite")
    tipo, origen_tipo = _tipo_inicial(_clasificacion(ctx, ctx.db.get(UnidadDocumental, h.unidad_id)))
    nuevo = TramiteHoja(tenant_id=ctx.tenant_id, hoja_id=h.id, orden=t.orden + 1, pagina_desde=pagina, pagina_hasta=t.pagina_hasta, tipo_documental=tipo,
                        origen={"tipo_documental": origen_tipo} if origen_tipo else {})
    t.pagina_hasta = pagina - 1
    ctx.db.add(nuevo)
    ctx.db.flush()
    _recalcular(ctx, h)
    ctx.db.commit()
    return nuevo


def unir(ctx, proyecto: Proyecto, h: HojaControl, tramite_id: uuid.UUID) -> None:
    """Une el trámite con el siguiente (eran un solo documento). Se conservan los datos del primero."""
    _abierto(proyecto)
    _editable(h)
    lista = tramites(ctx, h)
    t = _tramite(ctx, h, tramite_id)
    i = next(k for k, x in enumerate(lista) if x.id == t.id)
    if i + 1 >= len(lista):
        raise DatosInvalidos("Es el último trámite: no hay uno siguiente con el cual unirlo")
    siguiente = lista[i + 1]
    if t.pagina_hasta is not None and siguiente.pagina_hasta is not None:
        t.pagina_hasta = siguiente.pagina_hasta
    else:
        t.folio_hasta = siguiente.folio_hasta
    ctx.db.delete(siguiente)
    ctx.db.flush()
    _recalcular(ctx, h)
    ctx.db.commit()


CAMPOS = ("fecha", "tipo_documental", "detalle", "no_radicado", "observaciones", "folio_desde", "folio_hasta", "metadatos")
METADATOS = ("asunto", "remitente", "destinatario", "firmantes", "lugar", "numero")


def editar(ctx, proyecto: Proyecto, h: HojaControl, tramite_id: uuid.UUID, cambios: dict[str, Any]) -> TramiteHoja:
    _abierto(proyecto)
    _editable(h)
    t = _tramite(ctx, h, tramite_id)
    persona = ctx.usuario.nombre_completo
    origen = dict(t.origen or {})
    for campo, valor in cambios.items():
        if campo not in CAMPOS:
            raise DatosInvalidos(f"Campo desconocido: {campo}")
        if campo == "fecha":
            f = normalizar_fecha(valor)
            t.fecha, t.fecha_texto = f.completa, f.texto
            origen["fecha"] = _origen("persona", f"escrita por {persona}" + ("" if f.texto else " como sin fecha (S. F.)") + (" (fecha parcial)" if f.es_parcial else ""))
        elif campo == "tipo_documental":
            t.tipo_documental = str(valor or "").strip()[:300]
            lista = tipos_sugeridos(_clasificacion(ctx, ctx.db.get(UnidadDocumental, h.unidad_id)))
            en_lista = tipologias.como_sustantivo(t.tipo_documental).lower() in {tipologias.como_sustantivo(x).lower() for x in lista}
            origen["tipo_documental"] = _origen("persona", f"elegido por {persona}" + (" de la lista de la TRD" if en_lista else " (no está en la lista de la TRD)"))
        elif campo == "metadatos":
            actuales = dict(t.metadatos or {})
            for clave, v in (valor or {}).items():
                if clave not in METADATOS:
                    raise DatosInvalidos(f"Metadato desconocido: {clave}")
                actuales[clave] = str(v or "").strip()[:300]
                origen[f"metadatos.{clave}"] = _origen("persona", f"escrito por {persona}")
            t.metadatos = {k: v for k, v in actuales.items() if v}
        elif campo in ("folio_desde", "folio_hasta"):
            if t.pagina_desde is not None:
                raise DatosInvalidos("Los folios de un trámite con páginas digitalizadas se calculan desde ellas: parta o una trámites")
            setattr(t, campo, int(valor) if valor not in (None, "") else None)
            origen["folios"] = _origen("persona", f"escritos por {persona}")
        else:
            setattr(t, campo, str(valor or "").strip())
            origen[campo] = _origen("persona", f"escrito por {persona}")
    t.origen = origen
    ctx.db.commit()
    return t


def agregar(ctx, proyecto: Proyecto, h: HojaControl) -> TramiteHoja:
    """Un trámite al final, para la hoja de un expediente sin digitalizar (folios a mano)."""
    _abierto(proyecto)
    _editable(h)
    lista = tramites(ctx, h)
    if any(t.pagina_desde is not None for t in lista):
        raise DatosInvalidos("En un expediente digitalizado los trámites salen de partir las páginas")
    desde = (lista[-1].folio_hasta or 0) + 1 if lista else 1
    t = TramiteHoja(tenant_id=ctx.tenant_id, hoja_id=h.id, orden=len(lista) + 1, folio_desde=desde, folio_hasta=desde)
    ctx.db.add(t)
    ctx.db.commit()
    return t


def quitar(ctx, proyecto: Proyecto, h: HojaControl, tramite_id: uuid.UUID) -> None:
    _abierto(proyecto)
    _editable(h)
    t = _tramite(ctx, h, tramite_id)
    if t.pagina_desde is not None:
        raise DatosInvalidos("Un trámite con páginas no se quita: únalo con otro, para que ninguna página quede sin documento")
    ctx.db.delete(t)
    ctx.db.flush()
    _recalcular(ctx, h)
    ctx.db.commit()


def cambiar_imagenes_por_folio(ctx, proyecto: Proyecto, h: HojaControl, valor: int) -> HojaControl:
    _abierto(proyecto)
    _editable(h)
    if valor not in (1, 2):
        raise DatosInvalidos("Imágenes por folio: 1 o 2")
    h.imagenes_por_folio = valor
    _recalcular(ctx, h)
    ctx.db.commit()
    return h


# --- Propuesta desde el OCR ---------------------------------------------------------------------


def proponer_desde_ocr(ctx, proyecto: Proyecto, h: HojaControl, reemplazar: bool) -> dict[str, Any]:
    """Arma los trámites con lo que leyó el OCR. Todo queda como propuesta (origen «ocr») hasta que una persona lo confirma."""
    from arca.modulos.m13_ocr import propuestas  # noqa: PLC0415 — el OCR usa las páginas de digitalización; se importa al usarlo
    from arca.modulos.m13_ocr.servicios import textos  # noqa: PLC0415

    _abierto(proyecto)
    _editable(h)
    u = ctx.db.get(UnidadDocumental, h.unidad_id)
    lista = textos(ctx, u)
    if not lista:
        raise TransicionInvalida("El expediente no tiene páginas digitalizadas")
    faltan = sum(1 for p in lista if p["estado"] == "pendiente")
    if faltan:
        raise TransicionInvalida(f"Faltan {faltan} páginas por leer con OCR")
    actuales = tramites(ctx, h)
    trabajados = len(actuales) > 1 or any(t.tipo_documental or t.fecha_texto or t.detalle for t in actuales)
    if trabajados and not reemplazar:
        raise Conflicto("La hoja ya tiene trámites trabajados: confirme que quiere reemplazarlos por la propuesta del OCR")
    clasif = _clasificacion(ctx, u)
    docs = propuestas.proponer(lista, tipos_sugeridos(clasif))
    for t in actuales:
        ctx.db.delete(t)
    ctx.db.flush()
    for i, d in enumerate(docs, start=1):
        f = normalizar_fecha(d.fecha) if d.fecha else None
        origen = {campo: _origen("ocr", e.frase()) for campo, e in d.evidencias.items()}
        corte = d.evidencias.get("tipo_documental")
        origen["corte"] = _origen("ocr", f"el documento empieza en la página {d.pagina_desde}" + (f": «{corte.fragmento[:80]}»" if corte else " (primera página del expediente)")
                                  + f" · confianza del corte {d.confianza}")
        if d.tipo and not d.tipo_en_trd:
            origen["tipo_documental"]["detalle"] += " (no está en la lista de la TRD)"
        ctx.db.add(TramiteHoja(tenant_id=ctx.tenant_id, hoja_id=h.id, orden=i, pagina_desde=d.pagina_desde, pagina_hasta=d.pagina_hasta, tipo_documental=d.tipo[:300],
                               detalle=d.detalle, fecha=f.completa if f else None, fecha_texto=f.texto if f else None, no_radicado=d.radicado[:100], origen=origen,
                               metadatos=dict(d.metadatos)))
    ctx.db.flush()
    _recalcular(ctx, h)
    ctx.auditar(accion="PROPONER_HOJA_OCR", objeto="HojaControl", objeto_id=h.id,
                detalle=f"{u.identificador} · {len(docs)} documentos propuestos sobre {len(lista)} páginas")
    ctx.db.commit()
    return {"documentos": len(docs), "paginas": len(lista), "frase": f"{len(docs)} {'documento' if len(docs) == 1 else 'documentos'}"}


def confirmar(ctx, proyecto: Proyecto, h: HojaControl, tramite_id: uuid.UUID) -> TramiteHoja:
    """La persona revisó lo propuesto por el OCR y lo acepta tal cual: el origen pasa a ella, conservando de dónde vino."""
    _abierto(proyecto)
    _editable(h)
    t = _tramite(ctx, h, tramite_id)
    origen = dict(t.origen or {})
    for campo, o in origen.items():
        if o.get("fuente") == "ocr":
            origen[campo] = _origen("persona", f"confirmado por {ctx.usuario.nombre_completo} ({o['detalle']})")
    t.origen = origen
    ctx.db.commit()
    return t


# --- Importar hojas diligenciadas en libros de cálculo (lector de GEOLOGY) ----------------------


def importar(ctx, proyecto: Proyecto, contenido: bytes, nombre: str, imagenes_por_folio: int = 1) -> list[dict[str, Any]]:
    """Una hoja por pestaña. Se asocia a la unidad por el código de carpeta; lo que no se reconoce se informa."""
    _abierto(proyecto)
    archivo = guardar_archivo(ctx, proyecto, contenido, nombre, {"XLSX"})
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "hoja.xlsx"
        ruta.write_bytes(contenido)
        leidas = leer_libro(ruta, nombre)
    unidades = {u.clave: u for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id))}
    reporte = []
    for hi in leidas:
        fila: dict[str, Any] = {"pestana": hi.hoja, "carpeta": hi.codigo_carpeta, "tramites": len(hi.tramites), "avisos": hi.avisos, "resultado": "", "unidad": None}
        if hi.error or not hi.sirve:
            fila["resultado"] = hi.error or "no se reconoció el código de la carpeta o no hay trámites"
            reporte.append(fila)
            continue
        u = _reconocer(unidades, [hi.codigo_carpeta, hi.hoja, *map(str, (hi.encabezado or {}).values())])
        if u is None:
            fila["resultado"] = f"la carpeta «{hi.codigo_carpeta}» no está en el inventario del proyecto"
            reporte.append(fila)
            continue
        h = hoja_de(ctx, u)
        if h and h.estado not in EDITABLES:
            fila["resultado"] = f"la hoja de {u.identificador} ya está {h.estado.replace('_', ' ')}: no se reemplaza"
            reporte.append(fila)
            continue
        if h is None:
            h = HojaControl(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, unidad_id=u.id, estado="borrador", imagenes_por_folio=imagenes_por_folio,
                            creado_en=ahora_utc(), creado_por=ctx.usuario.id)
            ctx.db.add(h)
            ctx.db.flush()
        for anterior in tramites(ctx, h):
            ctx.db.delete(anterior)
        h.origen, h.importacion = "importada", {"archivo": nombre, "sha256": archivo.sha256, "pestana": hi.hoja}
        for orden, t in enumerate(hi.tramites, start=1):
            f = normalizar_fecha(t.get("fecha"))
            donde = f"importado de «{nombre}», pestaña «{hi.hoja}», fila {t.get('fila')}"
            tipo, detalle = tipologias.partir(t.get("tipo_documental") or "")
            desde = _entero(t.get("folio_desde"))
            hasta = _entero(t.get("folio_hasta")) or desde
            ctx.db.add(TramiteHoja(
                tenant_id=ctx.tenant_id, hoja_id=h.id, orden=orden, fecha=f.completa, fecha_texto=f.texto, tipo_documental=(tipo or "")[:300], detalle=detalle or "",
                folio_desde=desde, folio_hasta=hasta, no_radicado=t.get("no_radicado") or "", observaciones=t.get("observaciones") or "",
                origen={c: _origen("importado", donde) for c in ("fecha", "tipo_documental", "detalle", "folios", "no_radicado")},
            ))
        fila["resultado"], fila["unidad"] = "importada", u.identificador
        reporte.append(fila)
    ctx.auditar(accion="IMPORTAR_HOJAS_CONTROL", objeto="Proyecto", objeto_id=proyecto.id,
                detalle=f"{proyecto.codigo} · «{nombre}» · {sum(1 for r in reporte if r['resultado'] == 'importada')} de {len(reporte)} hojas · SHA-256 {archivo.sha256[:16]}…")
    ctx.db.commit()
    return reporte


def _reconocer(unidades: dict[str, UnidadDocumental], textos: list[str]) -> UnidadDocumental | None:
    """La unidad del inventario que nombra alguno de estos textos (el código leído, el nombre de la pestaña, el encabezado)."""
    for texto in textos:
        if not texto:
            continue
        if u := unidades.get(clave_de(texto)):
            return u
        for candidato in re.findall(r"[A-Za-z]{1,12}[\s_-]?\d{1,8}", texto):
            if u := unidades.get(clave_de(candidato)):
                return u
    return None


def _entero(valor) -> int | None:
    m = re.search(r"\d+", str(valor or ""))
    return int(m.group(0)) if m else None


# --- Verificar: reglas, comparación con el FUID y con lo digitalizado ---------------------------


def legibilidad(ctx, lista_paginas: list[dict[str, Any]]) -> list[str]:
    """Lo que el OCR dice de la calidad de cada página: poco legible, sin texto o girada (y ya mostrada derecha)."""
    from arca.modelos import TextoPagina  # noqa: PLC0415

    if not lista_paginas:
        return []
    por_clave = {(p["recurso_id"], p["pagina_en_archivo"]): p["n"] for p in lista_paginas}
    bajas, vacias, giradas = [], [], []
    for t in ctx.db.scalars(select(TextoPagina).where(TextoPagina.recurso_id.in_({k[0] for k in por_clave}))):
        n = por_clave.get((t.recurso_id, t.pagina))
        if n is None:
            continue
        if t.estado == "sin_texto":
            vacias.append(n)
        elif t.estado == "leida" and (t.confianza or 0) < 60:
            bajas.append(n)
        if t.rotacion:
            giradas.append(f"{n} ({t.rotacion}°)")
    salida = []
    if bajas:
        salida.append(f"páginas {', '.join(map(str, sorted(bajas)))}: el OCR las leyó con confianza baja (menos de 60 %); revise la imagen y, si no se lee bien, pida la recaptura")
    if vacias:
        salida.append(f"páginas {', '.join(map(str, sorted(vacias)))}: sin texto legible (hoja en blanco, reverso o imagen ilegible)")
    if giradas:
        salida.append(f"páginas {', '.join(giradas)}: estaban giradas; ARCA las muestra y las lee derechas (el original no se toca)")
    return salida


def validar(ctx, h: HojaControl) -> dict[str, Any]:
    u = ctx.db.get(UnidadDocumental, h.unidad_id)
    lista = tramites(ctx, h)
    clasif = _clasificacion(ctx, u)
    sugeridos = {tipologias.como_sustantivo(x).lower() for x in tipos_sugeridos(clasif)}
    errores: list[dict[str, Any]] = []
    avisos: list[str] = []
    motor = [Tramite(no_item=t.orden, tipo_documental=t.tipo_documental, folio_desde_leido=str(t.folio_desde or ""), folio_hasta_leido=str(t.folio_hasta or ""),
                     no_item_leido=str(t.orden), fecha=normalizar_fecha(t.fecha_texto)) for t in lista]
    r = verificar_folios(motor, u.folios)
    por_orden = {t.orden: t for t in lista}
    for e in r.errores_localizados:
        errores.append({"tramite_id": por_orden[e.no_item].id if e.no_item in por_orden else None, "orden": e.no_item, "campo": e.campo, "mensaje": e.mensaje})
    if not lista:
        errores.append({"tramite_id": None, "orden": None, "campo": "", "mensaje": "la hoja no tiene trámites"})
    for t in lista:
        propuestos = [c for c, o in (t.origen or {}).items() if o.get("fuente") == "ocr"]
        if propuestos:
            nombres = {"tipo_documental": "tipo documental", "fecha": "fecha", "detalle": "detalle", "no_radicado": "radicado", "corte": "dónde empieza",
                       "metadatos.asunto": "asunto", "metadatos.remitente": "remitente", "metadatos.destinatario": "destinatario",
                       "metadatos.firmantes": "firmantes", "metadatos.lugar": "lugar", "metadatos.numero": "número"}
            errores.append({"tramite_id": t.id, "orden": t.orden, "campo": "ocr",
                            "mensaje": f"propuesto por OCR sin confirmar: {', '.join(nombres.get(c, c) for c in propuestos)}"})
    lista_paginas = paginas(ctx, u)
    if lista_paginas and any(t.pagina_desde is not None for t in lista):
        cubiertas = sorted(p for t in lista if t.pagina_desde is not None for p in range(t.pagina_desde, t.pagina_hasta + 1))
        if cubiertas != list(range(1, len(lista_paginas) + 1)):
            errores.append({"tramite_id": None, "orden": None, "campo": "paginas", "mensaje": f"las páginas de los trámites no cubren las {len(lista_paginas)} del expediente digitalizado, una sola vez cada una"})
    if sugeridos:
        fuera = [t.orden for t in lista if t.tipo_documental and tipologias.como_sustantivo(t.tipo_documental).lower() not in sugeridos]
        if fuera:
            avisos.append(f"trámites {', '.join(map(str, fuera))}: el tipo documental no está en la lista de la subserie según la TRD")
    elif clasif is None:
        avisos.append("la unidad no está clasificada: no hay lista de tipos documentales de la TRD para comparar")
    avisos.extend(legibilidad(ctx, lista_paginas))
    anterior = None
    for t in lista:  # los documentos de una unidad compleja van en orden cronológico
        if t.fecha:
            if anterior and t.fecha < anterior.fecha:
                avisos.append(f"trámite {t.orden}: su fecha ({t.fecha.isoformat()}) es anterior a la del trámite {anterior.orden} ({anterior.fecha.isoformat()}): revise el orden cronológico")
            anterior = t
    from arca.modulos.historias import servicios as historias  # noqa: PLC0415 — solo lee el titular y la configuración

    avisos.extend(historias.avisos_hoja(ctx, u))
    from arca.modulos.alistamiento import servicios as alistamiento  # noqa: PLC0415

    avisos.extend(alistamiento.avisos_hoja(ctx, u, r.total_folios))
    pendientes_qc = sum(1 for p in lista_paginas if p["estado"] != EstadoRecurso.APROBADO.value)
    if pendientes_qc:
        avisos.append(f"{pendientes_qc} páginas aún no están aprobadas en el control de calidad de la digitalización")
    fechas = sorted(t.fecha_texto for t in lista if t.fecha_texto)
    if fechas and u.fecha_inicial and u.fecha_final and (fechas[0][:4] < str(u.fecha_inicial.year) or fechas[-1][:4] > str(u.fecha_final.year)):
        avisos.append(f"las fechas de la hoja ({fechas[0]} a {fechas[-1]}) se salen de las fechas extremas del FUID ({u.fecha_inicial.isoformat()} a {u.fecha_final.isoformat()})")
    if r.diferencia_folios:
        avisos.append(r.diferencia_folios)
    if lista_paginas:
        folios_imagenes = (len(lista_paginas) - 1) // (h.imagenes_por_folio or 1) + 1
        if r.total_folios and folios_imagenes != r.total_folios:
            avisos.append(f"la hoja suma {r.total_folios} folios y lo digitalizado da {folios_imagenes} ({len(lista_paginas)} imágenes)")
    sin_fecha = sum(1 for t in lista if not t.fecha_texto)
    return {"errores": errores, "avisos": avisos, "correcciones": [o for o in r.observaciones if o != r.diferencia_folios],
            "total_folios": r.total_folios, "fecha_inicial": fechas[0] if fechas else None, "fecha_final": fechas[-1] if fechas else None,
            "sin_fecha": sin_fecha, "diferencia_folios": r.diferencia_folios, "paginas": len(lista_paginas)}


def metadatos(ctx, proyecto: Proyecto, h: HojaControl | None, u: UnidadDocumental) -> list[dict[str, Any]]:
    """El encabezado de la hoja: cada dato con de dónde lo tomó ARCA, para validarlo."""
    clasif = _clasificacion(ctx, u)
    fuid = _fila_fuid(ctx, u)
    v = validar(ctx, h) if h else None
    filas = [
        {"campo": "entidad", "etiqueta": "Entidad", "valor": proyecto.entidad_cliente, "fuente": "proyecto", "detalle": f"entidad cliente del proyecto {proyecto.codigo}"},
    ]
    if clasif:
        dep = clasif["dependencia"]
        filas += [
            {"campo": "oficina_productora", "etiqueta": "Oficina productora", "valor": f"{dep[0]} {dep[1] or ''}".strip(), "fuente": "clasificacion", "detalle": clasif["fuente"]},
            {"campo": "serie", "etiqueta": "Serie", "valor": f"{clasif['serie'][0]} {clasif['serie'][1] or ''}".strip(), "fuente": "clasificacion", "detalle": clasif["fuente"]},
            {"campo": "subserie", "etiqueta": "Subserie", "valor": f"{clasif['subserie'][0]} {clasif['subserie'][1]}" if clasif["subserie"] else "—", "fuente": "clasificacion", "detalle": clasif["fuente"]},
        ]
    else:
        filas.append({"campo": "serie", "etiqueta": "Serie y subserie", "valor": None, "fuente": "falta", "detalle": "la unidad no tiene clasificación confirmada", "alerta": "Clasifíquela en la pestaña Clasificación"})
    filas += [
        {"campo": "identificador", "etiqueta": "Identificador", "valor": u.identificador, "fuente": "fuid", "detalle": fuid},
        {"campo": "nombre", "etiqueta": "Expediente", "valor": u.nombre, "fuente": "fuid", "detalle": fuid},
        {"campo": "caja", "etiqueta": "Caja · carpeta", "valor": f"{u.caja or '—'} · {u.carpeta or '—'}", "fuente": "fuid", "detalle": fuid},
    ]
    fuid_fechas = f"{u.fecha_inicial.isoformat() if u.fecha_inicial else 'S. F.'} a {u.fecha_final.isoformat() if u.fecha_final else 'S. F.'}"
    if v and v["fecha_inicial"]:
        iguales = v["fecha_inicial"] == (u.fecha_inicial.isoformat() if u.fecha_inicial else None) and v["fecha_final"] == (u.fecha_final.isoformat() if u.fecha_final else None)
        filas.append({"campo": "fechas", "etiqueta": "Fechas extremas", "valor": f"{v['fecha_inicial']} a {v['fecha_final']}", "fuente": "calculado",
                      "detalle": f"de la fecha más antigua y la más reciente de los trámites{' (' + str(v['sin_fecha']) + ' sin fecha)' if v['sin_fecha'] else ''}",
                      "alerta": None if iguales else f"el FUID dice {fuid_fechas}"})
    else:
        filas.append({"campo": "fechas", "etiqueta": "Fechas extremas", "valor": fuid_fechas, "fuente": "fuid", "detalle": f"{fuid} (la hoja aún no tiene fechas)"})
    if v:
        filas.append({"campo": "folios", "etiqueta": "Folios", "valor": v["total_folios"], "fuente": "calculado", "detalle": "suma de los folios de los trámites",
                      "alerta": f"el FUID dice {u.folios}" if u.folios is not None and v["total_folios"] != u.folios else None})
    else:
        filas.append({"campo": "folios", "etiqueta": "Folios", "valor": u.folios, "fuente": "fuid", "detalle": fuid})
    n_pag = len(paginas(ctx, u))
    filas.append({"campo": "digitalizacion", "etiqueta": "Digitalizado", "valor": f"{n_pag} imágenes" if n_pag else "sin digitalizar", "fuente": "digitalizacion",
                  "detalle": "archivos cargados y asociados a la unidad (sin contar los reemplazados ni los rechazados)"})
    return filas


# --- Revisión y verificación -------------------------------------------------------------------


def enviar(ctx, proyecto: Proyecto, h: HojaControl) -> HojaControl:
    _abierto(proyecto)
    _editable(h)
    v = validar(ctx, h)
    if v["errores"]:
        raise TransicionInvalida(f"La hoja tiene {len(v['errores'])} errores: corríjalos antes de enviarla a verificación")
    for t in tramites(ctx, h):
        t.revision, t.observacion_revision = "pendiente", ""
    h.estado, h.enviada_en, h.enviada_por, h.total_folios = "en_revision", ahora_utc(), ctx.usuario.id, v["total_folios"]
    ctx.auditar(accion="ENVIAR_HOJA_CONTROL", objeto="HojaControl", objeto_id=h.id, detalle=f"{v['total_folios']} folios · {len(tramites(ctx, h))} trámites")
    encolar_ctx(ctx, proyecto.id, h.unidad_id, "hoja enviada a verificación")
    ctx.db.commit()
    return h


def _revisor(ctx, h: HojaControl) -> None:
    if h.estado != "en_revision":
        raise TransicionInvalida("La hoja no está en verificación")
    if ctx.usuario.id in (h.enviada_por, h.creado_por):
        raise AccesoDenegado("Quien elaboró la hoja no la verifica (segregación de funciones)")


def revisar(ctx, proyecto: Proyecto, h: HojaControl, tramite_id: uuid.UUID, conforme: bool, observacion: str) -> TramiteHoja:
    _abierto(proyecto)
    _revisor(ctx, h)
    t = _tramite(ctx, h, tramite_id)
    if not conforme and len(observacion.strip()) < 5:
        raise DatosInvalidos("Escriba qué hay que corregir en el trámite")
    t.revision, t.observacion_revision = ("conforme", "") if conforme else ("observada", observacion.strip())
    ctx.db.commit()
    return t


def verificar(ctx, proyecto: Proyecto, h: HojaControl) -> HojaControl:
    _abierto(proyecto)
    _revisor(ctx, h)
    lista = tramites(ctx, h)
    if any(t.revision != "conforme" for t in lista):
        raise TransicionInvalida("Para verificar, todos los trámites deben estar conformes; si alguno tiene observación, devuelva la hoja")
    h.estado, h.verificada_en, h.verificada_por, h.novedad = "verificada", ahora_utc(), ctx.usuario.id, ""
    ctx.auditar(accion="VERIFICAR_HOJA_CONTROL", objeto="HojaControl", objeto_id=h.id, detalle=f"{len(lista)} trámites · {h.total_folios} folios")
    encolar_ctx(ctx, proyecto.id, h.unidad_id, "hoja verificada")
    ctx.db.commit()
    return h


def devolver(ctx, proyecto: Proyecto, h: HojaControl, motivo: str) -> HojaControl:
    _abierto(proyecto)
    _revisor(ctx, h)
    h.estado, h.novedad = "devuelta", motivo.strip()
    ctx.auditar(accion="DEVOLVER_HOJA_CONTROL", objeto="HojaControl", objeto_id=h.id, motivo=motivo,
                detalle=f"{sum(1 for t in tramites(ctx, h) if t.revision == 'observada')} trámites con observación")
    encolar_ctx(ctx, proyecto.id, h.unidad_id, "hoja devuelta")
    ctx.db.commit()
    return h


def reabrir(ctx, proyecto: Proyecto, h: HojaControl, motivo: str) -> HojaControl:
    """Una hoja verificada que hay que corregir vuelve a borrador, con motivo. La verificación anterior queda en la auditoría."""
    _abierto(proyecto)
    if h.estado != "verificada":
        raise TransicionInvalida("Solo se reabre una hoja verificada")
    h.estado, h.novedad, h.verificada_en, h.verificada_por = "devuelta", motivo.strip(), None, None
    ctx.auditar(accion="REABRIR_HOJA_CONTROL", objeto="HojaControl", objeto_id=h.id, motivo=motivo)
    encolar_ctx(ctx, proyecto.id, h.unidad_id, "hoja reabierta")
    ctx.db.commit()
    return h


def expedir(ctx, proyecto: Proyecto, h: HojaControl):
    """La hoja de control en el formato de la entidad. Solo la verificada."""
    if h.estado != "verificada":
        raise TransicionInvalida("La hoja de control se expide cuando está verificada")
    u = ctx.db.get(UnidadDocumental, h.unidad_id)
    v = validar(ctx, h)
    clasif = _clasificacion(ctx, u)
    nombre = lambda uid: ctx.db.scalar(select(Usuario.nombre_completo).where(Usuario.id == uid)) if uid else ""  # noqa: E731
    encabezado = {
        "numero_orden": u.numero_orden, "identificador": u.identificador, "codigo_serie": u.codigo_serie, "nombre": u.nombre, "caja": u.caja, "carpeta": u.carpeta,
        "tomo": u.tomo, "otro": u.otro, "folios": u.folios, "soporte": u.soporte, "frecuencia_consulta": u.frecuencia_consulta, "notas": u.notas, "fase": u.fase,
        "fecha_inicial": v["fecha_inicial"] or u.fecha_inicial, "fecha_final": v["fecha_final"] or u.fecha_final,
        "codigo_clasificacion": clasif["elemento"].codigo if clasif else "", "serie": (clasif["serie"][1] or "") if clasif else "",
        "subserie": clasif["subserie"][1] if clasif and clasif["subserie"] else "", "dependencia": clasif["dependencia"][0] if clasif else "",
        "oficina_productora": f"{clasif['dependencia'][0]} {clasif['dependencia'][1] or ''}".strip() if clasif else "",
        "total_folios": v["total_folios"], "total_documentos": len(tramites(ctx, h)), "elaboro": nombre(h.enviada_por or h.creado_por), "verifico": nombre(h.verificada_por),
        "fecha_verificacion": h.verificada_en.date() if h.verificada_en else None, "diferencia_folios": v["diferencia_folios"],
    }
    filas = [{"orden": t.orden, "fecha": t.fecha or t.fecha_texto or "S. F.", "tipo_documental": t.tipo_documental, "detalle": t.detalle, "folio_desde": t.folio_desde,
              "folio_hasta": t.folio_hasta, "folios": (t.folio_hasta - t.folio_desde + 1) if t.folio_desde and t.folio_hasta else None,
              "no_radicado": t.no_radicado or "N/A", "observaciones": t.observaciones, **{k: (t.metadatos or {}).get(k, "") for k in METADATOS}} for t in tramites(ctx, h)]
    return entregables.expedir_filas(ctx, proyecto, "hoja_control", encabezado, filas, f"Hoja_control_{u.identificador}", {"hoja_control": u.identificador})


# --- Bandeja del proyecto ----------------------------------------------------------------------


def bandeja(ctx, proyecto: Proyecto, estado: str | None, q: str | None, desplazamiento: int, limite: int) -> tuple[int, list[dict[str, Any]], dict[str, int]]:
    unidades = list(ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id)))
    hojas = {h.unidad_id: h for h in ctx.db.scalars(select(HojaControl).where(HojaControl.proyecto_id == proyecto.id))}
    cuenta_tramites = dict(ctx.db.execute(select(TramiteHoja.hoja_id, func.count()).group_by(TramiteHoja.hoja_id)).all()) if hojas else {}
    imagenes: dict[uuid.UUID, int] = {}
    for uid, pags in ctx.db.execute(select(RecursoDigital.unidad_id, RecursoDigital.paginas).where(RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.estado.not_in(NO_CUENTAN))):
        imagenes[uid] = imagenes.get(uid, 0) + max(1, pags or 1)
    from arca.modulos.procesos.servicios import configuraciones, mapa_lotes, procesos_de  # noqa: PLC0415

    confs, mapa = configuraciones(ctx, proyecto), mapa_lotes(ctx, proyecto)
    filas = []
    for u in unidades:
        h = hojas.get(u.id)
        aplica = h is not None or procesos_de(ctx, proyecto, u, confs, mapa)["hoja_control"]
        filas.append({"unidad_id": u.id, "identificador": u.identificador, "nombre": u.nombre, "caja": u.caja, "carpeta": u.carpeta, "folios_fuid": u.folios,
                      "imagenes": imagenes.get(u.id, 0), "estado": h.estado if h else ("sin_hoja" if aplica else "no_aplica"), "hoja_id": h.id if h else None,
                      "tramites": cuenta_tramites.get(h.id, 0) if h else 0, "total_folios": h.total_folios if h else None, "novedad": h.novedad if h else ""})
    cuenta = {k: sum(1 for f in filas if f["estado"] == k) for k in ("sin_hoja", "borrador", "en_revision", "devuelta", "verificada", "no_aplica")}
    cuenta["digitalizadas_sin_hoja"] = sum(1 for f in filas if f["estado"] == "sin_hoja" and f["imagenes"])
    if estado:
        filas = [f for f in filas if f["estado"] == estado]
    if q and (t := q.strip().lower()):
        filas = [f for f in filas if t in f"{f['identificador']} {f['nombre']} {f['caja'] or ''}".lower()]
    filas.sort(key=lambda f: (f["caja"] or "", f["identificador"]))
    return len(filas), filas[desplazamiento:desplazamiento + limite], cuenta
