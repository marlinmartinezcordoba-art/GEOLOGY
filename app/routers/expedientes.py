"""
Expedientes. El flujo de dos pasos de KUSTOS.

La diferencia de fondo con un pipeline automático es que aquí NADA se describe solo.
La carga verifica y se detiene (R40). La descripción nace cuando una persona pulsa
Generar ISAD(G), y la aprueba alguien distinto de quien la hizo (R47).

El estado vive en PostgreSQL, no en memoria, y cada movimiento deja huella en la bitácora.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import obtener_sesion
from app.models import Expediente, Periodo, Subserie, Tramite, Trazabilidad, UnidadInventario
from app.routers.usuarios import usuario_actual
from app.services import codigos as cod
from app.services.clasificacion import Encabezado, OpcionTvd
from app.services.estados import (Estado, Usuario, dias_en_papelera, fecha_de_purga,
                                  motivo_de_rechazo_de_carga)
from app.services.fechas import fecha_diligenciamiento_valida, fechas_extremas, normalizar_fecha
from app.services.folios import Tramite as TramiteCalculo, limpiar_observacion
from app.services.verificacion import Lectura, UnidadInventario as UnidadCalculo, verificar_hoja

router = APIRouter(prefix="/expedientes", tags=["Expedientes"])


# ---------------------------------------------------------------------------
# Lo que entra y lo que sale
# ---------------------------------------------------------------------------
class TramiteEntrada(BaseModel):
    no_item: int | None = None
    fecha: str | None = Field(default=None, description="Cualquier escritura; se normaliza a año-mes-día")
    tipo_documental: str = ""
    folio_desde: str | int | None = None
    folio_hasta: str | int | None = None
    no_radicado: str = ""
    sistema_informacion: str = ""
    expediente_sgdea: str = ""
    enlace_acceso: str = ""
    observaciones: str = ""
    fila: int | None = None


class HojaDeControl(BaseModel):
    """El cuerpo de una hoja de control F-GDM-007, venga del Excel o del editor."""
    codigo_carpeta: str = Field(examples=["AC-CP-00363"])
    archivo_origen: str = ""
    codigo_serie: str = ""
    serie: str = ""
    codigo_subserie: str = ""
    subserie: str = ""
    nombre_expediente: str = ""
    responsable: str = ""
    fecha_diligenciamiento: str = ""
    periodo_manual: str | None = Field(default=None, description="Solo para unidades sin fecha (R9)")
    tramites: list[TramiteEntrada]
    modo: str = Field(default="verificar", pattern="^(avance|verificar)$")


class MotivoEntrada(BaseModel):
    motivo: str = Field(min_length=10)


# ---------------------------------------------------------------------------
# Apoyos
# ---------------------------------------------------------------------------
def _huella(db: Session, exp: Expediente, nuevo: Estado, accion: str,
            quien: Usuario | None = None, motivo: str = "", errores: list[str] | None = None) -> None:
    db.add(Trazabilidad(expediente=exp, estado_anterior=exp.estado, estado_nuevo=nuevo.value,
                        accion=accion, usuario=quien.nombre if quien else None, motivo=motivo or None,
                        errores=json.dumps(errores, ensure_ascii=False) if errores else None))
    exp.estado = nuevo.value
    if quien:
        exp.responsable = quien.nombre


def _opciones_tvd(db: Session, romano: str) -> list[OpcionTvd]:
    """
    R22. La lista cerrada de subseries del periodo, tal como está en la tabla convalidada.

    Va con la oficina productora y su código de dependencia, porque un mismo periodo tiene
    varias oficinas y los códigos de serie y de subserie se repiten entre ellas. Sin ese dato
    dos filas distintas de la tabla parecen la misma y una de las dos desaparece de la lista.
    """
    from app.models import Seccion, Serie
    consulta = (db.query(Periodo.numero_romano, Serie.codigo, Serie.nombre, Subserie.codigo,
                         Subserie.nombre, Subserie.retencion_central_anios,
                         Subserie.disposicion_final, Seccion.codigo_dependencia,
                         Seccion.oficina_productora)
                  .select_from(Subserie).join(Serie, Subserie.serie_id == Serie.id)
                  .join(Seccion, Serie.seccion_id == Seccion.id)
                  .join(Periodo, Seccion.periodo_id == Periodo.id)
                  .filter(Periodo.numero_romano == romano.upper()))
    return [OpcionTvd(p, cs, s_, csu, su, ret, disp, dep or "", ofi or "")
            for p, cs, s_, csu, su, ret, disp, dep, ofi in consulta.all()]


def _documentos(db: Session, carpeta: str) -> dict:
    """
    Cuántos archivos digitalizados tiene la carpeta y cuántos están de verdad en el almacén.

    Un registro en la base no garantiza que el archivo esté: pudo cargarse antes de una
    reinstalación, o quedar a medias. Sin archivo el modelo no puede leer nada, y eso hay que
    decirlo antes de que alguien pulse un botón que no va a hacer nada.
    """
    from pathlib import Path

    from app.models import Archivo
    archivos = db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta).all()
    disponibles = [a for a in archivos if Path(a.ruta).exists()]
    faltantes = [a.nombre_original for a in archivos if not Path(a.ruta).exists()]
    return {"cargados": len(archivos), "disponibles": len(disponibles),
            "faltantes": faltantes, "se_puede_leer": bool(disponibles)}


def _rangos(db: Session) -> list:
    """Los rangos de los periodos, como están en la tabla convalidada."""
    from app.services.periodos import RangoPeriodo
    return [RangoPeriodo(p.numero_romano, p.fecha_inicio, p.fecha_fin)
            for p in db.query(Periodo).order_by(Periodo.orden).all()]


def _contexto_para_el_modelo(db: Session, exp: Expediente) -> dict:
    """Hechos ya verificados. El modelo redacta sobre esto y no decide ninguno."""
    from app.models import Seccion, Serie
    sub = db.get(Subserie, exp.subserie_id) if exp.subserie_id else None
    serie = db.get(Serie, sub.serie_id) if sub else None
    seccion = db.get(Seccion, serie.seccion_id) if serie else None
    periodo = db.get(Periodo, exp.periodo_id) if exp.periodo_id else None
    unidad = db.query(UnidadInventario).filter(
        UnidadInventario.codigo_carpeta == exp.codigo_carpeta).first()
    return {
        "codigo_carpeta": exp.codigo_carpeta,
        "periodo": periodo.numero_romano if periodo else "",
        "rango_periodo": periodo.rango_texto if periodo else "",
        "entidad_productora": periodo.entidad_productora if periodo else "",
        "oficina_productora": seccion.oficina_productora if seccion else "",
        "serie": serie.nombre if serie else "", "subserie": sub.nombre if sub else "",
        "fechas_extremas": exp.fechas_texto, "folios": exp.volumen_folios,
        "metros_lineales": exp.metros_lineales,
        "es_libro": exp.encuadernada, "encuadernacion_por": exp.encuadernacion_por,
        "nivel_descripcion": exp.nivel_descripcion, "soporte": exp.soporte,
        "forma_ingreso": exp.forma_ingreso,
        "historia_institucional": exp.historia_institucional,
        "historia_archivistica": exp.historia_archivistica,
        "nuevos_ingresos": exp.nuevos_ingresos,
        "condiciones_acceso": exp.condiciones_acceso,
        "condiciones_reproduccion": exp.condiciones_reproduccion,
        "lengua": exp.lengua, "caracteristicas_fisicas": exp.caracteristicas_fisicas,
        "instrumentos_descripcion": exp.instrumentos_descripcion,
        "existencia_originales": exp.existencia_originales,
        "existencia_copias": exp.existencia_copias,
        "unidades_relacionadas": exp.unidades_relacionadas,
        "notas": exp.notas, "nota_archivero": exp.nota_archivero,
        "reglas_normas": exp.reglas_normas,
        "fecha_descripcion": exp.fecha_descripcion.isoformat() if exp.fecha_descripcion else None,
        "responsable_hoja": exp.responsable_hoja,
        "asunto_inventario": (unidad.asunto or "") if unidad else "",
        "tramites": [{"no_item": t.no_item, "fecha": t.fecha_texto,
                      "tipo_documental": t.tipo_documental, "folio_desde": t.folio_desde,
                      "folio_hasta": t.folio_hasta, "observaciones": t.observaciones}
                     for t in exp.tramites],
    }


def _documento_del_expediente(db: Session, exp: Expediente) -> bytes | None:
    """La primera parte del expediente digitalizado, si está cargada y no es enorme."""
    from pathlib import Path

    from app.models import Archivo
    a = (db.query(Archivo).filter(Archivo.codigo_carpeta == exp.codigo_carpeta)
           .order_by(Archivo.fragmento).first())
    if not a or a.tamano_bytes > 30 * 1024 * 1024:
        return None
    ruta = Path(a.ruta)
    return ruta.read_bytes() if ruta.exists() else None


def _cargar(db: Session, codigo: str) -> Expediente:
    normalizado = cod.normalizar_codigo_carpeta(codigo) or codigo.upper()
    exp = db.query(Expediente).filter(Expediente.codigo_carpeta == normalizado).first()
    if not exp:
        raise HTTPException(404, f"La carpeta {normalizado} no está en KUSTOS.")
    return exp


def _ficha(exp: Expediente) -> dict:
    d = {"codigo_carpeta": exp.codigo_carpeta, "estado": exp.estado,
         "codigo_referencia": exp.codigo_referencia, "titulo": exp.titulo,
         "nombre_expediente": exp.nombre_expediente,
         "alcance_contenido": exp.alcance_contenido, "valoracion": exp.valoracion,
         "organizacion": exp.organizacion, "nombre_productor": exp.nombre_productor,
         "fechas_extremas": exp.fechas_texto, "folios": exp.volumen_folios,
         "diferencia_folios": exp.diferencia_folios,
        "metros_lineales": exp.metros_lineales,
        "es_libro": exp.encuadernada, "encuadernacion_por": exp.encuadernacion_por,
         "responsable": exp.responsable, "caja_origen": exp.caja_origen,
         "caja_trabajo": exp.caja_trabajo, "caja_definitiva": exp.caja_definitiva,
         "carpeta_nueva": exp.consecutivo_en_caja, "archivo_origen": exp.archivo_origen,
         "describio": exp.describio, "aprobo": exp.aprobo,
         "responsable_hoja": exp.responsable_hoja, "reviso_hoja": exp.reviso_hoja,
         "tramites": [{"no_item": t.no_item, "fecha": t.fecha_texto, "tipo_documental": t.tipo_documental,
                       "folio_desde": t.folio_desde, "folio_hasta": t.folio_hasta,
                       "no_radicado": t.no_radicado,
                       "observaciones": t.observaciones} for t in exp.tramites]}
    # Lo último que pasó, para poder decir en pantalla por qué se detuvo sin ir a la bitácora.
    d["documento"] = None      # lo llena el enrutador, que sí tiene la sesión abierta
    if exp.trazabilidad:
        ultima = exp.trazabilidad[-1]
        d["ultimo_movimiento"] = {"accion": ultima.accion, "motivo": ultima.motivo,
                                  "usuario": ultima.usuario,
                                  "fecha": ultima.fecha.isoformat(timespec="minutes")
                                  if ultima.fecha else None}
    if exp.estado == Estado.RETIRADO.value:
        d["retiro"] = {"motivo": exp.motivo_retiro, "dias_en_papelera": dias_en_papelera(exp),
                       "se_purga_el": str(fecha_de_purga(exp) or "")}
    return d


# ---------------------------------------------------------------------------
# Paso uno. Cargar y verificar. Aquí no se describe nada.
# ---------------------------------------------------------------------------
@router.post("/hoja-de-control", status_code=status.HTTP_200_OK,
             summary="Cargar o corregir una hoja de control, verificarla y detenerse")
def cargar_hoja(hoja: HojaDeControl, db: Session = Depends(obtener_sesion),
                quien: Usuario = Depends(usuario_actual)) -> dict:
    if not quien.edita_hoja_control:
        raise HTTPException(403, "Su perfil es de consulta y no edita hojas de control.")

    carpeta = cod.normalizar_codigo_carpeta(hoja.codigo_carpeta)
    if not carpeta:
        raise HTTPException(422, f"El código {hoja.codigo_carpeta!r} no tiene la forma AC-CP-#####.")

    # R3. La carpeta debe pertenecer a la selección inventariada.
    unidad = db.query(UnidadInventario).filter(UnidadInventario.codigo_carpeta == carpeta).first()
    if not unidad:
        raise HTTPException(422, f"La carpeta {carpeta} no está en el inventario de origen del "
                                 "contrato, es decir no pertenece a la selección inventariada.")

    exp = db.query(Expediente).filter(Expediente.codigo_carpeta == carpeta).first()

    # R44 y R45. No se carga dos veces ni se describe dos veces.
    if exp:
        from app.services.estados import Expediente as ExpedienteCalculo
        rechazo = motivo_de_rechazo_de_carga(
            ExpedienteCalculo(exp.codigo_carpeta, Estado(exp.estado), describio=exp.describio))
        if rechazo and hoja.modo == "verificar" and exp.estado != Estado.HOJA_EN_ELABORACION.value:
            raise HTTPException(409, rechazo)
    else:
        exp = Expediente(codigo_carpeta=carpeta, caja_origen=unidad.caja_origen,
                         caja_trabajo=unidad.caja_trabajo, estado=Estado.EN_COLA.value)
        db.add(exp)
        db.flush()

    exp.archivo_origen = hoja.archivo_origen or exp.archivo_origen
    # El campo 15 de la hoja de control lo pone la sesión, no el formulario. Quien diligencia
    # o corrige queda registrado con su propio nombre y no puede escribir el de otra persona:
    # de eso depende que la bitácora sirva como evidencia ante el Servicio Geológico.
    exp.responsable_hoja = quien.nombre

    # El campo 7, nombre del expediente, es el que escribió o corrigió la persona y manda
    # sobre todo lo demás: es el título atribuido del elemento 3.1.2. Antes no se guardaba y
    # la descripción terminaba tomando el asunto del inventario de origen, que en un fondo
    # acumulado suele ser un párrafo en mayúsculas y no un título. Va sin marca de propuesta
    # porque lo escribió una persona.
    if (hoja.nombre_expediente or "").strip():
        # Campo 7 de la F-GDM-007. Va a su columna: es el nombre corto del expediente en
        # la hoja, no el título atribuido de la descripción. Confundirlos hacía que el
        # ISAD(G) saliera titulado «Informes», que es justo lo que devuelven.
        exp.nombre_expediente = hoja.nombre_expediente.strip()

    diligenciamiento = fecha_diligenciamiento_valida(hoja.fecha_diligenciamiento)   # R31
    exp.fecha_diligenciamiento = diligenciamiento.completa

    calculo = [TramiteCalculo(
        no_item_leido=str(t.no_item or ""), folio_desde_leido=str(t.folio_desde or ""),
        folio_hasta_leido=str(t.folio_hasta or ""), tipo_documental=t.tipo_documental,
        fecha=normalizar_fecha(t.fecha), no_radicado=t.no_radicado,
        sistema_informacion=t.sistema_informacion, expediente_sgdea=t.expediente_sgdea,
        enlace_acceso=t.enlace_acceso, observaciones=t.observaciones, fila=t.fila)
        for t in hoja.tramites]

    # R6, R7 y R9. Manda la fecha. El periodo sale de las fechas extremas de los propios
    # trámites; el inventario de origen queda de referencia y solo se usa cuando el expediente
    # no tiene ninguna fecha legible. Si el inventario dice una cosa y las fechas otra, gana la
    # fecha y la diferencia queda anotada para control de calidad. Una persona siempre puede
    # fijarlo a mano y eso manda sobre todo lo demás.
    from app.services.periodos import (ORIGEN_FECHAS, ORIGEN_INVENTARIO, ORIGEN_MANUAL,
                                       resolver_periodo)

    fi, ff, _ = fechas_extremas([t.fecha for t in calculo])
    resuelto = resolver_periodo(unidad.periodo or "", fi, ff, _rangos(db),
                                hoja.periodo_manual or "", _sugerir_periodo(db, unidad))
    romano = resuelto.romano or ""
    exp.periodo_fijado_a_mano = resuelto.origen == ORIGEN_MANUAL

    # R41. Guardar avance no verifica: la hoja queda en elaboración.
    if hoja.modo == "avance":
        _guardar_tramites(db, exp, calculo)
        _huella(db, exp, Estado.HOJA_EN_ELABORACION, "guardar_avance", quien)
        db.commit()
        return {"carpeta": carpeta, "estado": exp.estado,
                "mensaje": "Avance guardado. La hoja no se verificó todavía."}

    resultado = verificar_hoja(
        Lectura(Encabezado(hoja.codigo_serie, hoja.serie, hoja.codigo_subserie, hoja.subserie,
                           hoja.nombre_expediente),
                calculo, quien.nombre, hoja.fecha_diligenciamiento),
        UnidadCalculo(carpeta, romano, unidad.folios, unidad.asunto or "", unidad.caja_origen or ""),
        _opciones_tvd(db, romano) if romano else [],
        periodo_sugerido=_sugerir_periodo(db, unidad))
    if resuelto.aviso:
        (resultado.errores if resuelto.requiere_persona else resultado.observaciones).append(resuelto.aviso)
    if romano and resuelto.origen == ORIGEN_INVENTARIO:
        resultado.observaciones.append(
            f"El periodo {romano} se tomó del inventario de origen porque el expediente no "
            "tiene fechas con qué comprobarlo. No está verificado por fechas.")

    _guardar_tramites(db, exp, calculo)
    periodo = db.query(Periodo).filter(Periodo.numero_romano == romano).first() if romano else None
    exp.periodo_id = periodo.id if periodo else None
    if resultado.alineada:
        sub = _subserie_de(db, resultado.clasificacion.opcion, romano)
        exp.subserie_id = sub.id if sub else None
    if not resultado.errores:
        # Las fechas extremas se leen según la unidad sea libro empastado o carpeta suelta:
        # en el libro mandan el primer y el último folio, porque no se puede reordenar.
        from app.services.libros import resolver_fechas
        fi2, ff2, texto2, enc, avisos_fechas = resolver_fechas(
            exp.tramites, unidad, exp.encuadernada,
            periodo.fecha_inicio if periodo else None, periodo.fecha_fin if periodo else None)
        exp.fecha_inicial, exp.fecha_final, exp.fechas_texto = fi2, ff2, texto2
        exp.volumen_folios = resultado.folios
        resultado.observaciones.extend(avisos_fechas)
    # La diferencia de folios se guarda en el expediente, no en la observación de un trámite:
    # tiene que salir después en la hoja de control y en el inventario de salida F-GDM-003.
    # Si al corregir la hoja los folios ya cuadran, la constancia se retira.
    exp.diferencia_folios = resultado.diferencia_folios or None

    _huella(db, exp, resultado.estado_resultante, "verificar", quien,
            motivo=resultado.detalle(quien.nombre), errores=resultado.errores or None)
    db.commit()

    return {"carpeta": carpeta, "estado": exp.estado, "errores": resultado.errores,
            "errores_localizados": [{"no_item": e.no_item, "fila": e.fila, "campo": e.campo,
                                     "mensaje": e.mensaje} for e in resultado.errores_localizados],
            "observaciones": resultado.observaciones,
            "subserie": str(resultado.clasificacion.opcion) if resultado.alineada else None,
            "periodo": romano or None, "origen_del_periodo": resuelto.origen,
            "discrepancia_periodo": resuelto.discrepancia or None,
            "tramites": resultado.tramites, "folios": resultado.folios,
            "diferencia_folios": resultado.diferencia_folios,
            "mensaje": resultado.detalle(quien.nombre),
            "siguiente_paso": ("Corrija lo señalado y vuelva a verificar."
                               if resultado.errores else
                               "Revise la hoja y, cuando esté conforme, pulse Generar ISAD(G).")}


def _guardar_tramites(db: Session, exp: Expediente, calculo: list[TramiteCalculo]) -> None:
    for viejo in list(exp.tramites):
        db.delete(viejo)
    db.flush()
    for t in calculo:
        exp.tramites.append(Tramite(
            no_item=t.no_item or 0, fecha=t.fecha.completa if t.fecha else None,
            fecha_texto=t.fecha.texto if t.fecha else None, tipo_documental=t.tipo_documental,
            folio_desde=t.folio_desde, folio_hasta=t.folio_hasta, no_radicado=t.no_radicado,
            sistema_informacion=t.sistema_informacion, expediente_sgdea=t.expediente_sgdea,
            enlace_acceso=t.enlace_acceso,
            # La columna de observaciones lleva SOLO las novedades de la carpeta: lo roto,
            # lo manchado, lo que falta. Ni la contabilidad de la foliación, que ya está en
            # las casillas de folios, ni el contraste con el inventario, que tiene su propio
            # sitio en el expediente y sale en la hoja y en el F-GDM-003.
            observaciones=limpiar_observacion(t.observaciones) or None))


def _subserie_de(db: Session, opcion, romano: str):
    """
    La fila de la base que corresponde a una opción de la tabla de valoración.

    Filtra también por la dependencia cuando la opción la trae: los mismos códigos de serie
    y de subserie existen en varias oficinas productoras del mismo periodo y sin ese filtro
    se guardaba la de cualquiera de ellas.
    """
    from app.models import Seccion, Serie
    consulta = (db.query(Subserie).join(Serie, Subserie.serie_id == Serie.id)
                  .join(Seccion, Serie.seccion_id == Seccion.id)
                  .join(Periodo, Seccion.periodo_id == Periodo.id)
                  .filter(Periodo.numero_romano == romano.upper(),
                          Serie.codigo == opcion.cod_serie,
                          Subserie.codigo == opcion.cod_subserie))
    dependencia = getattr(opcion, "codigo_dependencia", "")
    if dependencia:
        exacta = consulta.filter(Seccion.codigo_dependencia == dependencia).first()
        if exacta:
            return exacta
    return consulta.first()


def _sugerir_periodo(db: Session, unidad: UnidadInventario) -> tuple[str, str] | None:
    """
    R9. Para una carpeta sin ninguna fecha legible, propone el periodo de sus compañeras.

    Manda la caja de origen, que es la caja del archivo central en la que el expediente vino
    y la que el inventario antiguo registra. Una caja de origen se llenó en su momento con
    documentación de una misma época, así que sus compañeras son la mejor pista disponible.
    La caja de trabajo del contrato entra solo como respaldo, porque esa la armamos nosotros
    y puede mezclar procedencias.

    Ninguna carpeta debe quedar suelta: si no hay fecha, hay propuesta; y si no hay ni eso,
    la asigna una persona.
    """
    for campo, valor, como in (
            (UnidadInventario.caja_origen, unidad.caja_origen, "caja de origen"),
            (UnidadInventario.caja_trabajo, unidad.caja_trabajo, "caja de trabajo")):
        if not valor:
            continue
        companeras = (db.query(UnidadInventario.periodo)
                        .filter(campo == valor, UnidadInventario.periodo != "",
                                UnidadInventario.codigo_carpeta != unidad.codigo_carpeta).all())
        periodos = [p for (p,) in companeras if p and p.strip()]
        if periodos:
            elegido = max(set(periodos), key=periodos.count)
            cuantas = periodos.count(elegido)
            return elegido, (f"{como} {valor}, donde {cuantas} de {len(periodos)} carpetas "
                             f"son del periodo {elegido}")
    return None


# ---------------------------------------------------------------------------
# Paso dos. La descripción la dispara una persona.
# ---------------------------------------------------------------------------
@router.post("/{codigo_carpeta}/levantar-hoja",
             summary="Que el modelo lea el documento y proponga la hoja de control")
def levantar_hoja(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
                  quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Encola la lectura del expediente digitalizado. El modelo separa los trámites, reconoce
    fechas y tipos documentales, propone la foliación y anota el estado de conservación; y
    con eso el sistema resuelve solo las fechas extremas, el periodo y la subserie.

    Todo queda como propuesta: la hoja pasa a «en elaboración» para que una persona la revise.
    """
    from app.models import Archivo
    exp = _cargar(db, codigo_carpeta)
    if not quien.edita_hoja_control:
        raise HTTPException(403, "Su perfil es de consulta.")
    if exp.estado in (Estado.ARCHIVADO.value, Estado.EN_INVENTARIO.value,
                      Estado.DESCRIPCION_VALIDADA.value, Estado.DESCRIPCION_POR_VALIDAR.value):
        raise HTTPException(409, f"{exp.codigo_carpeta} ya tiene descripción hecha "
                                 f"(estado «{exp.estado}»). Use Rehacer si de verdad hay que "
                                 "volver a empezar.")
    doc = _documentos(db, exp.codigo_carpeta)
    if not doc["cargados"]:
        raise HTTPException(422, f"{exp.codigo_carpeta} no tiene documento digitalizado cargado. "
                                 "Cárguelo en la pestaña Cargue.")
    if not doc["se_puede_leer"]:
        raise HTTPException(422, f"{exp.codigo_carpeta} tiene el registro del documento pero el "
                                 f"archivo no está en el almacén: {', '.join(doc['faltantes'])}. "
                                 "Vuelva a cargarlo en la pestaña Cargue.")

    # El turno reparte los expedientes entre las llaves: el que se encola de primero entra
    # por la primera llave, el segundo por la segunda, y así.
    from app.models import Trazabilidad as _T
    turno = db.query(func.count(_T.id)).filter(_T.accion == "levantar_hoja").scalar() or 0

    from app.tasks import levantar_hoja_de_control
    try:
        levantar_hoja_de_control.delay(exp.id, quien.nombre, turno)
        encolado = True
    except Exception:
        encolado = False

    if not encolado:
        raise HTTPException(503, "El trabajador de tareas no está disponible. Levante los "
                                 "servicios y vuelva a intentar.")
    return {"carpeta": exp.codigo_carpeta, "encolado": True,
            "mensaje": ("El modelo está leyendo el expediente. Según el tamaño puede tardar "
                        "entre uno y varios minutos. Siga trabajando: cuando termine aparecerá "
                        "en «Hojas en proceso» con sus trámites propuestos, y de una vez con el "
                        "periodo y la subserie asignados.")}


@router.post("/{codigo_carpeta}/marcar-revisada", summary="Paso humano: alguien del equipo revisó la hoja")
def marcar_revisada(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
                    quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Confirma que una persona miró la hoja de control y quedó conforme. Sin este paso no se
    puede generar la descripción: es lo que separa el trabajo verificado del trabajo revisado.
    """
    exp = _cargar(db, codigo_carpeta)
    if not quien.revisa_hoja_control:
        raise HTTPException(403, "Su perfil es de consulta y no revisa hojas de control.")
    if exp.estado != Estado.HOJA_POR_REVISAR.value:
        raise HTTPException(409, f"{exp.codigo_carpeta} está en «{exp.estado}» y no esperando revisión.")
    # Campo 15 del formato: el responsable de la hoja de control es quien la revisa. Se toma
    # del inicio de sesión y no de un formulario, para que nadie pueda firmar por otro.
    exp.reviso_hoja = quien.nombre
    exp.fecha_revision = date.today()
    _huella(db, exp, Estado.HOJA_REVISADA, "revisar_hoja", quien)
    db.commit()
    return {"carpeta": exp.codigo_carpeta, "estado": exp.estado,
            "mensaje": f"Hoja de control revisada por {quien.nombre}. Ya se puede generar el ISAD(G)."}


@router.post("/{codigo_carpeta}/validar-isadg", summary="Paso humano: validar la descripción")
def validar_isadg(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
                  quien: Usuario = Depends(usuario_actual)) -> dict:
    """Quien valida el ISAD(G) confirma que la descripción está completa y bien redactada."""
    exp = _cargar(db, codigo_carpeta)
    if not quien.valida_descripcion:
        raise HTTPException(403, "La validación del ISAD(G) la hace la profesional a cargo de la "
                                 "descripción, o la dirección y la líder.")
    if exp.estado != Estado.DESCRIPCION_POR_VALIDAR.value:
        raise HTTPException(409, f"{exp.codigo_carpeta} está en «{exp.estado}» y no esperando validación.")
    _huella(db, exp, Estado.DESCRIPCION_VALIDADA, "validar_isadg", quien)
    db.commit()
    return {"carpeta": exp.codigo_carpeta, "estado": exp.estado,
            "mensaje": f"Descripción validada por {quien.nombre}. Queda lista para aprobación."}


@router.post("/{codigo_carpeta}/generar-isadg", summary="Generar la descripción de una hoja revisada")
def generar_isadg(codigo_carpeta: str, usar_modelo: bool = Query(
                      True, description="Falso describe solo con los datos verificados, sin gastar cuota"),
                  db: Session = Depends(obtener_sesion),
                  quien: Usuario = Depends(usuario_actual)) -> dict:
    exp = _cargar(db, codigo_carpeta)
    if not quien.elabora_descripcion:
        raise HTTPException(403, "La descripción ISAD(G) la elaboran las profesionales a cargo "
                                 "de la descripción y la dirección del proyecto. Su perfil "
                                 "diligencia y corrige hojas de control.")
    if exp.estado != Estado.HOJA_REVISADA.value:
        raise HTTPException(409, f"Solo se describe una hoja ya revisada por una persona. "
                                 f"{exp.codigo_carpeta} está en «{exp.estado}».")
    if not exp.subserie_id:
        raise HTTPException(422, "Asigne la subserie de la tabla de valoración antes de describir.")

    from app.services import modelos
    from app.services.descripcion import construir_descripcion

    propuesta = None
    if usar_modelo:
        contexto = _contexto_para_el_modelo(db, exp)
        documento = _documento_del_expediente(db, exp)
        if documento:
            # Con el documento a la vista la descripción sale mucho mejor: el modelo ve de
            # qué trata realmente el expediente y no solo la lista de tipos documentales.
            from app.services.lectura import instruccion_descripcion
            propuesta = modelos.leer_documento(
                db, documento, instruccion_descripcion(contexto, contexto["tramites"]),
                exp.volumen_folios)
        if not propuesta:
            propuesta = modelos.describir(db, contexto)
    construir_descripcion(db, exp, quien, propuesta.campos if propuesta else None)
    # Qué motor redactó. Se guarda para que la revisión la haga uno distinto.
    if propuesta:
        exp.redactada_por = propuesta.proveedor
    exp.describio = quien.nombre
    _huella(db, exp, Estado.PENDIENTE_REVISION, "generar_isadg", quien)
    db.commit()
    return {"carpeta": exp.codigo_carpeta, "estado": exp.estado,
            "codigo_referencia": exp.codigo_referencia,
            "redactada_por": propuesta.proveedor if propuesta else "solo datos verificados",
            "modelo": propuesta.modelo if propuesta else None,
            "mensaje": ("Descripción generada. Los textos propuestos por el modelo van marcados "
                        "y quedan pendientes de revisión."
                        if propuesta else
                        "Descripción generada solo con los datos verificados, sin modelo de "
                        "lenguaje. Puede completar los textos en la revisión o volver a generarla "
                        "cuando haya cuota.")}


@router.get("/modelos/disponibilidad", summary="Cuánta cuota le queda hoy a cada modelo",
            tags=["Expedientes"])
def cuota_modelos(refrescar: bool = Query(False, description="Volver a preguntarle a cada "
                                          "proveedor qué modelos tiene"),
                  db: Session = Depends(obtener_sesion),
                  quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    from app.services import modelos
    salida = modelos.disponibilidad(db, forzar=refrescar)
    db.commit()
    return salida


@router.post("/{codigo_carpeta}/aprobar", summary="Aprobar y archivar la descripción")
def aprobar(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    exp = _cargar(db, codigo_carpeta)
    if not quien.aprueba_descripcion:
        raise HTTPException(403, "Solo la dirección del proyecto o la líder aprueban descripciones.")
    if exp.describio and cod.normalizar_texto(exp.describio) == cod.normalizar_texto(quien.nombre):
        raise HTTPException(409, f"{quien.nombre} elaboró esta descripción y no puede aprobar su "
                                 "propio trabajo.")
    if exp.estado != Estado.DESCRIPCION_VALIDADA.value:
        raise HTTPException(409, f"{exp.codigo_carpeta} está en «{exp.estado}». Solo se aprueba "
                                 "una descripción ya validada.")
    exp.aprobo = quien.nombre
    exp.fecha_aprobacion = datetime.now()
    _huella(db, exp, Estado.ARCHIVADO, "aprobar", quien)
    db.commit()
    return {"carpeta": exp.codigo_carpeta, "estado": exp.estado,
            "mensaje": "Descripción aprobada. Queda lista para el inventario de salida."}


# ---------------------------------------------------------------------------
# Retiro de un expediente cargado por error (paso nuevo)
# ---------------------------------------------------------------------------
class EncuadernacionEntrada(BaseModel):
    es_libro: bool = Field(description="Verdadero si la unidad es un libro empastado o un tomo")


@router.post("/{codigo_carpeta}/encuadernacion",
             summary="Confirmar o negar que la unidad es un libro empastado")
def fijar_encuadernacion(codigo_carpeta: str, cuerpo: EncuadernacionEntrada,
                         db: Session = Depends(obtener_sesion),
                         quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Una persona decide si la unidad es libro, y su decisión manda sobre la detección
    automática del inventario de origen.

    Cambia cómo se leen las fechas extremas: en un libro salen del primer y del último folio,
    porque el orden original no se puede alterar; en una carpeta suelta salen de la fecha más
    antigua y la más reciente. Por eso al fijarla se vuelven a calcular.
    """
    if not quien.edita_hoja_control:
        raise HTTPException(403, "Su perfil es de consulta y no modifica expedientes.")
    exp = _cargar(db, codigo_carpeta)
    unidad = (db.query(UnidadInventario)
                .filter(UnidadInventario.codigo_carpeta == exp.codigo_carpeta).first())

    exp.encuadernada = cuerpo.es_libro
    exp.encuadernacion_por = quien.nombre

    from app.services.libros import resolver_fechas
    periodo = db.get(Periodo, exp.periodo_id) if exp.periodo_id else None
    fi, ff, texto, enc, avisos = resolver_fechas(
        exp.tramites, unidad, exp.encuadernada,
        periodo.fecha_inicio if periodo else None, periodo.fecha_fin if periodo else None)
    exp.fecha_inicial, exp.fecha_final, exp.fechas_texto = fi, ff, texto

    detalle = (f"{quien.nombre} marcó la unidad como "
               f"{'libro empastado' if cuerpo.es_libro else 'carpeta suelta'}. "
               f"Fechas extremas recalculadas: {texto}.")
    db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                        estado_nuevo=exp.estado, accion="encuadernacion",
                        usuario=quien.nombre, motivo=detalle + " " + " ".join(avisos)))
    db.commit()
    return {"carpeta": exp.codigo_carpeta, "es_libro": exp.encuadernada,
            "fechas_extremas": texto, "avisos": avisos, "mensaje": detalle}


@router.post("/{codigo_carpeta}/retirar", summary="Retirar del flujo un expediente cargado por error")
def retirar(codigo_carpeta: str, cuerpo: MotivoEntrada, db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    exp = _cargar(db, codigo_carpeta)
    if not quien.puede_retirar:
        raise HTTPException(403, "Retirar un expediente lo hace la dirección del proyecto o la líder.")
    if exp.estado == Estado.RETIRADO.value:
        raise HTTPException(409, f"{exp.codigo_carpeta} ya está retirada.")
    if exp.estado == Estado.EN_INVENTARIO.value:
        raise HTTPException(409, f"{exp.codigo_carpeta} ya está en el inventario de salida, en la "
                                 f"caja {exp.caja_definitiva}. Retírela primero de la caja.")
    exp.retirado_en = datetime.now()
    exp.motivo_retiro = cuerpo.motivo
    _huella(db, exp, Estado.RETIRADO, "retirar", quien, motivo=cuerpo.motivo)
    db.commit()
    return {"carpeta": exp.codigo_carpeta, "estado": exp.estado,
            "se_purga_el": str(fecha_de_purga(exp) or ""),
            "mensaje": "Expediente retirado del flujo. El código queda libre para volver a cargarlo "
                       "y la carpeta se puede restaurar durante treinta días."}


@router.post("/{codigo_carpeta}/restaurar", summary="Devolver al flujo un expediente retirado")
def restaurar(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
              quien: Usuario = Depends(usuario_actual)) -> dict:
    exp = _cargar(db, codigo_carpeta)
    if not quien.puede_retirar:
        raise HTTPException(403, "Restaurar un expediente lo hace la dirección del proyecto o la líder.")
    if exp.estado != Estado.RETIRADO.value:
        raise HTTPException(409, f"{exp.codigo_carpeta} no está retirada.")
    from app.services.estados import DIAS_EN_PAPELERA
    if dias_en_papelera(exp) > DIAS_EN_PAPELERA:
        raise HTTPException(409, f"{exp.codigo_carpeta} lleva más de {DIAS_EN_PAPELERA} días retirada "
                                 "y ya fue purgada. Cárguela de nuevo; la bitácora conserva el antecedente.")
    motivo = exp.motivo_retiro or ""
    _huella(db, exp, Estado.DEVUELTO, "restaurar", quien, motivo=f"Restaurada. Motivo del retiro: {motivo}")
    exp.retirado_en = None
    exp.motivo_retiro = None
    db.commit()
    return {"carpeta": exp.codigo_carpeta, "estado": exp.estado,
            "mensaje": "Expediente restaurado. Corríjalo y vuelva a verificar."}


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------
@router.get("/periodos", summary="Los periodos institucionales del fondo")
def periodos(db: Session = Depends(obtener_sesion),
             quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    """La lista para el desplegable de periodo, con su rango y su entidad productora."""
    return [{"romano": p.numero_romano, "rango": p.rango_texto,
             "entidad": p.entidad_productora,
             "inicio": p.fecha_inicio.isoformat() if p.fecha_inicio else None,
             "fin": p.fecha_fin.isoformat() if p.fecha_fin else None}
            for p in db.query(Periodo).order_by(Periodo.orden).all()]


@router.get("/candidatos-periodo/{codigo_carpeta}",
            summary="Periodos posibles para una carpeta, según la caja de la que viene")
def candidatos_periodo(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
                       quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Los periodos que puede tener una carpeta, ordenados por cuántas compañeras los respaldan.

    Una caja de origen del archivo central se llenó en su momento con documentación de una
    misma época, de modo que sus compañeras son la mejor pista cuando el expediente no tiene
    fechas con qué resolverlo. Se devuelve la lista para que la persona escoja, no un dato
    impuesto.
    """
    carpeta = cod.normalizar_codigo_carpeta(codigo_carpeta) or codigo_carpeta.upper()
    u = db.query(UnidadInventario).filter(UnidadInventario.codigo_carpeta == carpeta).first()
    if not u:
        raise HTTPException(404, f"{carpeta} no está en el inventario de origen.")

    salida = []
    for campo, valor, como in (
            (UnidadInventario.caja_origen, u.caja_origen, "caja de origen"),
            (UnidadInventario.caja_trabajo, u.caja_trabajo, "caja de trabajo")):
        if not valor:
            continue
        filas = (db.query(UnidadInventario.periodo, func.count(UnidadInventario.id))
                   .filter(campo == valor, UnidadInventario.periodo != "")
                   .group_by(UnidadInventario.periodo).all())
        total = sum(c for _, c in filas)
        for romano, cuantas in sorted(filas, key=lambda x: -x[1]):
            if romano and not any(x["romano"] == romano for x in salida):
                salida.append({"romano": romano, "compañeras": cuantas, "de": total,
                               "porque": f"{cuantas} de {total} carpetas de la {como} {valor} "
                                         f"son del periodo {romano}"})
        if salida:
            break

    return {"carpeta": carpeta, "periodo_inventario": u.periodo or "",
            "caja_origen": u.caja_origen, "caja_trabajo": u.caja_trabajo,
            "candidatos": salida}


@router.get("/tvd/{periodo}", summary="Lista cerrada de subseries del periodo")
def subseries_del_periodo(periodo: str, db: Session = Depends(obtener_sesion),
                          quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    """
    La clasificación la elige una persona de esta lista, que es la tabla de valoración
    documental convalidada del periodo. El sistema propone, pero quien decide es el archivero.
    """
    opciones = _opciones_tvd(db, periodo)
    if not opciones:
        raise HTTPException(404, f"El periodo {periodo} no tiene tabla de valoración cargada.")

    salida = []
    for o in sorted(opciones, key=lambda x: (x.codigo_dependencia, x.cod_serie, x.cod_subserie)):
        # La etiqueta va como estuvo siempre, sin la oficina productora delante: así lo pidió
        # la dirección del proyecto, que ya tiene la lista aprendida y no quiere que le cambie
        # de forma. La oficina no se pierde: viaja en el valor de la opción, se llena sola en
        # el código de dependencia del encabezado y se muestra debajo del selector una vez
        # escogida. Lo que se corrigió es que dos filas distintas de la tabla ya no se pisan.
        etiqueta = f"{o.cod_serie} {o.serie} › {o.cod_subserie} {o.subserie}"
        salida.append({"valor": o.clave,
                       "cod_serie": o.cod_serie, "serie": o.serie,
                       "cod_subserie": o.cod_subserie, "subserie": o.subserie,
                       "codigo_dependencia": o.codigo_dependencia,
                       "dependencia": o.oficina_productora,
                       "retencion_central_anios": o.retencion_central_anios,
                       "disposicion_final": o.disposicion_final,
                       "etiqueta": etiqueta})
    return salida


@router.get("/inventario/{codigo_carpeta}", summary="Qué dice el inventario de origen de una carpeta")
def inventario(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
               quien: Usuario = Depends(usuario_actual)) -> dict:
    """Sirve para prellenar la hoja de control y no volver a escribir lo que ya está escrito."""
    carpeta = cod.normalizar_codigo_carpeta(codigo_carpeta) or codigo_carpeta.upper()
    u = db.query(UnidadInventario).filter(UnidadInventario.codigo_carpeta == carpeta).first()
    if not u:
        raise HTTPException(404, f"La carpeta {carpeta} no está en el inventario de origen del "
                                 "contrato, es decir no pertenece a la selección inventariada.")
    # El periodo se resuelve con las fechas que trae el inventario, que es lo único que hay
    # antes de leer el documento. Manda la fecha, igual que en todo lo demás.
    from app.services.periodos import resolver_periodo
    resuelto = resolver_periodo(u.periodo or "", u.fecha_inicial, u.fecha_final, _rangos(db),
                                sugerencia_caja=_sugerir_periodo(db, u))
    romano = resuelto.romano or ""
    origen = resuelto.origen
    if not romano and (u.periodo or "").strip():
        # Las fechas no alcanzaron a resolverlo. Se usa el del inventario para no dejar la
        # pantalla vacía, pero se dice de dónde salió y que no está comprobado.
        romano = u.periodo.strip().upper()
        origen = "inventario, sin comprobar con las fechas"

    # Y con el periodo resuelto se propone una subserie de su tabla de valoración. Se propone
    # SIEMPRE que el periodo tenga tabla cargada: la persona valida y corrige, no clasifica
    # desde cero. La propuesta buena, la que sale del contenido leído, llega después con la
    # hoja de control levantada por el modelo.
    propuesta, como, seguridad = _proponer_subserie(db, u, romano)

    return {"codigo_carpeta": u.codigo_carpeta, "periodo": romano,
            "periodo_inventario": u.periodo or "",
            "origen_del_periodo": origen,
            "aviso_periodo": resuelto.aviso or resuelto.discrepancia or "",
            "requiere_persona": resuelto.requiere_persona,
            "sin_periodo": not romano, "folios": u.folios,
            "asunto": u.asunto, "caja_origen": u.caja_origen, "caja_trabajo": u.caja_trabajo,
            "cod_serie": u.cod_serie or "", "serie": u.serie or "",
            "cod_subserie": u.cod_subserie or "", "subserie": u.subserie or "",
            "propuesta_subserie": propuesta, "propuesta_porque": como,
            "propuesta_seguridad": seguridad,
            "fecha_inicial": u.fecha_inicial.isoformat() if u.fecha_inicial else None,
            "fecha_final": u.fecha_final.isoformat() if u.fecha_final else None}


def _proponer_subserie(db: Session, unidad, romano: str) -> tuple[dict | None, str, str]:
    """
    Propone una subserie de la tabla de valoración del periodo. SIEMPRE propone una.

    Esta es la propuesta rápida, la del botón «Traer datos»: no gasta modelo, porque en ese
    momento todavía no se ha leído el documento y lo único que hay es el asunto del
    inventario. La propuesta buena, la que sale del contenido leído, la hace el modelo al
    levantar la hoja de control y llega después por sí sola.

    Ni siquiera aquí se deja la casilla vacía. Antes, cuando el código del inventario no
    existía en la tabla del periodo, la lista quedaba sin escoger y la persona tenía que
    clasificar desde cero; ahora se propone lo más parecido y se dice con cuánta seguridad,
    para que la persona valide en lugar de diligenciar.
    """
    from app.services.clasificacion import (CONFIANZA_MEDIA, Eleccion, asimilar_encabezado,
                                            elegir_por_contenido)
    if not romano:
        return None, "", ""
    opciones = _opciones_tvd(db, romano)
    if not opciones:
        return None, "", ""

    eleccion = Eleccion()
    if unidad.cod_serie or unidad.subserie:
        c = asimilar_encabezado(Encabezado(unidad.cod_serie or "", unidad.serie or "",
                                           unidad.cod_subserie or "", unidad.subserie or ""),
                                opciones)
        if c.alineada:
            eleccion = Eleccion(c.opcion, "por la clasificación que trae el inventario",
                                CONFIANZA_MEDIA, "inventario")

    if not eleccion.hay:
        from app.tasks import subseries_mas_usadas
        eleccion = elegir_por_contenido(
            opciones, [unidad.asunto or "", unidad.serie or "", unidad.subserie or ""],
            subseries_mas_usadas(db, romano))

    return eleccion.como_dict(), eleccion.porque, eleccion.confianza


@router.get("/resumen", summary="Cuántos expedientes hay en cada estado")
def resumen(db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    """Alimenta el tablero del día y el centro de control."""
    from sqlalchemy import func as f
    conteo = dict(db.query(Expediente.estado, f.count(Expediente.id))
                    .group_by(Expediente.estado).all())
    orden = [Estado.EN_COLA, Estado.EN_PROCESAMIENTO, Estado.HOJA_EN_ELABORACION,
             Estado.HOJA_VERIFICADA, Estado.PENDIENTE_REVISION, Estado.DEVUELTO,
             Estado.ARCHIVADO, Estado.EN_INVENTARIO, Estado.RETIRADO]
    return {
        "estados": [{"estado": e.value, "cantidad": conteo.get(e.value, 0)} for e in orden],
        "total": sum(conteo.values()),
        "inventario_de_origen": db.query(UnidadInventario).count(),
        "hoy": db.query(Expediente).filter(
            f.date(Expediente.actualizado_en) == f.current_date()).count(),
    }


@router.get("/produccion", summary="Qué se hizo hoy y a qué ritmo vamos")
def produccion_del_dia(dia: str | None = Query(None, description="Un día concreto, en año-mes-día. "
                                               "Vacío es hoy."),
                       db: Session = Depends(obtener_sesion),
                       quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    El tablero de producción del contrato: el embudo del proceso, lo hecho en el día por
    labor y por persona, los últimos treinta días y la proyección de terminación.

    Todo sale de la bitácora, de modo que refleja el trabajo real y no un contador aparte.
    """
    from datetime import date as _fecha
    from app.services.produccion import produccion
    elegido = None
    if dia:
        try:
            elegido = _fecha.fromisoformat(dia)
        except ValueError:
            raise HTTPException(422, f"La fecha {dia!r} no tiene la forma año-mes-día.")
    return produccion(db, elegido).como_dict()


@router.get("/ahora", summary="Qué se está moviendo en este momento y quién")
def en_marcha(minutos: int = Query(30, ge=5, le=480),
              db: Session = Depends(obtener_sesion),
              quien: Usuario = Depends(usuario_actual)) -> dict:
    """El tablero en vivo: avance del contrato, qué hay en vuelo y quién está trabajando."""
    from app.services.produccion import _embudo, ahora
    universo, embudo = _embudo(db)
    return {"universo": universo, "embudo": embudo, **ahora(db, minutos)}


@router.get("/calidad", summary="Control de calidad: qué está mal en lo que llevamos")
def calidad(estado: str | None = Query(None, description="Revisar solo los de un estado"),
            gravedad: str | None = Query(None, pattern="^(error|revisar|aviso)$"),
            limite: int = Query(2000, le=10000),
            db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Pasa todas las pruebas de calidad sobre lo cargado y devuelve los hallazgos.

    No corrige nada. Señala la carpeta, qué prueba falló y dónde se corrige, para que el
    equipo lo arregle antes de que el expediente siga avanzando y para poder demostrarle al
    Servicio Geológico Colombiano que lo entregado se revisó.
    """
    from app.services.calidad import revisar_todo
    informe = revisar_todo(db, estado, limite)
    hallazgos = [h for h in informe.hallazgos if not gravedad or h.gravedad == gravedad]
    return {"resumen": informe.resumen(),
            "hallazgos": [h.como_dict() for h in hallazgos]}


@router.get("/calidad/excel", summary="Descargar el informe de calidad en Excel")
def calidad_excel(estado: str | None = Query(None), limite: int = Query(5000, le=20000),
                  db: Session = Depends(obtener_sesion),
                  quien: Usuario = Depends(usuario_actual)):
    """El mismo informe, en un libro que se puede anexar a un acta o a un informe de avance."""
    from fastapi.responses import FileResponse
    from app.services.calidad import informe_a_excel, revisar_todo
    informe = revisar_todo(db, estado, limite)
    ruta = informe_a_excel(informe, quien.nombre)
    return FileResponse(ruta, filename=ruta.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("", summary="Listar expedientes por estado")
def listar(estado: str | None = None, limite: int = Query(100, le=1000),
           db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    consulta = db.query(Expediente)
    if estado:
        consulta = consulta.filter(Expediente.estado == estado)
    return [{"codigo_carpeta": e.codigo_carpeta, "estado": e.estado, "responsable": e.responsable,
             "folios": e.volumen_folios, "fechas_extremas": e.fechas_texto,
             "documento": _documentos(db, e.codigo_carpeta)}
            for e in consulta.order_by(Expediente.actualizado_en.desc()).limit(limite).all()]


@router.get("/{codigo_carpeta}", summary="Ficha del expediente")
def ficha(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
          quien: Usuario = Depends(usuario_actual)) -> dict:
    exp = _cargar(db, codigo_carpeta)
    d = _ficha(exp)
    d["documento"] = _documentos(db, exp.codigo_carpeta)
    d.update(_clasificacion_de(db, exp))
    return d


def _clasificacion_de(db: Session, exp: Expediente) -> dict:
    """
    El periodo y la subserie que ya tiene asignados el expediente.

    Sin esto, lo que el modelo clasificó al levantar la hoja se quedaba guardado en la base
    y la pantalla del editor volvía a abrirse en blanco, como si nadie hubiera clasificado
    nada. La persona tenía que escoger otra vez lo que la plataforma ya había escogido.
    """
    from app.models import Seccion, Serie
    periodo = db.get(Periodo, exp.periodo_id) if exp.periodo_id else None
    sub = db.get(Subserie, exp.subserie_id) if exp.subserie_id else None
    serie = db.get(Serie, sub.serie_id) if sub else None
    seccion = db.get(Seccion, serie.seccion_id) if serie else None
    return {"periodo": periodo.numero_romano if periodo else "",
            "cod_serie": serie.codigo if serie else "",
            "serie": serie.nombre if serie else "",
            "cod_subserie": sub.codigo if sub else "",
            "subserie": sub.nombre if sub else "",
            "codigo_dependencia": seccion.codigo_dependencia if seccion else "",
            "dependencia": seccion.oficina_productora if seccion else ""}


@router.get("/{codigo_carpeta}/hoja-de-control.xlsx",
            summary="La hoja de control de una carpeta, en el formato oficial F-GDM-007")
def hoja_de_control_en_excel(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
                             quien: Usuario = Depends(usuario_actual)):
    """
    Descarga la hoja de control de UNA carpeta, llena sobre la plantilla del Servicio
    Geológico.

    Sirve para cuando hay que entregar, revisar o imprimir un expediente concreto sin bajar
    el paquete completo. El código de carpeta se admite como se escriba —«808», «ac-cp-808»,
    «AC-CP-00808»— y la plataforma lo normaliza.
    """
    from fastapi.responses import Response

    from app.services import expedicion
    from app.services import formatos_sgc as fmt

    exp = _cargar(db, codigo_carpeta)
    if not exp.tramites:
        raise HTTPException(422, f"{exp.codigo_carpeta} todavía no tiene trámites en su hoja "
                                 "de control, así que no hay nada que expedir. Levántela con "
                                 "el modelo o diligéncíela primero.")
    expedicion.completar_revisores(db)
    contenido = fmt.hoja_de_control(expedicion.datos_de_hoja(db, exp))
    nombre = f"F-GDM-007_{exp.codigo_carpeta}.xlsx"
    return Response(contenido,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/{codigo_carpeta}/trazabilidad", summary="Historia completa del expediente")
def trazabilidad(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
                 quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    exp = _cargar(db, codigo_carpeta)
    return [{"fecha": h.fecha.isoformat(timespec="seconds"), "accion": h.accion,
             "de": h.estado_anterior, "a": h.estado_nuevo, "usuario": h.usuario,
             "motivo": h.motivo, "errores": json.loads(h.errores) if h.errores else None}
            for h in exp.trazabilidad]
