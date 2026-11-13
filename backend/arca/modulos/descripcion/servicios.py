"""Configuración de procesos por lote y descripción ISAD(G) (NTC 4095:2013) de cada unidad documental.

Reglas (D-26, D-36):
- Cada lote de trabajo dice si lleva hoja de control, descripción ISAD(G) o ambas. Lo que no se configure para un
  lote toma lo del proyecto; el proyecto, si nadie lo configuró, lleva hoja de control y no ISAD(G).
- La descripción no depende de la fase del ciclo vital (D-24). Sí depende de la digitalización: solo se describe lo
  digitalizado, y se construye sobre lo que ya se verificó.
  - Si el lote lleva hoja de control, se describe con la hoja verificada (fechas, folios, tipos).
  - Si no la lleva, se usa el texto del OCR (documentos y fechas que se reconocieron).
- Lo que se deduce se calcula con código, con su origen: código de referencia, fechas extremas, volumen,
  productor, valoración desde la TRD, acceso, copias digitales.
- El título y el alcance y contenido se PROPONEN y una persona los escribe o los confirma. Una propuesta sin
  confirmar no se envía.
- Antes de enviar se corren las reglas de revisión del motor de GEOLOGY: con un hallazgo «DEVUELVE» no se envía.
  La aprueba otra persona.
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select

from arca.modelos import (
    ClasificacionUnidad,
    DescripcionUnidad,
    ElementoInstrumento,
    EstadoProyecto,
    HojaControl,
    Instrumento,
    MovimientoFase,
    Proyecto,
    TramiteHoja,
    UnidadDocumental,
    Usuario,
    VersionInstrumento,
)
from arca.modelos.base import ahora_utc
from arca.modelos.transferencias import FASES
from arca.modulos.entregables import servicios as entregables
from arca.modulos.flujo.cola import encolar_ctx
from arca.modulos.m10_digitalizacion.paginas import paginas
from arca.modulos.procesos.servicios import configuraciones, mapa_lotes, procesos_de
from arca.motor.isadg import descripcion as motor
from arca.motor.isadg import revision
from arca.nucleo.errores import AccesoDenegado, Conflicto, DatosInvalidos, NoEncontrado, TransicionInvalida

# (clave, elemento de la norma, etiqueta, área, se puede editar)
ELEMENTOS: list[tuple[str, str, str, str, bool]] = [
    ("codigo_referencia", "3.1.1", "Código de referencia", "Identificación", False),
    ("titulo", "3.1.2", "Título", "Identificación", True),
    ("fecha_inicial", "3.1.3", "Fecha inicial", "Identificación", True),
    ("fecha_final", "3.1.3", "Fecha final", "Identificación", True),
    ("nivel", "3.1.4", "Nivel de descripción", "Identificación", False),
    ("volumen", "3.1.5", "Volumen y soporte", "Identificación", True),
    ("productor", "3.2.1", "Nombre del productor", "Contexto", True),
    ("historia_archivistica", "3.2.3", "Historia archivística", "Contexto", True),
    ("forma_ingreso", "3.2.4", "Forma de ingreso", "Contexto", True),
    ("alcance", "3.3.1", "Alcance y contenido", "Contenido y estructura", True),
    ("valoracion", "3.3.2", "Valoración, selección y eliminación", "Contenido y estructura", False),
    ("organizacion", "3.3.4", "Organización", "Contenido y estructura", True),
    ("acceso", "3.4.1", "Condiciones de acceso", "Acceso y uso", True),
    ("lengua", "3.4.3", "Lengua", "Acceso y uso", True),
    ("instrumentos", "3.4.5", "Instrumentos de descripción", "Acceso y uso", True),
    ("copias", "3.5.2", "Existencia y localización de copias", "Documentación asociada", False),
    ("notas", "3.6.1", "Notas", "Notas", True),
    ("reglas", "3.7.2", "Reglas o normas", "Control de la descripción", False),
]
CLAVES = [e[0] for e in ELEMENTOS]
EDITABLES = {e[0] for e in ELEMENTOS if e[4]}
ACCESO = {"publica": "Acceso público", "clasificada": "Información pública clasificada (Ley 1712 de 2014): acceso restringido según la causal",
          "reservada": "Información pública reservada (Ley 1712 de 2014): sin acceso público durante la reserva"}
ESTADOS_EDITABLES = ("borrador", "devuelta")


def _abierto(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


def _origen(fuente: str, detalle: str) -> dict[str, str]:
    return {"fuente": fuente, "detalle": detalle}


# --- Lo verificado que alimenta la descripción ----------------------------------------------------


def _clasificacion(ctx, u: UnidadDocumental) -> dict[str, Any] | None:
    c = ctx.db.scalar(select(ClasificacionUnidad).where(ClasificacionUnidad.unidad_id == u.id, ClasificacionUnidad.estado == "confirmada"))
    if c is None:
        return None
    e = ctx.db.get(ElementoInstrumento, c.elemento_id)
    v = ctx.db.get(VersionInstrumento, c.version_id)
    i = ctx.db.get(Instrumento, v.instrumento_id)
    def nombre(nivel, codigo):
        return ctx.db.scalar(select(ElementoInstrumento.nombre).where(ElementoInstrumento.version_id == v.id, ElementoInstrumento.nivel == nivel, ElementoInstrumento.codigo == codigo)) or ""
    return {"e": e, "v": v, "i": i, "dependencia": nombre("dependencia", e.codigo_dependencia), "serie": nombre("serie", e.padre) if e.nivel == "subserie" else e.nombre,
            "fuente": f"{i.tipo} «{i.nombre}» v{v.version}" + (f" ({v.acto_administrativo})" if v.acto_administrativo else "")}


def _hoja(ctx, u: UnidadDocumental) -> tuple[HojaControl | None, list[TramiteHoja]]:
    h = ctx.db.scalar(select(HojaControl).where(HojaControl.unidad_id == u.id))
    return h, (list(ctx.db.scalars(select(TramiteHoja).where(TramiteHoja.hoja_id == h.id).order_by(TramiteHoja.orden))) if h else [])


def _ocr(ctx, u: UnidadDocumental, tipos: list[str]):
    from arca.modulos.m13_ocr import propuestas  # noqa: PLC0415
    from arca.modulos.m13_ocr.servicios import textos  # noqa: PLC0415

    lista = textos(ctx, u)
    if not lista or any(p["estado"] == "pendiente" for p in lista):
        return None
    return propuestas.proponer(lista, tipos)


def calcular(ctx, proyecto: Proyecto, u: UnidadDocumental, procesos: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, str]], list[str]]:
    """Los valores que se deducen, cada uno con su origen, y los avisos de lo que falta para describir bien."""
    v: dict[str, Any] = {}
    o: dict[str, dict[str, str]] = {}
    avisos: list[str] = []
    c = _clasificacion(ctx, u)
    h, tramites = _hoja(ctx, u)
    pags = paginas(ctx, u)
    fuid = "FUID del proyecto"
    if c is None:
        avisos.append("la unidad no tiene clasificación confirmada: no se puede calcular el código, el productor ni la valoración")
    codigo = c["e"].codigo if c else (u.codigo_serie or "SS")
    v["codigo_referencia"] = f"CO.{proyecto.codigo}.{codigo}.{u.identificador}"
    o["codigo_referencia"] = _origen("calculado", "país, código del proyecto, código de la serie o subserie según la clasificación e identificador de la unidad")
    v["nivel"], o["nivel"] = "Expediente", _origen("calculado", "unidad documental compuesta del inventario")
    usa_hoja = procesos["hoja_control"] and h is not None and h.estado == "verificada"
    if procesos["hoja_control"] and not usa_hoja:
        avisos.append("el lote lleva hoja de control y la de esta unidad no está verificada: la descripción se recalculará cuando lo esté")
    docs = None if usa_hoja else _ocr(ctx, u, list(c["e"].tipos_documentales or []) if c else [])
    # Fechas extremas.
    if usa_hoja:
        fechas = sorted(t.fecha_texto for t in tramites if t.fecha_texto)
        if fechas:
            v["fecha_inicial"], v["fecha_final"] = fechas[0], fechas[-1]
            o["fecha_inicial"] = o["fecha_final"] = _origen("hoja_control", f"de la hoja de control verificada ({len(tramites)} trámites, {sum(1 for t in tramites if not t.fecha_texto)} sin fecha)")
    elif docs:
        fechas = sorted(d.fecha for d in docs if d.fecha)
        if fechas:
            v["fecha_inicial"], v["fecha_final"] = fechas[0], fechas[-1]
            o["fecha_inicial"] = o["fecha_final"] = _origen("ocr", f"de las fechas que el OCR reconoció en {len(docs)} documentos: revíselas")
    if "fecha_inicial" not in v:
        v["fecha_inicial"] = u.fecha_inicial.isoformat() if u.fecha_inicial else ""
        v["fecha_final"] = u.fecha_final.isoformat() if u.fecha_final else ""
        o["fecha_inicial"] = o["fecha_final"] = _origen("fuid", fuid)
    # Volumen y soporte.
    folios = h.total_folios if usa_hoja and h.total_folios else u.folios
    partes = []
    if folios:
        metros = motor.metros_lineales(folios)
        partes.append(f"{folios} folios en papel" + (f" ({str(metros).replace('.', ',')} metros lineales)" if metros else ""))
    if pags:
        partes.append(f"{len(pags)} imágenes digitales")
    v["volumen"] = "; ".join(partes)
    o["volumen"] = _origen("calculado", ("folios contados en la hoja de control verificada" if usa_hoja else "folios del FUID") + (" e imágenes cargadas en ARCA" if pags else ""))
    if c:
        v["productor"] = motor._productor(proyecto.entidad_cliente, c["dependencia"])
        o["productor"] = _origen("clasificacion", f"entidad del proyecto y dependencia {c['e'].codigo_dependencia} según la {c['fuente']}")
        retencion = f" Retención: {c['e'].retencion_gestion} años en archivo de gestión y {c['e'].retencion_central} en archivo central." if c["e"].retencion_gestion is not None else ""
        v["valoracion"] = f"{motor.leer_disposicion(c['e'].disposicion or '')} según la {c['fuente']}, {c['e'].nivel} {c['e'].codigo} {c['e'].nombre}.{retencion}"
        if c["e"].procedimiento:
            v["valoracion"] += f" {c['e'].procedimiento.rstrip('.')}."
        o["valoracion"] = _origen("trd", f"disposición final y retención de la {c['fuente']}; no se deduce ni se inventa")
        v["acceso"] = ACCESO.get(c["e"].acceso or "publica", c["e"].acceso)
        o["acceso"] = _origen("trd", f"acceso según la {c['fuente']}")
    # Historia archivística y forma de ingreso: la caja y los movimientos registrados en ARCA.
    movs = list(ctx.db.scalars(select(MovimientoFase).where(MovimientoFase.unidad_id == u.id).order_by(MovimientoFase.creado_en)))
    traza = [f"Unidad de la caja {u.caja}, carpeta {u.carpeta}" if u.caja else ""] + [f"{m.motivo or 'cambio de fase'} ({FASES.get(m.hasta, m.hasta).lower()}, {m.creado_en.date().isoformat()})" for m in movs]
    v["historia_archivistica"] = "; ".join(x for x in traza if x) + "."
    o["historia_archivistica"] = _origen("calculado", "caja y carpeta del FUID y movimientos de fase registrados en ARCA")
    if any(m.hasta == "historico" for m in movs):
        v["forma_ingreso"], o["forma_ingreso"] = "Transferencia secundaria", _origen("calculado", "transferencia secundaria recibida en ARCA")
    # Organización, instrumentos, copias, lengua y reglas.
    n_docs = len(tramites) if usa_hoja else (len(docs) if docs else None)
    v["organizacion"] = f"Ordenación cronológica de los documentos{f' ({n_docs})' if n_docs else ''}" + (f", con foliación continua de {folios} folios." if folios else ".")
    o["organizacion"] = _origen("calculado", "orden de la hoja de control verificada" if usa_hoja else "orden de las páginas digitalizadas")
    instrumentos = ["Formato único de inventario documental (FUID)"] + (["hoja de control verificada"] if usa_hoja else []) + (["base de descripción ISAD(G)"])
    v["instrumentos"], o["instrumentos"] = "; ".join(instrumentos) + ".", _origen("calculado", "instrumentos que existen en ARCA para la unidad")
    if pags:
        v["copias"] = f"Copia digital en ARCA: {len(pags)} imágenes en {len({p['recurso_id'] for p in pags})} archivos, con huella SHA-256 verificada."
        o["copias"] = _origen("digitalizacion", "archivos digitalizados asociados a la unidad")
    v["lengua"], o["lengua"] = motor.LENGUA, _origen("calculado", "valor por defecto del proyecto: cámbielo si el expediente tiene documentos en otra lengua")
    v["reglas"], o["reglas"] = motor.REGLAS, _origen("calculado", "norma con la que se describe en ARCA")
    # Propuestas: título y alcance (las escribe o confirma una persona).
    base_tramites = tramites if usa_hoja else [type("T", (), {"tipo_documental": d.tipo})() for d in (docs or [])]
    if base_tramites:
        naturaleza, _ = motor.naturaleza_predominante(base_tramites)
        dep = c["dependencia"] if c else ""
        titulo = (naturaleza[:1].upper() + naturaleza[1:]) if naturaleza else (c["e"].nombre if c else u.nombre)
        if dep:
            titulo += f" de {motor._con_articulo(dep)}"
        if v.get("fecha_inicial"):
            anios = sorted({v['fecha_inicial'][:4], (v.get('fecha_final') or v['fecha_inicial'])[:4]})
            titulo += f", {'–'.join(anios)}"
        v["titulo"] = titulo
        o["titulo"] = _origen("propuesta", "propuesto desde el tipo documental que predomina " + ("en la hoja de control" if usa_hoja else "en lo que leyó el OCR")
                              + " y la dependencia: escríbalo para que identifique ESTA unidad, o confírmelo")
        tipos: list[str] = []
        for t in base_tramites:
            if t.tipo_documental and t.tipo_documental.lower() not in [x.lower() for x in tipos]:
                tipos.append(t.tipo_documental)
        detalles = [t.detalle for t in tramites if getattr(t, "detalle", "")][:5] if usa_hoja else [d.detalle for d in (docs or []) if d.detalle][:5]
        alcance = f"La unidad reúne {len(base_tramites)} documentos: {'; '.join(tipos[:12])}."
        if detalles:
            alcance += " Entre ellos: " + "; ".join(detalles) + "."
        metas = [getattr(t, "metadatos", None) or {} for t in tramites] if usa_hoja else [d.metadatos for d in (docs or [])]
        for clave, rotulo in (("remitente", "Remitentes"), ("destinatario", "Destinatarios"), ("firmantes", "Firman")):
            valores = list(dict.fromkeys(m[clave] for m in metas if m.get(clave)))[:6]
            if valores:
                alcance += f" {rotulo}: {'; '.join(valores)}."
        v["alcance"] = alcance
        o["alcance"] = _origen("propuesta", ("propuesto desde los trámites de la hoja de control verificada" if usa_hoja else "propuesto desde los documentos que reconoció el OCR")
                               + ": agregue los asuntos y los vacíos que encontró, o confírmelo")
    else:
        avisos.append("no hay hoja de control verificada ni OCR completo: el título y el alcance se escriben a mano")
    return v, o, avisos


# --- Descripción ---------------------------------------------------------------------------------


def unidad_de(ctx, proyecto: Proyecto, unidad_id: uuid.UUID) -> UnidadDocumental:
    u = ctx.db.get(UnidadDocumental, unidad_id)
    if u is None or u.proyecto_id != proyecto.id:
        raise NoEncontrado("La unidad no existe en el proyecto")
    return u


def descripcion_de(ctx, u: UnidadDocumental) -> DescripcionUnidad | None:
    return ctx.db.scalar(select(DescripcionUnidad).where(DescripcionUnidad.unidad_id == u.id))


def crear(ctx, proyecto: Proyecto, u: UnidadDocumental) -> DescripcionUnidad:
    _abierto(proyecto)
    procesos = procesos_de(ctx, proyecto, u)
    if not procesos["isadg"]:
        raise TransicionInvalida(f"La unidad no lleva descripción ISAD(G) según la {procesos['origen']}. Cámbielo en la configuración por lote")
    if not paginas(ctx, u):
        raise TransicionInvalida("La descripción se hace sobre lo digitalizado: la unidad no tiene imágenes")
    if descripcion_de(ctx, u):
        raise Conflicto("La unidad ya tiene descripción")
    valores, origen, _ = calcular(ctx, proyecto, u, procesos)
    d = DescripcionUnidad(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, unidad_id=u.id, estado="borrador", campos={k: valores.get(k, "") for k in CLAVES},
                          origen=origen, creado_en=ahora_utc(), creado_por=ctx.usuario.id)
    ctx.db.add(d)
    ctx.db.flush()
    ctx.auditar(accion="CREAR_DESCRIPCION", objeto="DescripcionUnidad", objeto_id=d.id, detalle=f"{proyecto.codigo} · {u.identificador}")
    ctx.db.commit()
    return d


def _editable(d: DescripcionUnidad) -> None:
    if d.estado not in ESTADOS_EDITABLES:
        raise TransicionInvalida("La descripción solo se edita en borrador o cuando la devuelven")


def recalcular(ctx, proyecto: Proyecto, u: UnidadDocumental, d: DescripcionUnidad) -> DescripcionUnidad:
    """Vuelve a calcular lo deducido (por ejemplo, cuando se verificó la hoja). Lo que escribió o confirmó una persona no se toca."""
    _abierto(proyecto)
    _editable(d)
    valores, origen, _ = calcular(ctx, proyecto, u, procesos_de(ctx, proyecto, u))
    campos, orig = dict(d.campos), dict(d.origen)
    for k in CLAVES:
        if (orig.get(k) or {}).get("fuente") == "persona":
            continue
        if k in valores:
            campos[k], orig[k] = valores[k], origen[k]
    d.campos, d.origen = campos, orig
    ctx.db.commit()
    return d


def editar(ctx, proyecto: Proyecto, d: DescripcionUnidad, cambios: dict[str, str]) -> DescripcionUnidad:
    _abierto(proyecto)
    _editable(d)
    campos, orig = dict(d.campos), dict(d.origen)
    for k, valor in cambios.items():
        if k not in EDITABLES:
            raise DatosInvalidos(f"El elemento «{k}» no se edita: se calcula o se hereda de la TRD")
        campos[k] = str(valor or "").strip()
        orig[k] = _origen("persona", f"escrito por {ctx.usuario.nombre_completo}")
    d.campos, d.origen = campos, orig
    ctx.db.commit()
    return d


def confirmar(ctx, proyecto: Proyecto, d: DescripcionUnidad, elemento: str) -> DescripcionUnidad:
    _abierto(proyecto)
    _editable(d)
    o = (d.origen or {}).get(elemento)
    if not o or o.get("fuente") not in ("propuesta", "ocr"):
        raise DatosInvalidos("Ese elemento no tiene una propuesta por confirmar")
    d.origen = {**d.origen, elemento: _origen("persona", f"confirmado por {ctx.usuario.nombre_completo} ({o['detalle']})")}
    ctx.db.commit()
    return d


class _Renglon(dict):
    """El renglón como lo espera la revisión del motor: por clave y con el nivel como atributo."""

    @property
    def nivel(self) -> str:
        return self.get("nivel", "Expediente")


def revisar(ctx, proyecto: Proyecto, u: UnidadDocumental, d: DescripcionUnidad) -> dict[str, Any]:
    """Las reglas de revisión del motor (DEVUELVE bloquea; REVISE se mira) y las propuestas sin confirmar."""
    c = _clasificacion(ctx, u)
    h, tramites = _hoja(ctx, u)
    contexto: dict[str, Any] = {"subserie": c["e"].nombre if c else ""}
    if h and h.estado == "verificada":
        fechas = sorted(t.fecha_texto for t in tramites if t.fecha_texto)
        if fechas:
            contexto["extremas_hoja"] = (fechas[0], fechas[-1])
        if h.total_folios and u.folios and h.total_folios != u.folios:
            contexto["diferencia_folios"] = f"La hoja de control suma {h.total_folios} folios y el FUID declara {u.folios}."
    r = _Renglon({**d.campos, "nivel": d.campos.get("nivel") or "Expediente"})
    hallazgos = revision.revisar([r], {d.campos.get("codigo_referencia"): contexto})
    pendientes = [k for k, o in (d.origen or {}).items() if o.get("fuente") in ("propuesta", "ocr")]
    return {"hallazgos": [{"gravedad": x.gravedad, "regla": x.regla, "que_pasa": x.que_pasa, "como_se_arregla": x.como_se_arregla} for x in hallazgos],
            "devuelve": sum(1 for x in hallazgos if x.gravedad == revision.DEVUELVE), "revise": sum(1 for x in hallazgos if x.gravedad == revision.REVISE),
            "por_confirmar": pendientes}


def enviar(ctx, proyecto: Proyecto, u: UnidadDocumental, d: DescripcionUnidad) -> DescripcionUnidad:
    _abierto(proyecto)
    _editable(d)
    r = revisar(ctx, proyecto, u, d)
    if r["por_confirmar"]:
        raise TransicionInvalida(f"Hay elementos propuestos sin confirmar: {', '.join(r['por_confirmar'])}")
    if r["devuelve"]:
        raise TransicionInvalida(f"La revisión encontró {r['devuelve']} incumplimientos de la norma: corríjalos antes de enviar")
    d.estado, d.enviada_en, d.enviada_por, d.observaciones = "en_revision", ahora_utc(), ctx.usuario.id, {}
    ctx.auditar(accion="ENVIAR_DESCRIPCION", objeto="DescripcionUnidad", objeto_id=d.id, detalle=f"{u.identificador} · {r['revise']} puntos para revisar")
    encolar_ctx(ctx, proyecto.id, d.unidad_id, "descripción enviada")
    ctx.db.commit()
    return d


def _aprobador(ctx, d: DescripcionUnidad) -> None:
    if d.estado != "en_revision":
        raise TransicionInvalida("La descripción no está en revisión")
    if ctx.usuario.id in (d.enviada_por, d.creado_por):
        raise AccesoDenegado("Quien elaboró la descripción no la aprueba (segregación de funciones)")


def aprobar(ctx, proyecto: Proyecto, u: UnidadDocumental, d: DescripcionUnidad) -> DescripcionUnidad:
    _abierto(proyecto)
    _aprobador(ctx, d)
    nombre = lambda uid: ctx.db.scalar(select(Usuario.nombre_completo).where(Usuario.id == uid)) or ""  # noqa: E731
    d.estado, d.aprobada_en, d.aprobada_por, d.novedad = "aprobada", ahora_utc(), ctx.usuario.id, ""
    d.campos = {**d.campos, "nota_archivero": f"Descripción elaborada por {nombre(d.enviada_por)} y revisada por {ctx.usuario.nombre_completo}.",
                "fecha_descripcion": date.today().isoformat()}
    ctx.auditar(accion="APROBAR_DESCRIPCION", objeto="DescripcionUnidad", objeto_id=d.id, detalle=u.identificador)
    encolar_ctx(ctx, proyecto.id, d.unidad_id, "descripción aprobada")
    ctx.db.commit()
    return d


def devolver(ctx, proyecto: Proyecto, u: UnidadDocumental, d: DescripcionUnidad, observaciones: dict[str, str], motivo: str) -> DescripcionUnidad:
    _abierto(proyecto)
    _aprobador(ctx, d)
    if len(motivo.strip()) < 5:
        raise DatosInvalidos("Escriba el motivo de la devolución")
    d.estado, d.novedad, d.observaciones = "devuelta", motivo.strip(), {k: v.strip() for k, v in observaciones.items() if k in CLAVES and v.strip()}
    ctx.auditar(accion="DEVOLVER_DESCRIPCION", objeto="DescripcionUnidad", objeto_id=d.id, motivo=motivo, detalle=f"{u.identificador} · {len(d.observaciones)} elementos observados")
    encolar_ctx(ctx, proyecto.id, d.unidad_id, "descripción devuelta")
    ctx.db.commit()
    return d


def reabrir(ctx, proyecto: Proyecto, d: DescripcionUnidad, motivo: str) -> DescripcionUnidad:
    _abierto(proyecto)
    if d.estado != "aprobada":
        raise TransicionInvalida("Solo se reabre una descripción aprobada")
    d.estado, d.novedad, d.aprobada_en, d.aprobada_por = "devuelta", motivo.strip(), None, None
    ctx.auditar(accion="REABRIR_DESCRIPCION", objeto="DescripcionUnidad", objeto_id=d.id, motivo=motivo)
    encolar_ctx(ctx, proyecto.id, d.unidad_id, "descripción reabierta")
    ctx.db.commit()
    return d


def bandeja(ctx, proyecto: Proyecto, estado: str | None, q: str | None, desplazamiento: int, limite: int) -> tuple[int, list[dict[str, Any]], dict[str, int]]:
    confs, mapa = configuraciones(ctx, proyecto), mapa_lotes(ctx, proyecto)
    descs = {d.unidad_id: d for d in ctx.db.scalars(select(DescripcionUnidad).where(DescripcionUnidad.proyecto_id == proyecto.id))}
    hojas = dict(ctx.db.execute(select(HojaControl.unidad_id, HojaControl.estado).where(HojaControl.proyecto_id == proyecto.id)).all())
    filas = []
    for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id)):
        pr = procesos_de(ctx, proyecto, u, confs, mapa)
        d = descs.get(u.id)
        estado_u = d.estado if d else ("sin_descripcion" if pr["isadg"] else "no_aplica")
        filas.append({"unidad_id": u.id, "identificador": u.identificador, "nombre": u.nombre, "caja": u.caja, "lote": pr["lote"], "estado": estado_u,
                      "titulo": (d.campos.get("titulo") if d else "") or "", "hoja_control": hojas.get(u.id) if pr["hoja_control"] else "no_aplica",
                      "fase": u.fase, "novedad": d.novedad if d else ""})
    cuenta = {k: sum(1 for f in filas if f["estado"] == k) for k in ("no_aplica", "sin_descripcion", "borrador", "en_revision", "devuelta", "aprobada")}
    if estado:
        filas = [f for f in filas if f["estado"] == estado]
    if q and (t := q.strip().lower()):
        filas = [f for f in filas if t in f"{f['identificador']} {f['nombre']} {f['titulo']} {f['caja'] or ''}".lower()]
    filas.sort(key=lambda f: (f["caja"] or "", f["identificador"]))
    return len(filas), filas[desplazamiento:desplazamiento + limite], cuenta


def expedir(ctx, proyecto: Proyecto):
    """La base de descripción ISAD(G) con todo lo aprobado, en la plantilla de la entidad."""
    aprobadas = list(ctx.db.execute(select(DescripcionUnidad, UnidadDocumental).join(UnidadDocumental, DescripcionUnidad.unidad_id == UnidadDocumental.id)
                                    .where(DescripcionUnidad.proyecto_id == proyecto.id, DescripcionUnidad.estado == "aprobada")).all())
    if not aprobadas:
        raise TransicionInvalida("No hay descripciones aprobadas para expedir")
    aprobadas.sort(key=lambda x: (x[1].caja or "", x[1].identificador))
    filas = [{**{k: d.campos.get(k, "") for k in CLAVES}, "identificador": u.identificador, "caja": u.caja, "carpeta": u.carpeta,
              "nota_archivero": d.campos.get("nota_archivero", ""), "fecha_descripcion": d.campos.get("fecha_descripcion", "")} for d, u in aprobadas]
    return entregables.expedir_filas(ctx, proyecto, "descripcion_isadg", {"total_unidades": len(filas)}, filas, f"Descripcion_ISADG_{proyecto.codigo}",
                                     {"descripcion_isadg": len(filas)})
