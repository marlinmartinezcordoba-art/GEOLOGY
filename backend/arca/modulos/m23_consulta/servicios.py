"""M23 · Consulta: buscar en los expedientes de los proyectos a los que la persona tiene acceso.

Reglas (D-37):
- Se busca sin importar tildes ni mayúsculas, en los metadatos (FUID y clasificación), el texto leído por OCR, los
  trámites de la hoja de control VERIFICADA y la descripción ISAD(G) APROBADA. Lo que está en elaboración no se
  consulta: lo que se consulta es lo que ya se validó.
- Cada palabra buscada debe aparecer en la unidad (en cualquiera de sus fuentes). Entre comillas, la frase exacta.
- El acceso de la TRD manda (y en un proyecto de historias laborales, su configuración: acceso restringido aunque la TRD
  no lo marque): en una unidad clasificada o reservada, quien no tiene el permiso de consulta reservada
  ve los metadatos, pero no el contenido (ni las imágenes, ni el texto, ni los fragmentos), y la búsqueda no le
  revela coincidencias en ese contenido.
- Solo se consulta lo de los proyectos del alcance de la persona. Abrir una ficha queda en la auditoría.
"""

import io
import re
import unicodedata
import uuid
from datetime import date
from typing import Any

from sqlalchemy import and_, exists, func, or_, select

from arca.modelos import (
    ClasificacionUnidad,
    ConfigHistorias,
    DescripcionUnidad,
    ElementoInstrumento,
    EntradaIndice,
    HojaControl,
    IndiceUnidad,
    Instrumento,
    MovimientoFase,
    Proyecto,
    RecursoDigital,
    TextoPagina,
    TitularExpediente,
    TramiteHoja,
    UnidadDocumental,
    VersionInstrumento,
)
from arca.modelos.base import ahora_utc
from arca.modelos.transferencias import FASES
from arca.modulos.historias import servicios as historias
from arca.modulos.m04_instrumentos.clasificacion import calendario
from arca.modulos.m10_digitalizacion.paginas import NO_CUENTAN, paginas
from arca.nucleo.errores import AccesoDenegado, DatosInvalidos

RESERVADAS = ("clasificada", "reservada")
FUENTES = {"metadatos": "FUID y clasificación", "ocr": "Texto OCR", "hoja": "Hoja de control", "descripcion": "Descripción ISAD(G)"}
CAMPOS_DESCRIPCION = {"titulo": "3.1.2 Título", "alcance": "3.3.1 Alcance y contenido", "productor": "3.2.1 Productor", "historia_archivistica": "3.2.3 Historia archivística", "notas": "3.6.1 Notas"}


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, letra por letra: el resultado tiene la misma longitud que el texto (en NFC)."""
    salida = []
    for c in unicodedata.normalize("NFC", texto or ""):
        base = "".join(x for x in unicodedata.normalize("NFD", c) if not unicodedata.combining(x)) or " "
        salida.append(base[0].lower()[0])
    return "".join(salida)


def terminos(q: str) -> list[str]:
    """Las frases entre comillas y las palabras sueltas (de dos letras o más), normalizadas."""
    frases = [normalizar(f.strip()) for f in re.findall(r'"([^"]+)"', q or "") if f.strip()]
    resto = re.sub(r'"[^"]*"', " ", q or "")
    palabras = [normalizar(p) for p in re.split(r"\s+", resto) if len(p.strip(".,;:()")) >= 2]
    limpios = [re.sub(r"[%_\\]", "", t).strip(".,;:()") for t in frases + palabras]  # sin comodines de SQL
    return [t for t in limpios if len(t) >= 2][:12]


# --- El índice --------------------------------------------------------------------------------


def _clasificacion(ctx, unidad_id: uuid.UUID) -> dict[str, Any] | None:
    c = ctx.db.scalar(select(ClasificacionUnidad).where(ClasificacionUnidad.unidad_id == unidad_id, ClasificacionUnidad.estado == "confirmada"))
    if c is None:
        return None
    e = ctx.db.get(ElementoInstrumento, c.elemento_id)
    v = ctx.db.get(VersionInstrumento, c.version_id)
    i = ctx.db.get(Instrumento, v.instrumento_id)

    def nombre(nivel, codigo):
        return ctx.db.scalar(select(ElementoInstrumento.nombre).where(ElementoInstrumento.version_id == v.id, ElementoInstrumento.nivel == nivel, ElementoInstrumento.codigo == codigo)) or ""

    return {"e": e, "instrumento": f"{i.tipo} «{i.nombre}» v{v.version}", "dependencia": nombre("dependencia", e.codigo_dependencia),
            "serie": nombre("serie", e.padre) if e.nivel == "subserie" else e.nombre, "reservada": (e.acceso or "publica") in RESERVADAS}


def _firmas(ctx, proyecto: Proyecto) -> dict[uuid.UUID, str]:
    """Una firma por unidad que cambia cuando cambia cualquiera de sus fuentes."""
    pid = proyecto.id
    clas = dict(ctx.db.execute(select(ClasificacionUnidad.unidad_id, ClasificacionUnidad.id).where(ClasificacionUnidad.proyecto_id == pid, ClasificacionUnidad.estado == "confirmada")).all())
    ocr = {uid: f"{n}:{m}" for uid, n, m in ctx.db.execute(
        select(RecursoDigital.unidad_id, func.count(TextoPagina.id), func.max(TextoPagina.creado_en)).join(TextoPagina, TextoPagina.recurso_id == RecursoDigital.id)
        .where(RecursoDigital.proyecto_id == pid, RecursoDigital.estado.not_in(NO_CUENTAN)).group_by(RecursoDigital.unidad_id)).all()}
    hojas = {uid: f"{e}:{v}" for uid, e, v in ctx.db.execute(select(HojaControl.unidad_id, HojaControl.estado, HojaControl.verificada_en).where(HojaControl.proyecto_id == pid)).all()}
    descs = {uid: f"{e}:{a}" for uid, e, a in ctx.db.execute(select(DescripcionUnidad.unidad_id, DescripcionUnidad.estado, DescripcionUnidad.aprobada_en).where(DescripcionUnidad.proyecto_id == pid)).all()}
    titulares = dict(ctx.db.execute(select(TitularExpediente.unidad_id, TitularExpediente.actualizado_en).where(TitularExpediente.proyecto_id == pid)).all())
    conf = ctx.db.scalar(select(ConfigHistorias.actualizado_en).where(ConfigHistorias.proyecto_id == pid))  # el acceso restringido cambia el índice
    return {uid: f"{act}|{clas.get(uid)}|{ocr.get(uid)}|{hojas.get(uid)}|{descs.get(uid)}|{titulares.get(uid)}|{conf}"[:300]
            for uid, act in ctx.db.execute(select(UnidadDocumental.id, UnidadDocumental.actualizado_en).where(UnidadDocumental.proyecto_id == pid)).all()}


def _entrada(ctx, u: UnidadDocumental, fuente: str, referencia: str, texto: str, reservada: bool, pagina: int | None = None) -> None:
    texto = unicodedata.normalize("NFC", texto or "").strip()
    if texto:
        ctx.db.add(EntradaIndice(tenant_id=ctx.tenant_id, proyecto_id=u.proyecto_id, unidad_id=u.id, fuente=fuente, referencia=referencia[:200], pagina=pagina,
                                 reservada=reservada and fuente != "metadatos", texto=texto, normal=normalizar(texto)))


def indexar_unidad(ctx, u: UnidadDocumental) -> None:
    for vieja in ctx.db.scalars(select(EntradaIndice).where(EntradaIndice.unidad_id == u.id)):
        ctx.db.delete(vieja)
    c = _clasificacion(ctx, u.id)
    reservada = bool(c and c["reservada"]) or historias.restringida(ctx, u)
    meta = [u.identificador, u.nombre, u.codigo_serie, f"caja {u.caja}" if u.caja else "", f"carpeta {u.carpeta}" if u.carpeta else "", u.notas,
            u.fecha_inicial.isoformat() if u.fecha_inicial else "", u.fecha_final.isoformat() if u.fecha_final else ""]
    if c:
        meta += [c["e"].codigo, c["e"].nombre, c["serie"], c["e"].codigo_dependencia, c["dependencia"]]
    titular = ctx.db.scalar(select(TitularExpediente).where(TitularExpediente.unidad_id == u.id))
    if titular:  # historia laboral: se busca por el número de documento y el nombre de la persona
        meta += [f"{titular.tipo_documento} {titular.numero_documento}", titular.nombres, titular.cargo, titular.dependencia]
    _entrada(ctx, u, "metadatos", FUENTES["metadatos"], " · ".join(str(x) for x in meta if x), reservada)
    orden = {(p["recurso_id"], p["pagina_en_archivo"]): p["n"] for p in paginas(ctx, u)}
    if orden:
        for t in ctx.db.scalars(select(TextoPagina).where(TextoPagina.recurso_id.in_({k[0] for k in orden}), TextoPagina.estado == "leida")):
            n = orden.get((t.recurso_id, t.pagina))
            if n:
                _entrada(ctx, u, "ocr", f"página {n}", t.texto, reservada, n)
    h = ctx.db.scalar(select(HojaControl).where(HojaControl.unidad_id == u.id, HojaControl.estado == "verificada"))
    if h:
        for t in ctx.db.scalars(select(TramiteHoja).where(TramiteHoja.hoja_id == h.id).order_by(TramiteHoja.orden)):
            texto = " · ".join(x for x in (t.tipo_documental, t.detalle, t.fecha_texto or "S. F.", t.no_radicado, t.observaciones, *(t.metadatos or {}).values()) if x)
            _entrada(ctx, u, "hoja", f"trámite {t.orden} (folios {t.folio_desde}–{t.folio_hasta})", texto, reservada, t.pagina_desde)
    d = ctx.db.scalar(select(DescripcionUnidad).where(DescripcionUnidad.unidad_id == u.id, DescripcionUnidad.estado == "aprobada"))
    if d:
        for clave, etiqueta in CAMPOS_DESCRIPCION.items():
            _entrada(ctx, u, "descripcion", etiqueta, d.campos.get(clave, ""), reservada)


def sincronizar(ctx, proyecto: Proyecto, limite: int = 3000) -> dict[str, int]:
    """Reindexa las unidades cuyas fuentes cambiaron desde la última vez (hasta `limite` por llamada)."""
    firmas = _firmas(ctx, proyecto)
    actuales = {i.unidad_id: i for i in ctx.db.scalars(select(IndiceUnidad).where(IndiceUnidad.proyecto_id == proyecto.id))}
    cambiadas = [uid for uid, f in firmas.items() if actuales.get(uid) is None or actuales[uid].firma != f]
    for uid in cambiadas[:limite]:
        u = ctx.db.get(UnidadDocumental, uid)
        indexar_unidad(ctx, u)
        i = actuales.get(uid) or IndiceUnidad(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, unidad_id=uid, firma="")
        i.firma, i.actualizado_en = firmas[uid], ahora_utc()
        if uid not in actuales:
            ctx.db.add(i)
    if cambiadas:
        ctx.db.commit()
    return {"reindexadas": min(len(cambiadas), limite), "pendientes": max(0, len(cambiadas) - limite)}


# --- Buscar -----------------------------------------------------------------------------------


def proyectos_visibles(ctx) -> list[Proyecto]:
    consulta = select(Proyecto).where(Proyecto.tenant_id == ctx.tenant_id)
    if ctx.alcance_proyectos is not None:
        consulta = consulta.where(Proyecto.id.in_(ctx.alcance_proyectos))
    return list(ctx.db.scalars(consulta.order_by(Proyecto.codigo)))


def _fragmento(e: EntradaIndice, termino: str) -> str:
    i = e.normal.find(termino)
    if i < 0:
        return e.texto[:160]
    a, b = max(0, i - 70), min(len(e.texto), i + len(termino) + 90)
    return ("…" if a else "") + e.texto[a:b].replace("\n", " ") + ("…" if b < len(e.texto) else "")


def buscar(ctx, proyectos: list[Proyecto], f: dict[str, Any], desplazamiento: int, limite: int, ver_reservado: bool) -> dict[str, Any]:
    indice = {"reindexadas": 0, "pendientes": 0}
    for p in proyectos:
        r = sincronizar(ctx, p)
        indice["reindexadas"] += r["reindexadas"]
        indice["pendientes"] += r["pendientes"]
    U = UnidadDocumental  # noqa: N806
    clas = (select(ClasificacionUnidad.unidad_id.label("uid"), ElementoInstrumento.codigo.label("codigo"), ElementoInstrumento.nombre.label("nombre_clas"),
                   ElementoInstrumento.codigo_dependencia.label("dependencia"), ElementoInstrumento.acceso.label("acceso"))
            .join(ElementoInstrumento, ClasificacionUnidad.elemento_id == ElementoInstrumento.id).where(ClasificacionUnidad.estado == "confirmada").subquery())
    consulta = (select(U, Proyecto.codigo, clas.c.codigo, clas.c.nombre_clas, clas.c.dependencia, clas.c.acceso)
                .join(Proyecto, U.proyecto_id == Proyecto.id).outerjoin(clas, clas.c.uid == U.id).where(U.proyecto_id.in_([p.id for p in proyectos])))
    if f.get("codigo"):
        consulta = consulta.where(clas.c.codigo.like(f"{f['codigo'].strip()}%"))
    if f.get("dependencia"):
        consulta = consulta.where(clas.c.dependencia == f["dependencia"].strip())
    if f.get("caja"):
        consulta = consulta.where(func.lower(U.caja) == f["caja"].strip().lower())
    if f.get("fase"):
        consulta = consulta.where(U.fase == f["fase"])
    if f.get("desde"):
        consulta = consulta.where(or_(U.fecha_final.is_(None), U.fecha_final >= f["desde"]))
    if f.get("hasta"):
        consulta = consulta.where(or_(U.fecha_inicial.is_(None), U.fecha_inicial <= f["hasta"]))
    if f.get("digitalizadas"):
        consulta = consulta.where(exists(select(RecursoDigital.id).where(RecursoDigital.unidad_id == U.id, RecursoDigital.estado.not_in(NO_CUENTAN))))
    if f.get("con_hoja"):
        consulta = consulta.where(exists(select(HojaControl.id).where(HojaControl.unidad_id == U.id, HojaControl.estado == "verificada")))
    if f.get("descritas"):
        consulta = consulta.where(exists(select(DescripcionUnidad.id).where(DescripcionUnidad.unidad_id == U.id, DescripcionUnidad.estado == "aprobada")))
    fuentes = [x for x in (f.get("fuentes") or []) if x in FUENTES] or list(FUENTES)
    ts = terminos(f.get("q") or "")

    def condicion_entrada(t: str):
        c = and_(EntradaIndice.unidad_id == U.id, EntradaIndice.normal.like(f"%{t}%"), EntradaIndice.fuente.in_(fuentes))
        return c if ver_reservado else and_(c, EntradaIndice.reservada.is_(False))

    for t in ts:
        consulta = consulta.where(exists(select(EntradaIndice.id).where(condicion_entrada(t))))
    total = ctx.db.scalar(select(func.count()).select_from(consulta.subquery()))
    filas = ctx.db.execute(consulta.order_by(Proyecto.codigo, U.caja, U.identificador).offset(desplazamiento).limit(limite)).all()
    ids = [fila[0].id for fila in filas]
    coincidencias: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if ts and ids:
        c = and_(EntradaIndice.unidad_id.in_(ids), EntradaIndice.normal.like(f"%{ts[0]}%"), EntradaIndice.fuente.in_(fuentes))
        for e in ctx.db.scalars(select(EntradaIndice).where(c if ver_reservado else and_(c, EntradaIndice.reservada.is_(False))).limit(len(ids) * 6)):
            lista = coincidencias.setdefault(e.unidad_id, [])
            if len(lista) < 3:
                lista.append({"fuente": e.fuente, "donde": e.referencia, "pagina": e.pagina, "fragmento": _fragmento(e, ts[0])})
    imagenes: dict[uuid.UUID, int] = {}
    if ids:
        for uid, pags in ctx.db.execute(select(RecursoDigital.unidad_id, RecursoDigital.paginas).where(RecursoDigital.unidad_id.in_(ids), RecursoDigital.estado.not_in(NO_CUENTAN))):
            imagenes[uid] = imagenes.get(uid, 0) + max(1, pags or 1)
    titulos = dict(ctx.db.execute(select(DescripcionUnidad.unidad_id, DescripcionUnidad.campos).where(DescripcionUnidad.unidad_id.in_(ids), DescripcionUnidad.estado == "aprobada")).all()) if ids else {}
    hojas = set(ctx.db.scalars(select(HojaControl.unidad_id).where(HojaControl.unidad_id.in_(ids), HojaControl.estado == "verificada"))) if ids else set()
    resultado = []
    restringidas = historias.restringidas(ctx, [fila[0] for fila in filas])
    for u, proyecto_codigo, codigo, nombre_clas, dependencia, acceso in filas:
        reservada = (acceso or "publica") in RESERVADAS or u.id in restringidas
        if u.id in restringidas and (acceso or "publica") not in RESERVADAS:
            acceso = "restringida (historia laboral)"
        resultado.append({
            "unidad_id": u.id, "proyecto_id": u.proyecto_id, "proyecto": proyecto_codigo, "identificador": u.identificador, "nombre": u.nombre,
            "caja": u.caja, "carpeta": u.carpeta, "fecha_inicial": u.fecha_inicial, "fecha_final": u.fecha_final, "folios": u.folios, "fase": u.fase,
            "clasificacion": f"{codigo} {nombre_clas}" if codigo else None, "dependencia": dependencia, "acceso": acceso or "publica", "reservada": reservada,
            "contenido_visible": ver_reservado or not reservada, "imagenes": imagenes.get(u.id, 0), "hoja_verificada": u.id in hojas,
            "titulo": (titulos.get(u.id) or {}).get("titulo"), "coincidencias": coincidencias.get(u.id, []),
        })
    return {"total": total, "filas": resultado, "terminos": ts, "indice": indice}


# --- Ficha ------------------------------------------------------------------------------------


def ficha(ctx, proyecto: Proyecto, u: UnidadDocumental, ver_reservado: bool) -> dict[str, Any]:
    c = _clasificacion(ctx, u.id)
    reservada = bool(c and c["reservada"]) or historias.restringida(ctx, u)
    visible = ver_reservado or not reservada
    cal = calendario(u, c["e"]) if c else None
    movs = [{"desde": FASES.get(m.desde or "", None), "hasta": FASES.get(m.hasta, m.hasta), "motivo": m.motivo, "fecha": m.creado_en}
            for m in ctx.db.scalars(select(MovimientoFase).where(MovimientoFase.unidad_id == u.id).order_by(MovimientoFase.creado_en))]
    h = ctx.db.scalar(select(HojaControl).where(HojaControl.unidad_id == u.id, HojaControl.estado == "verificada"))
    tramites = [{"orden": t.orden, "fecha": t.fecha_texto, "tipo_documental": t.tipo_documental, "detalle": t.detalle, "folio_desde": t.folio_desde, "folio_hasta": t.folio_hasta,
                 "pagina_desde": t.pagina_desde, "no_radicado": t.no_radicado, "observaciones": t.observaciones}
                for t in ctx.db.scalars(select(TramiteHoja).where(TramiteHoja.hoja_id == h.id).order_by(TramiteHoja.orden))] if h and visible else []
    d = ctx.db.scalar(select(DescripcionUnidad).where(DescripcionUnidad.unidad_id == u.id, DescripcionUnidad.estado == "aprobada"))
    pags = paginas(ctx, u) if visible else []
    ctx.auditar(accion="CONSULTAR_UNIDAD", objeto="UnidadDocumental", objeto_id=u.id,
                detalle=f"{proyecto.codigo} · {u.identificador}" + (" · solo metadatos (acceso reservado)" if not visible else ""))
    ctx.db.commit()
    return {
        "proyecto": {"id": proyecto.id, "codigo": proyecto.codigo, "nombre": proyecto.nombre, "entidad": proyecto.entidad_cliente},
        "unidad": {"id": u.id, "identificador": u.identificador, "numero_orden": u.numero_orden, "nombre": u.nombre, "codigo_serie": u.codigo_serie,
                   "fecha_inicial": u.fecha_inicial, "fecha_final": u.fecha_final, "caja": u.caja, "carpeta": u.carpeta, "tomo": u.tomo, "folios": u.folios,
                   "soporte": u.soporte, "notas": u.notas, "fase": u.fase, "fase_nombre": FASES.get(u.fase, u.fase), "disposicion_aplicada": u.disposicion_aplicada},
        "clasificacion": None if not c else {"codigo": c["e"].codigo, "nombre": c["e"].nombre, "nivel": c["e"].nivel, "serie": c["serie"], "dependencia": f"{c['e'].codigo_dependencia} {c['dependencia']}".strip(),
                                             "instrumento": c["instrumento"], "acceso": c["e"].acceso or "publica", "disposicion": cal["disposicion"] if cal else None,
                                             "calendario": cal},
        "reservada": reservada, "contenido_visible": visible, "historial": movs,
        "hoja_control": {"verificada": h is not None, "total_folios": h.total_folios if h else None, "tramites": tramites},
        "descripcion": {k: d.campos.get(k) for k in ("codigo_referencia", "titulo", "fecha_inicial", "fecha_final", "nivel", "volumen", "productor", "historia_archivistica",
                                                    "alcance", "valoracion", "organizacion", "acceso", "notas", "nota_archivero", "fecha_descripcion")} if d else None,
        "paginas": [{"n": p["n"], "archivo": p["archivo"], "pagina_en_archivo": p["pagina_en_archivo"]} for p in pags],
    }


def exigir_contenido(ctx, u: UnidadDocumental, ver_reservado: bool) -> None:
    c = _clasificacion(ctx, u.id)
    if ((c and c["reservada"]) or historias.restringida(ctx, u)) and not ver_reservado:
        raise AccesoDenegado("Esta unidad tiene acceso clasificado o reservado según la TRD: su rol solo puede ver los metadatos")


def exportar(ctx, proyectos: list[Proyecto], f: dict[str, Any], ver_reservado: bool) -> bytes:
    """Los resultados de la búsqueda en Excel (hasta 5.000), con los filtros usados."""
    import openpyxl  # noqa: PLC0415

    r = buscar(ctx, proyectos, f, 0, 5000, ver_reservado)
    libro = openpyxl.Workbook()
    h = libro.active
    h.title = "Resultados"
    h.append(["Consulta en ARCA", date.today().isoformat()])
    h.append(["Filtros", "; ".join(f"{k}: {v}" for k, v in f.items() if v not in (None, "", [], False))])
    h.append(["Resultados", r["total"]])
    h.append([])
    h.append(["Proyecto", "Identificador", "Nombre", "Clasificación", "Dependencia", "Fecha inicial", "Fecha final", "Caja", "Carpeta", "Folios", "Fase", "Imágenes",
              "Hoja verificada", "Título ISAD(G)", "Acceso", "Dónde aparece"])
    for x in r["filas"]:
        h.append([x["proyecto"], x["identificador"], x["nombre"], x["clasificacion"], x["dependencia"], x["fecha_inicial"], x["fecha_final"], x["caja"], x["carpeta"], x["folios"],
                  FASES.get(x["fase"], x["fase"]), x["imagenes"], "Sí" if x["hoja_verificada"] else "No", x["titulo"], x["acceso"],
                  "; ".join(f"{FUENTES[c['fuente']]} · {c['donde']}" for c in x["coincidencias"])])
    salida = io.BytesIO()
    libro.save(salida)
    ctx.auditar(accion="EXPORTAR_CONSULTA", objeto="Organizacion", objeto_id=ctx.tenant_id, detalle=f"{r['total']} resultados · términos: {' '.join(r['terminos']) or '—'}")
    ctx.db.commit()
    return salida.getvalue()


def validar_filtros(f: dict[str, Any]) -> None:
    if f.get("fase") and f["fase"] not in FASES:
        raise DatosInvalidos("Fase desconocida")
    if f.get("desde") and f.get("hasta") and f["hasta"] < f["desde"]:
        raise DatosInvalidos("La fecha final del rango es anterior a la inicial")
