"""Paquete de entrega digital (D-40): lo que ARCA entrega para cargar en el SGDEA de la entidad.

ARCA no es un SGDEA (D-38): entrega el resultado. Un paquete es un ZIP con una carpeta por expediente:

- `expediente.pdf`: en **PDF/A-2b**, validado después de escrito (ver `pdfa.py`): las páginas en orden, derechas, con
  el texto reconocido por OCR debajo de la imagen (se puede buscar y copiar). Si el servidor no tiene OCR, solo con las
  imágenes. Si un expediente no se puede aprobar como PDF/A, va como PDF común y el informe dice por qué.
- `metadatos.json`: el FUID, la clasificación (con la TRD, el acceso, la disposición y la retención), la hoja de control
  verificada (cada documento con su tipo, fecha, folios, páginas y metadatos), la descripción ISAD(G) aprobada, la fase y
  los archivos originales con su huella.
- `hoja_control.csv`, si tiene hoja verificada.

Y en la raíz: `manifiesto.csv` (la huella SHA-256 de cada archivo del paquete), `originales.csv` (la huella de cada
original recibido), `pdfa.csv` (el resultado de la validación PDF/A de cada expediente), `pendientes.csv` (lo que no entró y por qué) y `LEAME.txt`.

Por defecto entra solo lo que está listo según lo que lleva su lote: hoja verificada si la lleva y descripción aprobada si
la lleva.
"""

import csv
import io
import json
import uuid
import zipfile
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select

from arca.modelos import (
    ArchivoDigital,
    CajaProyecto,
    ClasificacionUnidad,
    DescripcionUnidad,
    ElementoInstrumento,
    EstadoProyecto,
    HojaControl,
    Instrumento,
    PaqueteEntrega,
    Proyecto,
    RecursoDigital,
    Trabajo,
    TramiteHoja,
    UnidadDocumental,
    VersionInstrumento,
)
from arca.modelos.base import ahora_utc
from arca.modelos.transferencias import FASES
from arca.modulos.entrega import pdfa
from arca.modulos.inspeccion import servicios as inspeccion
from arca.modulos.m08_inventarios.fuid import clave_de
from arca.modulos.m08_inventarios.servicios import guardar_archivo
from arca.modulos.m10_digitalizacion.paginas import imagen_pagina, paginas
from arca.modulos.procesos.servicios import configuraciones, mapa_lotes, procesos_de
from arca.nucleo import almacen
from arca.nucleo.errores import DatosInvalidos, NoEncontrado, TransicionInvalida

MAX_UNIDADES = 500


def _abierto(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


def _seleccion(ctx, proyecto: Proyecto, cajas: list[str], lote: str, solo_listos: bool) -> tuple[list[UnidadDocumental], list[tuple[str, str]]]:
    unidades = list(ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id)))
    if cajas:
        buscadas = {clave_de(c) for c in cajas if c.strip()}
        unidades = [u for u in unidades if u.caja and clave_de(u.caja) in buscadas]
    mapa = mapa_lotes(ctx, proyecto)
    if lote:
        unidades = [u for u in unidades if u.caja and mapa.get(clave_de(u.caja), "") == lote]
    confs = configuraciones(ctx, proyecto)
    hojas = dict(ctx.db.execute(select(HojaControl.unidad_id, HojaControl.estado).where(HojaControl.proyecto_id == proyecto.id)).all())
    descs = dict(ctx.db.execute(select(DescripcionUnidad.unidad_id, DescripcionUnidad.estado).where(DescripcionUnidad.proyecto_id == proyecto.id)).all())
    con_imagenes = set(ctx.db.scalars(select(RecursoDigital.unidad_id).where(RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.unidad_id.is_not(None))))
    plan = inspeccion.plan_de(ctx, proyecto)
    inspeccionados = inspeccion.estado_lotes(ctx, proyecto) if plan and plan.exigir_para_entrega else None
    entran, fuera = [], []
    for u in sorted(unidades, key=lambda x: (x.caja or "", x.identificador)):
        if u.id not in con_imagenes:
            fuera.append((u.identificador, "sin digitalizar"))
            continue
        if solo_listos and inspeccionados is not None:
            lote_u = mapa.get(clave_de(u.caja or ""), "")
            ultima = inspeccionados.get(lote_u)
            if ultima is None or ultima.estado != "aceptada":
                fuera.append((u.identificador, f"el lote «{lote_u or 'sin lote'}» " + ("fue rechazado en la inspección de calidad" if ultima else "no ha pasado la inspección de calidad")))
                continue
        pr = procesos_de(ctx, proyecto, u, confs, mapa)
        if solo_listos and pr["hoja_control"] and hojas.get(u.id) != "verificada":
            fuera.append((u.identificador, "la hoja de control no está verificada"))
            continue
        if solo_listos and pr["isadg"] and descs.get(u.id) != "aprobada":
            fuera.append((u.identificador, "la descripción ISAD(G) no está aprobada"))
            continue
        entran.append(u)
    return entran, fuera


def solicitar(ctx, proyecto: Proyecto, cajas: list[str], lote: str, solo_listos: bool) -> PaqueteEntrega:
    """Registra el paquete y lo pone en la cola: se arma en segundo plano."""
    _abierto(proyecto)
    entran, fuera = _seleccion(ctx, proyecto, cajas, lote, solo_listos)
    if not entran:
        motivos: dict[str, int] = {}
        for _, m in fuera:
            motivos[m] = motivos.get(m, 0) + 1
        detalle = "; ".join(f"{n}: {m}" for m, n in sorted(motivos.items(), key=lambda x: -x[1])[:5])
        raise DatosInvalidos("No hay expedientes listos para entregar con ese filtro" + (f" ({len(fuera)} pendientes · {detalle})" if fuera else ""))
    if len(entran) > MAX_UNIDADES:
        raise DatosInvalidos(f"Son {len(entran)} expedientes: arme paquetes de hasta {MAX_UNIDADES} (por caja o por lote)")
    numero = (ctx.db.scalar(select(func.max(PaqueteEntrega.numero)).where(PaqueteEntrega.proyecto_id == proyecto.id)) or 0) + 1
    p = PaqueteEntrega(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, numero=numero, estado="en_cola", filtro={"cajas": cajas, "lote": lote, "solo_listos": solo_listos},
                       unidades=len(entran), pendientes=[{"identificador": i, "motivo": m} for i, m in fuera], creado_en=ahora_utc(), creado_por=ctx.usuario.id)
    ctx.db.add(p)
    ctx.db.flush()
    ctx.db.add(Trabajo(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, unidad_id=None, tipo="paquete", estado="pendiente", motivo=f"paquete de entrega n.º {numero}",
                       usuario_id=ctx.usuario.id, creado_en=ahora_utc(), parametros={"paquete_id": str(p.id)}))
    ctx.auditar(accion="SOLICITAR_PAQUETE", objeto="PaqueteEntrega", objeto_id=p.id, detalle=f"{proyecto.codigo} · n.º {numero} · {len(entran)} expedientes · {len(fuera)} pendientes")
    ctx.db.commit()
    return p


def _metadatos(ctx, proyecto: Proyecto, u: UnidadDocumental, pags: list[dict[str, Any]]) -> dict[str, Any]:
    c = ctx.db.scalar(select(ClasificacionUnidad).where(ClasificacionUnidad.unidad_id == u.id, ClasificacionUnidad.estado == "confirmada"))
    clas = None
    if c:
        e = ctx.db.get(ElementoInstrumento, c.elemento_id)
        v = ctx.db.get(VersionInstrumento, c.version_id)
        i = ctx.db.get(Instrumento, v.instrumento_id)
        clas = {"codigo": e.codigo, "nombre": e.nombre, "nivel": e.nivel, "serie": e.padre if e.nivel == "subserie" else e.codigo, "dependencia": e.codigo_dependencia,
                "instrumento": f"{i.tipo} {i.nombre}", "version": v.version, "acto_administrativo": v.acto_administrativo, "acceso": e.acceso,
                "disposicion": e.disposicion, "retencion_gestion": e.retencion_gestion, "retencion_central": e.retencion_central}
    h = ctx.db.scalar(select(HojaControl).where(HojaControl.unidad_id == u.id, HojaControl.estado == "verificada"))
    tramites = [{"orden": t.orden, "fecha": t.fecha_texto, "tipo_documental": t.tipo_documental, "detalle": t.detalle, "folio_desde": t.folio_desde, "folio_hasta": t.folio_hasta,
                 "pagina_desde": t.pagina_desde, "pagina_hasta": t.pagina_hasta, "no_radicado": t.no_radicado, "observaciones": t.observaciones, "metadatos": t.metadatos or {}}
                for t in ctx.db.scalars(select(TramiteHoja).where(TramiteHoja.hoja_id == h.id).order_by(TramiteHoja.orden))] if h else []
    d = ctx.db.scalar(select(DescripcionUnidad).where(DescripcionUnidad.unidad_id == u.id, DescripcionUnidad.estado == "aprobada"))
    originales = []
    for rid in dict.fromkeys(p["recurso_id"] for p in pags):
        r = ctx.db.get(RecursoDigital, rid)
        a = ctx.db.get(ArchivoDigital, r.archivo_id)
        originales.append({"archivo": r.ruta_original, "formato": a.formato, "paginas": r.paginas, "tamano": a.tamano, "sha256": a.sha256, "calidad": r.estado})
    caja = ctx.db.scalar(select(CajaProyecto).where(CajaProyecto.proyecto_id == proyecto.id, CajaProyecto.clave == clave_de(u.caja))) if u.caja else None
    return {
        "esquema": "ARCA · paquete de entrega v1", "generado_en": ahora_utc().isoformat(), "proyecto": {"codigo": proyecto.codigo, "nombre": proyecto.nombre, "entidad": proyecto.entidad_cliente},
        "unidad": {"identificador": u.identificador, "numero_orden": u.numero_orden, "nombre": u.nombre, "codigo_serie_fuid": u.codigo_serie,
                   "fecha_inicial": u.fecha_inicial.isoformat() if u.fecha_inicial else None, "fecha_final": u.fecha_final.isoformat() if u.fecha_final else None,
                   "caja": u.caja, "carpeta": u.carpeta, "tomo": u.tomo, "folios_inventario": u.folios, "soporte": u.soporte, "notas": u.notas,
                   "fase": FASES.get(u.fase, u.fase), "disposicion_aplicada": u.disposicion_aplicada, "lote": caja.lote if caja else ""},
        "clasificacion": clas,
        "hoja_control": None if not h else {"total_folios": h.total_folios, "imagenes_por_folio": h.imagenes_por_folio, "verificada_en": h.verificada_en.isoformat() if h.verificada_en else None, "documentos": tramites},
        "descripcion_isadg": d.campos if d else None,
        "digitalizacion": {"paginas": len(pags), "originales": originales},
    }


def _pdf(ctx, u: UnidadDocumental, pags: list[dict[str, Any]], meta: dict[str, Any]) -> tuple[pdfa.Resultado, bool]:
    """El PDF/A del expediente: con texto buscable si hay OCR; si no, solo las imágenes. Devuelve (resultado, con texto)."""
    import pikepdf  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    from arca.modulos.m13_ocr import lector  # noqa: PLC0415

    imagenes = [imagen_pagina(ctx, u, p["n"], ancho=2200) for p in pags]
    con_texto = lector.disponible() and "spa" in lector.idiomas()
    if con_texto:
        documento = pikepdf.Pdf.new()
        for img in imagenes:
            documento.pages.extend(pikepdf.open(io.BytesIO(lector.pdf_buscable(img))).pages)
    else:
        hojas = [Image.open(io.BytesIO(x)).convert("RGB") for x in imagenes]
        salida = io.BytesIO()
        hojas[0].save(salida, "PDF", resolution=200, save_all=True, append_images=hojas[1:])
        documento = pikepdf.open(io.BytesIO(salida.getvalue()))
    clas = meta.get("clasificacion") or {}
    titulo = f"{u.identificador} · {u.nombre}" if u.nombre else u.identificador
    asunto = " · ".join(x for x in (f"{clas.get('codigo')} {clas.get('nombre')}" if clas else "", meta["proyecto"]["nombre"]) if x)
    palabras = ", ".join(x for x in (clas.get("codigo", ""), u.caja and f"caja {u.caja}", u.carpeta and f"carpeta {u.carpeta}") if x)
    return pdfa.convertir(documento, titulo, asunto=asunto, autor=meta["proyecto"]["entidad"] or "", palabras=palabras), con_texto


def _csv(filas: list[list[Any]]) -> bytes:
    salida = io.StringIO()
    csv.writer(salida, delimiter=";").writerows(filas)
    return salida.getvalue().encode("utf-8-sig")


def generar(ctx, paquete: PaqueteEntrega) -> PaqueteEntrega:
    """Arma el ZIP (lo llama el trabajador). Lo guarda en el almacén con su huella."""
    proyecto = ctx.db.get(Proyecto, paquete.proyecto_id)
    f = paquete.filtro or {}
    entran, _ = _seleccion(ctx, proyecto, f.get("cajas") or [], f.get("lote") or "", f.get("solo_listos", True))
    buffer = io.BytesIO()
    manifiesto: list[list[Any]] = [["archivo", "bytes", "sha256"]]
    originales: list[list[Any]] = [["expediente", "archivo original", "formato", "páginas", "bytes", "sha256", "calidad"]]
    con_texto = True
    informe_pdfa: list[list[Any]] = [["expediente", "formato", "conforme", "validado con", "hallazgos"]]

    def agregar(z: zipfile.ZipFile, ruta: str, datos: bytes) -> None:
        z.writestr(ruta, datos)
        manifiesto.append([ruta, len(datos), almacen.huella(datos)])

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for u in entran:
            pags = paginas(ctx, u)
            carpeta = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in u.identificador)
            meta = _metadatos(ctx, proyecto, u, pags)
            pdf, texto = _pdf(ctx, u, pags, meta)
            con_texto = con_texto and texto
            meta["pdf"] = pdf.como_dict()
            informe_pdfa.append([u.identificador, meta["pdf"]["formato"], "sí" if pdf.conforme else "no", pdf.motor,
                                 " | ".join(f"{h['regla']}: {h['mensaje']}" for h in pdf.hallazgos)[:2000]])
            agregar(z, f"{carpeta}/expediente.pdf", pdf.contenido)
            agregar(z, f"{carpeta}/metadatos.json", json.dumps(meta, ensure_ascii=False, indent=2, default=str).encode("utf-8"))
            if meta["hoja_control"]:
                filas = [["n.º", "fecha", "tipo documental", "detalle", "folio desde", "folio hasta", "radicado", "asunto", "remitente", "destinatario", "observaciones"]]
                filas += [[t["orden"], t["fecha"] or "S. F.", t["tipo_documental"], t["detalle"], t["folio_desde"], t["folio_hasta"], t["no_radicado"] or "N/A",
                           t["metadatos"].get("asunto", ""), t["metadatos"].get("remitente", ""), t["metadatos"].get("destinatario", ""), t["observaciones"]] for t in meta["hoja_control"]["documentos"]]
                agregar(z, f"{carpeta}/hoja_control.csv", _csv(filas))
            for o in meta["digitalizacion"]["originales"]:
                originales.append([u.identificador, o["archivo"], o["formato"], o["paginas"], o["tamano"], o["sha256"], o["calidad"]])
        agregar(z, "originales.csv", _csv(originales))
        agregar(z, "pdfa.csv", _csv(informe_pdfa))
        agregar(z, "pendientes.csv", _csv([["expediente", "por qué no entró"]] + [[x["identificador"], x["motivo"]] for x in paquete.pendientes]))
        conformes = sum(1 for f in informe_pdfa[1:] if f[2] == "sí")
        leame = (f"Paquete de entrega n.º {paquete.numero} · {proyecto.codigo} · {proyecto.nombre}\nEntidad: {proyecto.entidad_cliente}\n"
                 f"Generado por ARCA el {date.today().isoformat()} · {len(entran)} expedientes\n\n"
                 f"Cada carpeta es un expediente: expediente.pdf ({pdfa.NOMBRE}, páginas en orden" + (", con texto buscable" if con_texto else "") + "), metadatos.json y, si la tiene, hoja_control.csv.\n"
                 f"pdfa.csv dice, por expediente, si el PDF quedó aprobado como {pdfa.NOMBRE} ({conformes} de {len(entran)}) y, si no, por qué.\n"
                 "manifiesto.csv trae la huella SHA-256 de cada archivo de este paquete; originales.csv, la de cada archivo original recibido.\n"
                 "pendientes.csv dice qué expedientes no entraron y por qué.\n")
        agregar(z, "LEAME.txt", leame.encode("utf-8"))
        z.writestr("manifiesto.csv", _csv(manifiesto))
    contenido = buffer.getvalue()
    archivo = guardar_archivo(ctx, proyecto, contenido, f"Entrega_{proyecto.codigo}_n{paquete.numero}_{datetime.now():%Y%m%d_%H%M}.zip", {"ZIP"})
    paquete.estado, paquete.archivo_id, paquete.unidades, paquete.terminado_en, paquete.error = "listo", archivo.id, len(entran), ahora_utc(), ""
    paquete.resumen = {"pdfa": {"nivel": pdfa.NOMBRE, "conformes": conformes, "total": len(entran)}, "con_texto": con_texto}
    ctx.auditar(accion="GENERAR_PAQUETE", objeto="PaqueteEntrega", objeto_id=paquete.id,
                detalle=f"{proyecto.codigo} · n.º {paquete.numero} · {len(entran)} expedientes · {conformes} en {pdfa.NOMBRE} · {len(contenido) // 1024} KB · SHA-256 {archivo.sha256[:16]}…")
    ctx.db.commit()
    return paquete


def listar(ctx, proyecto: Proyecto) -> list[dict[str, Any]]:
    salida = []
    for p in ctx.db.scalars(select(PaqueteEntrega).where(PaqueteEntrega.proyecto_id == proyecto.id).order_by(PaqueteEntrega.numero.desc())):
        a = ctx.db.get(ArchivoDigital, p.archivo_id) if p.archivo_id else None
        salida.append({"id": p.id, "numero": p.numero, "estado": p.estado, "filtro": p.filtro, "unidades": p.unidades, "pendientes": p.pendientes, "error": p.error, "resumen": p.resumen or {},
                       "creado_en": p.creado_en, "terminado_en": p.terminado_en, "nombre_archivo": a.nombre_original if a else None, "tamano": a.tamano if a else None,
                       "sha256": a.sha256 if a else None})
    return salida


def archivo(ctx, proyecto: Proyecto, paquete_id: uuid.UUID) -> tuple[bytes, ArchivoDigital]:
    p = ctx.db.get(PaqueteEntrega, paquete_id)
    if p is None or p.proyecto_id != proyecto.id or not p.archivo_id:
        raise NoEncontrado("El paquete no existe o todavía no está listo")
    a = ctx.db.get(ArchivoDigital, p.archivo_id)
    datos = almacen.leer(a.clave_almacen, ctx.tenant_id)
    if almacen.huella(datos) != a.sha256:
        raise TransicionInvalida("ALERTA DE INTEGRIDAD: el paquete no coincide con su huella")
    ctx.auditar(accion="DESCARGAR_PAQUETE", objeto="PaqueteEntrega", objeto_id=p.id, detalle=f"{proyecto.codigo} · n.º {p.numero}")
    ctx.db.commit()
    return datos, a

