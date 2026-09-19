"""
Descarga de los instrumentos archivísticos en Excel.

El inventario sale sobre la plantilla oficial F-GDM-003 versión 9 del Servicio Geológico.
La base de descripción sale con las 44 columnas de la plantilla del contrato. Las hojas de
control salen en un libro con una pestaña por expediente.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from geology.nucleo.bd import obtener_sesion
from geology.modelos import Caja, Expediente, Periodo, Seccion, Serie, Subserie
from geology.rutas.cuentas import usuario_actual
from geology.dominio import formatos_sgc as fmt
from geology.dominio import hojas_calculo as ins
from geology.dominio.estados import Estado, Usuario

router = APIRouter(prefix="/instrumentos", tags=["Instrumentos"])

EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

COLUMNAS_ISADG = [
    ("3.1.1", "Código de referencia"), ("3.1.2", "Título"),
    ("3.1.3", "Fecha inicial"), ("3.1.3", "Fecha final"),
    ("3.1.4", "Nivel de descripción"), ("3.1.5", "Volumen. Unidades de conservación"),
    ("3.1.5", "Volumen. Soporte"), ("3.1.5", "Volumen. Folios"),
    ("3.1.5", "Volumen. Metros lineales"), ("3.2.1", "Nombre del productor"),
    ("3.2.1", "Periodo institucional"), ("3.2.2", "Historia institucional"),
    ("3.2.3", "Historia archivística"), ("3.2.4", "Forma de ingreso"),
    ("3.3.1", "Alcance y contenido"), ("3.3.2", "Valoración, selección y eliminación"),
    ("3.3.3", "Nuevos ingresos"), ("3.3.4", "Organización"),
    ("3.4.1", "Condiciones de acceso"), ("3.4.2", "Condiciones de reproducción"),
    ("3.4.3", "Lengua y escritura"), ("3.4.4", "Características físicas y requisitos técnicos"),
    ("3.4.5", "Instrumentos de descripción"),
    ("3.5.1", "Existencia y localización de los originales"),
    ("3.5.2", "Existencia y localización de copias"),
    ("3.5.3", "Unidades de descripción relacionadas"), ("3.5.4", "Nota de publicaciones"),
    ("3.6.1", "Notas"), ("3.7.1", "Profesional que elabora la descripción"),
    ("3.7.2", "Reglas o normas"), ("3.7.3", "Fecha de la descripción"),
    ("3.7.3", "Profesional que revisa"), ("3.7.3", "Estado de la descripción"),
    ("clas", "Código de dependencia"), ("clas", "Código de serie"),
    ("clas", "Código de subserie"), ("clas", "Nombre del expediente en la hoja de control"),
    ("ctrl", "Caja definitiva"), ("ctrl", "N.º de carpeta en la caja"),
    ("ctrl", "Archivo de origen"), ("ctrl", "Estado en GEOLOGY"),
]

CENTIMETROS_POR_CIEN_FOLIOS = 1.0


def _contexto(db: Session, exp: Expediente) -> dict:
    periodo = db.get(Periodo, exp.periodo_id) if exp.periodo_id else None
    sub = db.get(Subserie, exp.subserie_id) if exp.subserie_id else None
    serie = db.get(Serie, sub.serie_id) if sub else None
    seccion = db.get(Seccion, serie.seccion_id) if serie else None
    return {"periodo": periodo, "sub": sub, "serie": serie, "seccion": seccion}


def _expedientes(db: Session, estados: list[str], caja: str | None, periodo: str | None):
    consulta = db.query(Expediente).filter(Expediente.estado.in_(estados))
    if caja:
        consulta = consulta.filter(Expediente.caja_definitiva == caja.upper())
    if periodo:
        consulta = consulta.join(Periodo).filter(Periodo.numero_romano == periodo.upper())
    return consulta.order_by(Expediente.caja_definitiva, Expediente.consecutivo_en_caja,
                             Expediente.codigo_carpeta).all()


def datos_hoja_de_control(db: Session, exp: Expediente) -> dict:
    """Lo que la plantilla F-GDM-007 necesita de un expediente. Lo usan Instrumentos y Consulta."""
    c = _contexto(db, exp)
    return {
        "codigo_dependencia": c["seccion"].codigo_dependencia if c["seccion"] else "",
        "dependencia": c["seccion"].oficina_productora if c["seccion"] else "",
        "codigo_serie": c["serie"].codigo if c["serie"] else "",
        "serie": c["serie"].nombre if c["serie"] else "",
        "codigo_subserie": c["sub"].codigo if c["sub"] else "",
        "subserie": c["sub"].nombre if c["sub"] else "",
        "nombre_expediente": exp.titulo or "",
        # Campo 15: quien revisó la hoja. Quien la diligenció va en la bitácora.
        "reviso_hoja": exp.reviso_hoja or "",
        "fecha_revision": exp.fecha_revision,
        "responsable_hoja": exp.responsable_hoja or "",
        "fecha_diligenciamiento": exp.fecha_diligenciamiento,
        "tramites": [{"no_item": t.no_item, "fecha": t.fecha or t.fecha_texto,
                      "tipo_documental": t.tipo_documental, "folio_desde": t.folio_desde,
                      "folio_hasta": t.folio_hasta, "no_radicado": t.no_radicado,
                      "sistema_informacion": t.sistema_informacion,
                      "expediente_sgdea": t.expediente_sgdea,
                      "enlace_acceso": t.enlace_acceso,
                      "observaciones": t.observaciones} for t in exp.tramites],
    }


@router.get("/fuid", summary="Inventario de salida F-GDM-003 en Excel")
def fuid(caja: str | None = Query(None, description="Solo esta caja definitiva"),
         periodo: str | None = Query(None, description="Solo este periodo"),
         solo_inventariadas: bool = Query(True, description="Falso incluye también las aprobadas sin caja"),
         db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)):
    estados = ([Estado.EN_INVENTARIO.value] if solo_inventariadas
               else [Estado.EN_INVENTARIO.value, Estado.ARCHIVADO.value])
    expedientes = _expedientes(db, estados, caja, periodo)
    if not expedientes:
        raise HTTPException(404, "No hay expedientes que cumplan ese filtro. El inventario de "
                                 "salida solo incluye lo que ya está en caja definitiva.")

    filas = []
    primero = _contexto(db, expedientes[0])
    for i, exp in enumerate(expedientes, start=1):
        c = _contexto(db, exp)
        codigo = ".".join(x for x in (
            c["seccion"].codigo_dependencia if c["seccion"] else "",
            c["serie"].codigo if c["serie"] else "",
            c["sub"].codigo if c["sub"] else "") if x)
        nombre_serie = " / ".join(x for x in (
            c["serie"].nombre if c["serie"] else "",
            c["sub"].nombre if c["sub"] else "") if x)
        folios = exp.volumen_folios or 0
        filas.append({
            "orden": i, "codigo": codigo, "serie_subserie": nombre_serie,
            "unidad_documental": exp.titulo or "",
            "fecha_inicial": exp.fecha_inicial.isoformat() if exp.fecha_inicial else (exp.fechas_texto or "S/F"),
            "fecha_final": exp.fecha_final.isoformat() if exp.fecha_final else "",
            "soporte_fisico": "X",
            "caja": exp.caja_definitiva or "", "carpeta": exp.consecutivo_en_caja or "",
            "correlativo": exp.codigo_carpeta, "folios": folios,
            "publico": "X",
            # La columna de notas del F-GDM-003 lleva la referencia física y, cuando la hay,
            # la constancia de que los folios contados no son los que declaraba el inventario
            # de origen. La dirección del proyecto pidió que eso saliera también aquí y no
            # solo en la hoja de control.
            "notas": " ".join(x for x in (
                f"Código de referencia {exp.codigo_referencia or ''}.",
                f"Caja de origen {exp.caja_origen or '—'}.",
                exp.diferencia_folios or "") if x).strip(),
        })

    encabezado = {
        "entidad_remitente": "Hometic SAS",
        "entidad_productora": "Servicio Geológico Colombiano",
        "unidad_administrativa": primero["seccion"].unidad_administrativa if primero["seccion"] else "",
        "oficina_productora": primero["seccion"].oficina_productora if primero["seccion"] else "",
        "objeto": ("Inventario de salida del contrato 733 de 2026" +
                   (f", caja {caja.upper()}" if caja else "") +
                   (f", periodo {periodo.upper()}" if periodo else "")),
    }
    contenido = fmt.fuid(filas, encabezado)
    nombre = "F-GDM-003_inventario" + (f"_{caja.upper()}" if caja else "") + \
             (f"_periodo_{periodo.upper()}" if periodo else "") + f"_{date.today().isoformat()}.xlsx"
    return Response(contenido, media_type=EXCEL,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/base-isadg", summary="Base de descripción ISAD(G) en Excel")
def base_isadg(periodo: str | None = None, db: Session = Depends(obtener_sesion),
               quien: Usuario = Depends(usuario_actual)):
    estados = [Estado.DESCRIPCION_POR_VALIDAR.value, Estado.DESCRIPCION_VALIDADA.value,
               Estado.ARCHIVADO.value, Estado.EN_INVENTARIO.value]
    expedientes = _expedientes(db, estados, None, periodo)
    if not expedientes:
        raise HTTPException(404, "Todavía no hay descripciones para exportar.")

    filas = []
    for exp in expedientes:
        c = _contexto(db, exp)
        folios = exp.volumen_folios or 0
        filas.append({
            "Código de referencia": exp.codigo_referencia, "Título": exp.titulo,
            "Fecha inicial": exp.fecha_inicial.isoformat() if exp.fecha_inicial else "",
            "Fecha final": exp.fecha_final.isoformat() if exp.fecha_final else "",
            "Nivel de descripción": exp.nivel_descripcion,
            "Volumen. Unidades de conservación": 1,
            "Volumen. Soporte": exp.soporte, "Volumen. Folios": folios,
            "Volumen. Metros lineales": round(folios * CENTIMETROS_POR_CIEN_FOLIOS / 100 / 100, 4),
            "Nombre del productor": exp.nombre_productor,
            "Periodo institucional": c["periodo"].numero_romano if c["periodo"] else "",
            "Historia institucional": exp.historia_institucional,
            "Historia archivística": exp.historia_archivistica,
            "Forma de ingreso": exp.forma_ingreso,
            "Alcance y contenido": exp.alcance_contenido,
            "Valoración, selección y eliminación": exp.valoracion,
            "Nuevos ingresos": exp.nuevos_ingresos, "Organización": exp.organizacion,
            "Condiciones de acceso": exp.condiciones_acceso,
            "Condiciones de reproducción": exp.condiciones_reproduccion,
            "Lengua y escritura": exp.lengua,
            "Características físicas y requisitos técnicos": exp.caracteristicas_fisicas,
            "Instrumentos de descripción": exp.instrumentos_descripcion,
            "Existencia y localización de los originales": exp.existencia_originales,
            "Existencia y localización de copias": exp.existencia_copias,
            "Unidades de descripción relacionadas": exp.unidades_relacionadas,
            "Nota de publicaciones": exp.nota_publicaciones, "Notas": exp.notas,
            "Profesional que elabora la descripción": exp.describio,
            "Reglas o normas": exp.reglas_normas,
            "Fecha de la descripción": exp.fecha_descripcion.isoformat() if exp.fecha_descripcion else "",
            "Profesional que revisa": exp.aprobo,
            "Estado de la descripción": exp.estado,
            "Código de dependencia": c["seccion"].codigo_dependencia if c["seccion"] else "",
            "Código de serie": c["serie"].codigo if c["serie"] else "",
            "Código de subserie": c["sub"].codigo if c["sub"] else "",
            "Nombre del expediente en la hoja de control": exp.titulo,
            "Caja definitiva": exp.caja_definitiva,
            "N.º de carpeta en la caja": exp.consecutivo_en_caja,
            "Archivo de origen": exp.archivo_origen, "Estado en GEOLOGY": exp.estado,
        })
    contenido = ins.generar_base_isadg(filas, COLUMNAS_ISADG)
    nombre = f"BASE_ISADG{'_periodo_'+periodo.upper() if periodo else ''}_{date.today().isoformat()}.xlsx"
    return Response(contenido, media_type=EXCEL,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/base-isadg-plantilla",
            summary="Base de descripción ISAD(G) en la plantilla del proyecto")
def base_isadg_en_plantilla(solo_conservacion_total: bool = False,
                            incluir_por_validar: bool = False,
                            db: Session = Depends(obtener_sesion),
                            quien: Usuario = Depends(usuario_actual)):
    """
    La misma descripción, escrita DENTRO de la plantilla del proyecto y no en una hoja armada
    por el programa.

    La diferencia con /base-isadg no es cosmética. Aquí la descripción es multinivel: arranca
    en el fondo, baja a la sección —que en este fondo es el periodo institucional—, sigue por
    la subserie de la tabla convalidada y termina en la unidad documental, y cada renglón
    queda amarrado al de arriba. Eso es lo que pide la norma y lo que espera el Archivo
    General de la Nación en una transferencia secundaria; una lista de expedientes sin los
    niveles encima es un inventario, no una descripción archivística.

    incluir_por_validar     agrega las descripciones que todavía no han sido validadas. Sirve
                            para revisar cómo va quedando, NUNCA para entregar: el archivo
                            saldría con borradores dentro.
    """
    from geology.dominio import base_isadg as bi

    estados = ()
    if incluir_por_validar:
        estados = (Estado.DESCRIPCION_POR_VALIDAR.value, Estado.DESCRIPCION_VALIDADA.value,
                   Estado.ARCHIVADO.value, Estado.EN_INVENTARIO.value)
    try:
        renglones = bi.construir(db, solo_conservacion_total, estados)
    except bi.FaltaLaPlantilla as e:
        raise HTTPException(503, str(e))
    if not renglones:
        raise HTTPException(404, "Todavía no hay descripciones validadas para llevar a la "
                                 "base. Si quiere ver cómo va quedando, pida la misma "
                                 "descarga con incluir_por_validar.")

    # La revisión previa viaja dentro del archivo, y si hay incumplimiento de norma el
    # nombre lo dice: nadie puede entregar por error un archivo marcado NO_ENTREGABLE.
    from geology.dominio import revision_isadg as rv
    hallazgos = rv.revisar(renglones, rv.contexto_de(db, renglones))
    resumen = rv.resumen(hallazgos)

    from pathlib import Path as _P
    import tempfile
    with tempfile.TemporaryDirectory() as carpeta:
        archivo = bi.escribir(renglones, _P(carpeta) / "base.xlsx",
                              hallazgos=hallazgos, resumen_revision=resumen)
        contenido = archivo.read_bytes()
    marca = "" if resumen["se_puede_entregar"] else "_NO_ENTREGABLE"
    nombre = f"Base_Datos_ISADG_733_{date.today().isoformat()}{marca}.xlsx"
    return Response(contenido, media_type=EXCEL,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/hojas-de-control", summary="Hojas de control en el formato oficial F-GDM-007")
def hojas_de_control(caja: str | None = None, periodo: str | None = None, limite: int = Query(200, le=500),
                     db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)):
    estados = [e.value for e in Estado if e is not Estado.RETIRADO]
    expedientes = _expedientes(db, estados, caja, periodo)[:limite]
    if not expedientes:
        raise HTTPException(404, "No hay hojas de control que cumplan ese filtro.")
    hojas = {}
    for exp in expedientes:
        hojas[f"F-GDM-007_{exp.codigo_carpeta}.xlsx"] = fmt.hoja_de_control(datos_hoja_de_control(db, exp))

    # Cada hoja de control es un formato completo, con su encabezado y su logotipo. Por eso
    # se entregan como archivos separados dentro de un comprimido y no como pestañas de un
    # mismo libro: al copiarlas como pestañas se pierde el logotipo del Servicio Geológico.
    if len(hojas) == 1:
        nombre, contenido = next(iter(hojas.items()))
        return Response(contenido, media_type=EXCEL,
                        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
    return Response(fmt.paquete(hojas), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="HOJAS_DE_CONTROL_{date.today().isoformat()}.zip"'})


@router.get("/paquete-oficial",
            summary="Todo lo ya hecho, expedido en los formatos oficiales del Servicio Geológico")
def paquete_oficial(caja: str | None = Query(None, description="Solo esta caja definitiva"),
                    periodo: str | None = Query(None, description="Solo este periodo"),
                    limite: int = Query(300, le=1000, description="Cuántos expedientes"),
                    por_pagina: int = Query(4, description="Rótulos de carpeta por hoja oficio"),
                    db: Session = Depends(obtener_sesion),
                    quien: Usuario = Depends(usuario_actual)):
    """
    Vuelve a expedir, en las plantillas del Servicio Geológico, todo lo que ya está hecho.

    No hay que rehacer nada: los datos están en la base y los instrumentos se generan cuando
    se piden, así que lo que se diligenció con el formato anterior sale aquí en el formato
    oficial, con la misma información.

    Antes de armar el paquete se completa, en las hojas ya revisadas, quién las revisó: el
    campo 15 pasó a ser el responsable de la revisión y ese dato se toma de la bitácora.
    """
    from geology.dominio import expedir

    completados = expedir.completar_revisores(db)
    archivos = expedir.armar(db, caja, periodo, limite, por_pagina)
    if not archivos:
        raise HTTPException(404, "No hay nada que expedir todavía con ese filtro: se necesitan "
                                 "expedientes con hoja de control levantada.")
    nombre = ("FORMATOS_OFICIALES"
              + (f"_{caja.upper()}" if caja else "")
              + (f"_periodo_{periodo.upper()}" if periodo else "")
              + f"_{date.today().isoformat()}.zip")
    return Response(fmt.paquete(archivos), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{nombre}"',
        "X-Expedientes-Completados": str(completados)})


@router.get("/resumen", summary="Qué se puede descargar hoy")
def resumen(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    from sqlalchemy import func as f
    return {
        "en_inventario": db.query(Expediente).filter(
            Expediente.estado == Estado.EN_INVENTARIO.value).count(),
        "aprobadas_sin_caja": db.query(Expediente).filter(
            Expediente.estado == Estado.ARCHIVADO.value).count(),
        "con_descripcion": db.query(Expediente).filter(Expediente.codigo_referencia.isnot(None)).count(),
        "con_hoja_de_control": db.query(Expediente).filter(Expediente.volumen_folios.isnot(None)).count(),
        "cajas": [{"codigo": c.codigo, "periodo": c.periodo, "carpetas": c.total_carpetas,
                   "cerrada": c.cerrada} for c in db.query(Caja).order_by(Caja.codigo).all()],
        "periodos": [p for (p,) in db.query(Periodo.numero_romano).join(Seccion).join(Serie)
                       .join(Subserie).join(Expediente, Expediente.subserie_id == Subserie.id)
                       .distinct().all()],
    }
