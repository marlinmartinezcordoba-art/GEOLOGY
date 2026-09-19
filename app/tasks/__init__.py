"""
Tareas en segundo plano.

Aquí vive lo que tarda: leer el expediente digitalizado completo y pedirle al modelo el
levantamiento de la hoja de control. Un expediente de trescientos folios puede tomar varios
minutos, y por eso no se hace mientras la persona espera frente a la pantalla: se encola,
la persona sigue trabajando y el resultado aparece en la bandeja cuando está listo.

Si el modelo se queda sin cuota o falla, la tarea lo deja anotado y el expediente vuelve a
la cola. Nunca se inventa una hoja de control.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

from app.core.celery_app import celery_app
from app.core.database import SesionLocal
from app.services.estados import Estado

# Peso máximo de cada BLOQUE que se manda a leer, en megabytes del documento original.
#
# El tope de los proveedores se mide sobre la petición ya armada, y el documento viaja
# codificado en texto, lo que lo engorda alrededor de un tercio. Con el tope puesto en 30 se
# estaba enviando cerca de 40 y lo rechazaban los tres: Gemini corta en 20 y Claude en 32.
# Por eso 14, que codificado da unos 19 y pasa por todos. No es una restricción de KUSTOS
# sino de a dónde se manda.
#
# Una advertencia práctica. Un escaneo a color pesa alrededor de 1,5 MB por página, así que
# un bloque de estos alcanza para unas nueve; en escala de grises a 300 puntos por pulgada
# —que es lo que exige la norma para documento textual— pesa la tercera parte y cada bloque
# se lleva casi treinta páginas. Capturar en grises hace la lectura tres veces más rápida y
# gasta tres veces menos cuota.
TOPE_MB = float(os.getenv("TOPE_MB_POR_ARCHIVO", "14"))

# Y el tope de páginas por petición. Por encima de esto conviene partir aunque el archivo pese
# poco: un expediente escaneado a 300 puntos por pulgada llena el contexto antes de llegar al
# límite de páginas, y la lectura falla sin decir por qué.
TOPE_PAGINAS = int(os.getenv("TOPE_PAGINAS_POR_ARCHIVO", "100"))


# Palabras con las que suele arrancar un asunto largo y que no aportan nada en un rótulo.
_ARRANQUES = ("expediente de ", "expediente que contiene ", "documentos de ",
              "documentación de ", "carpeta de ", "contiene ", "se trata de ")


def nombre_corto(asunto: str, tope: int = 60) -> str:
    """
    Convierte un asunto largo en el nombre del expediente, que es el campo 7 de la hoja.

    El campo 7 es el rótulo: «Estudios de laboratorio», no «Informes de resultados muestras
    N° 2356, 3467, 2358 de gasolina de la finca de Chochal del municipio de Cundinamarca».
    Ese detalle es el del tipo documental de cada trámite y allí se queda.

    Se corta por la primera pausa fuerte —dos puntos, punto y coma, raya, paréntesis o
    coma— y se le quitan los arranques que no dicen nada. Es un recorte, no una redacción:
    solo entra en juego cuando el modelo no mandó el nombre corto.
    """
    import re as _re
    texto = " ".join(str(asunto or "").split())
    if not texto:
        return ""
    texto = _re.split(r"\s+[·—–-]\s+|[:;(]|,", texto)[0].strip()
    bajo = texto.lower()
    for arranque in _ARRANQUES:
        if bajo.startswith(arranque):
            texto = texto[len(arranque):]
            break
    texto = texto.strip(" .,-")
    if len(texto) > tope:                      # sigue largo: se corta por palabra, no a la mitad
        recorte = texto[:tope].rsplit(" ", 1)[0]
        texto = recorte or texto[:tope]
    return texto[:1].upper() + texto[1:] if texto else ""


def _huella(db, exp, nuevo: Estado, accion: str, motivo: str = "", usuario: str | None = None):
    from app.models import Trazabilidad
    db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                        estado_nuevo=nuevo.value, accion=accion, usuario=usuario,
                        motivo=motivo or None))
    exp.estado = nuevo.value


@celery_app.task(name="kustos.levantar_hoja", bind=True, max_retries=2)
def levantar_hoja_de_control(self, expediente_id: int, quien: str | None = None,
                             turno: int | None = None) -> dict:
    """Lee el documento del expediente y propone su hoja de control."""
    from app.models import Archivo, Expediente, Periodo, UnidadInventario
    from app.services import lectura, modelos, particion
    from app.services.fechas import normalizar_fecha
    from app.services.folios import limpiar_observacion

    db = SesionLocal()
    try:
        exp = db.get(Expediente, expediente_id)
        if not exp:
            return {"error": "el expediente ya no existe"}

        # Si ya lo está leyendo otra tarea, esta se retira. Pasa cuando un expediente llega
        # partido: cada parte encola su lectura y basta con que la haga una.
        if exp.estado == Estado.EN_PROCESAMIENTO.value:
            return {"carpeta": exp.codigo_carpeta, "omitido": "ya se está leyendo"}
        if exp.estado in (Estado.DESCRIPCION_POR_VALIDAR.value, Estado.DESCRIPCION_VALIDADA.value,
                          Estado.ARCHIVADO.value, Estado.EN_INVENTARIO.value,
                          Estado.RETIRADO.value):
            return {"carpeta": exp.codigo_carpeta, "omitido": f"está en «{exp.estado}»"}

        archivos = (db.query(Archivo).filter(Archivo.codigo_carpeta == exp.codigo_carpeta)
                      .order_by(Archivo.fragmento).all())
        if not archivos:
            _huella(db, exp, Estado.DEVUELTO, "levantar_hoja",
                    "No hay documento digitalizado cargado para esta carpeta.", quien)
            db.commit()
            return {"error": "sin documento"}

        unidad = (db.query(UnidadInventario)
                    .filter(UnidadInventario.codigo_carpeta == exp.codigo_carpeta).first())
        periodo = db.get(Periodo, exp.periodo_id) if exp.periodo_id else None
        romano = periodo.numero_romano if periodo else (unidad.periodo if unidad else "")

        _huella(db, exp, Estado.EN_PROCESAMIENTO, "levantar_hoja",
                f"El modelo está leyendo {len(archivos)} archivo(s).", quien)
        db.commit()

        contexto = {
            "codigo_carpeta": exp.codigo_carpeta, "periodo": romano,
            "rango_periodo": periodo.rango_texto if periodo else "",
            "asunto": unidad.asunto if unidad else "",
            "folios": unidad.folios if unidad else None,
            "fechas_inventario": (f"{unidad.fecha_inicial} a {unidad.fecha_final}"
                                  if unidad and unidad.fecha_inicial else ""),
        }

        # Las partes de un expediente fraccionado se leen una por una y la numeración de
        # trámites y folios continúa de una a la siguiente, como manda la regla.
        todos: list[dict] = []
        propuestas_por_parte: list[dict] = []
        avisos: list[str] = []
        caracteristicas: list[str] = []
        proveedores: list[str] = []
        ultimo_item, ultimo_folio = 0, 0

        for a in archivos:
            # Se lee la matriz de preservación si ya se construyó, y si no el original. En
            # ninguno de los dos casos se le tocó la imagen: el modelo tiene que ver el papel
            # como está, con sus manchas y su tinta desvanecida. La copia de consulta, que sí
            # está limpiada, no se usa aquí justamente por eso.
            ruta = Path(a.ruta_matriz) if getattr(a, "ruta_matriz", None) else Path(a.ruta)
            if not ruta.exists():
                ruta = Path(a.ruta)
            if not ruta.exists():
                avisos.append(f"No se encontró el archivo {a.nombre_original} en el almacén.")
                continue

            # Los tomos de este fondo pasan de los quinientos folios y ningún proveedor admite
            # un documento así en una sola petición. Antes eso obligaba a partir el archivo a
            # mano y el expediente volvía devuelto sin nada hecho. Ahora lo parte el sistema:
            # el archivo del almacén no se toca, los bloques viven en memoria mientras dura
            # cada petición y la numeración de trámites y folios sigue corrida entre ellos, de
            # modo que sale UNA hoja de control y no se nota por dónde se cortó.
            try:
                paginas_del_archivo = particion.contar_paginas(ruta)
                trozos = particion.bloques(ruta, TOPE_PAGINAS, TOPE_MB, avisos)
            except particion.DocumentoIlegible as e:
                avisos.append(f"{e} Vuelva a generar el archivo y cárguelo de nuevo.")
                continue
            partido = paginas_del_archivo > TOPE_PAGINAS or a.tamano_bytes > TOPE_MB * 1048576

            # Si el reconocimiento óptico dejó texto, se le pasa al modelo como apoyo junto
            # con la imagen. Sobre lo mecanografiado le ahorra descifrar; sobre manuscrito el
            # reconocimiento devuelve poco y la instrucción le dice que mande la imagen. En un
            # archivo partido no se pasa: ese texto es del tomo entero y no del bloque, y
            # apuntarle al modelo folios que no tiene delante es peor que no darle nada.
            from app.services.digitalizacion import texto_reconocido
            apoyo = "" if partido else texto_reconocido(getattr(a, "ruta_texto", None))

            leidos_del_archivo = 0
            trozos = _uno_a_uno(trozos, a.nombre_original, avisos)
            for bloque in trozos:
                leidos_del_archivo += 1
                instruccion = lectura.instruccion_hoja_de_control(contexto, apoyo)
                if partido:
                    instruccion += (
                        f"\n\nESTE ARCHIVO SE ESTÁ LEYENDO POR BLOQUES porque es un tomo muy "
                        f"extenso. Usted está viendo el bloque {bloque.numero}, que son las "
                        f"páginas {bloque.pagina_inicial} a {bloque.pagina_final} de un "
                        f"archivo de {paginas_del_archivo}. Registre ÚNICAMENTE los trámites "
                        "que alcance a ver en estas páginas; los de los demás bloques los "
                        "registra otra lectura y se unen después. No advierta que el "
                        "expediente está incompleto ni que faltan folios por esta razón.")
                if ultimo_item:
                    instruccion += (f"\n\nEsta es una parte posterior del mismo expediente. "
                                    f"Empiece la numeración de trámites en {ultimo_item + 1} y "
                                    f"la de folios en {ultimo_folio + 1}.")

                try:
                    propuesta = modelos.leer_documento(db, bloque.contenido, instruccion,
                                                       contexto.get("folios"), turno)
                except modelos.DocumentoRechazado as e:
                    # No es falta de cuota: el archivo mismo es el que no pasa. Se dice cuál
                    # es la página para que se pueda volver a capturar solo ese tramo.
                    avisos.append(
                        f"Los proveedores rechazaron las páginas {bloque.pagina_inicial} a "
                        f"{bloque.pagina_final} de {a.nombre_original}. Suele ser resolución "
                        f"muy alta o el archivo protegido con contraseña. Detalle: {e}")
                    db.commit()
                    break
                db.commit()
                if not propuesta:
                    if todos:
                        # Ya hay trámites levantados de los bloques anteriores: se conservan y
                        # se avisa hasta dónde se alcanzó a leer, en vez de perder el trabajo.
                        avisos.append(
                            f"La lectura se detuvo en la página {bloque.pagina_inicial} de "
                            f"{a.nombre_original} porque ningún modelo tenía cuota disponible. "
                            "Lo leído hasta ahí quedó guardado; vuelva a levantar la hoja "
                            "mañana para completar el resto.")
                        break
                    _huella(db, exp, Estado.EN_COLA, "levantar_hoja",
                            "Ningún modelo tiene cuota disponible. El expediente espera en la "
                            "cola.", quien)
                    db.commit()
                    return {"error": "sin cuota", "carpeta": exp.codigo_carpeta}

                proveedores.append(propuesta.proveedor)
                propuestas_por_parte.append(propuesta.campos)
                leidos = propuesta.campos.get("tramites") or []
                for t in leidos:
                    ultimo_item += 1
                    t["no_item"] = ultimo_item
                    ultimo_folio = max(ultimo_folio, int(t.get("folio_hasta") or 0))
                    todos.append(t)
                if propuesta.campos.get("alerta"):
                    avisos.append(str(propuesta.campos["alerta"]))
                coincide = str(propuesta.campos.get("coincide_con_el_inventario") or "").lower()
                if coincide in ("no", "parcial") and bloque.numero == 1:
                    avisos.append(
                        f"CONTRASTE CON EL INVENTARIO: {coincide}. "
                        f"{propuesta.campos.get('por_que_no_coincide') or ''} "
                        f"Según el documento se trata de: "
                        f"{propuesta.campos.get('asunto_del_documento') or 'sin determinar'}.")
                if propuesta.campos.get("folios_contados") and not partido:
                    contados = propuesta.campos["folios_contados"]
                    declarados = contexto.get("folios")
                    if declarados and str(contados) != str(declarados):
                        avisos.append(f"El modelo contó {contados} folios y el inventario declara "
                                      f"{declarados}. Cuente el expediente físico.")
                if propuesta.campos.get("caracteristicas_fisicas"):
                    rasgo = str(propuesta.campos["caracteristicas_fisicas"])
                    if rasgo not in caracteristicas:
                        caracteristicas.append(rasgo)
                if propuesta.campos.get("estado_general"):
                    nota = "Estado general: " + str(propuesta.campos["estado_general"])
                    if nota not in avisos:
                        avisos.append(nota)

            if partido and leidos_del_archivo:
                avisos.append(f"{a.nombre_original} tiene {paginas_del_archivo} páginas y se leyó "
                              f"en {leidos_del_archivo} bloques encadenados. La numeración de "
                              "trámites y folios continúa de un bloque al siguiente.")

        if not todos:
            _huella(db, exp, Estado.DEVUELTO, "levantar_hoja",
                    "El modelo no reconoció ningún trámite en el documento. "
                    + " ".join(avisos), quien)
            db.commit()
            return {"error": "sin trámites", "avisos": avisos}

        # Se guarda como PROPUESTA: los trámites quedan escritos, pero la hoja queda en
        # elaboración para que una persona la revise antes de verificarla.
        from app.models import Tramite
        for viejo in list(exp.tramites):
            db.delete(viejo)
        db.flush()
        for t in todos:
            fecha = normalizar_fecha(t.get("fecha"))
            exp.tramites.append(Tramite(
                no_item=int(t.get("no_item") or 0), fecha=fecha.completa, fecha_texto=fecha.texto,
                tipo_documental=(t.get("tipo_documental") or "").strip()[:200],
                folio_desde=int(t.get("folio_desde") or 0) or None,
                folio_hasta=int(t.get("folio_hasta") or 0) or None,
                # La observación pasa por el filtro que quita la contabilidad de folios:
                # esa columna es de estado de conservación, no de cuántos folios hay.
                observaciones=limpiar_observacion(t.get("observaciones")) or None,
                no_radicado=(str(t.get("no_radicado") or "").strip().upper() or "N/A"),
                sistema_informacion="N/A",
                expediente_sgdea="N/A", enlace_acceso="N/A"))

        exp.volumen_folios = ultimo_folio or exp.volumen_folios

        # Si lo contado en el papel no es lo que declara el inventario de origen, queda la
        # constancia en el expediente. De ahí sale a la hoja de control y al inventario de
        # salida F-GDM-003. Manda lo contado; el inventario es solo el contraste.
        declarados = unidad.folios if unidad else None
        if declarados and exp.volumen_folios and declarados != exp.volumen_folios:
            exp.diferencia_folios = (
                f"LOS FOLIOS NO COINCIDEN. La hoja de control suma {exp.volumen_folios} "
                f"folio(s) y el inventario de origen declara {declarados}. Manda lo contado "
                "en el expediente; queda la constancia de la diferencia.")
            avisos.append(exp.diferencia_folios)
        else:
            exp.diferencia_folios = None

        # El nombre del expediente, campo 7 de la hoja, sale de lo que el modelo leyó en el
        # documento y no del asunto del inventario, que puede estar equivocado. Queda marcado
        # como propuesta, igual que todo lo que escribe el modelo.
        #
        # Va el nombre CORTO, no el asunto. El campo 7 es el rótulo del expediente —«Estudios
        # de laboratorio»— y el detalle —los números de las muestras, las fincas, los
        # municipios— va en el tipo documental de cada trámite, que es su sitio. El asunto
        # largo se guarda igual, porque alimenta el alcance y contenido de la descripción.
        if not exp.titulo:
            for p_ in propuestas_por_parte:
                nombre = str(p_.get("nombre_del_expediente") or "").strip()
                if nombre:
                    exp.titulo = "[PROPUESTA DEL MODELO, PENDIENTE DE REVISIÓN] " + nombre
                    break
            else:
                # Si el modelo no lo mandó, se recorta el asunto a su primera idea antes de
                # ponerlo en el campo 7: más vale corto y general que un párrafo en el rótulo.
                for p_ in propuestas_por_parte:
                    asunto = str(p_.get("asunto_del_documento") or "").strip()
                    if asunto:
                        exp.titulo = ("[PROPUESTA DEL MODELO, PENDIENTE DE REVISIÓN] "
                                      + nombre_corto(asunto))
                        break

        # Con los trámites ya leídos se resuelve solo lo que se puede resolver: las fechas
        # extremas, el periodo y la subserie. La persona solo interviene cuando no hay fecha.
        propuesta_periodo, propuesta_tvd = _clasificar(db, exp, unidad, turno)
        if propuesta_periodo:
            detalle_extra = propuesta_periodo
        else:
            detalle_extra = ""
        if caracteristicas and not exp.caracteristicas_fisicas:
            exp.caracteristicas_fisicas = "[PROPUESTA DEL MODELO, PENDIENTE DE REVISIÓN] " + \
                                          " ".join(caracteristicas)
        detalle = (f"El modelo ({', '.join(sorted(set(proveedores)))}) propuso "
                   f"{len(todos)} trámite(s) y {ultimo_folio} folios. Revise antes de verificar.")
        if detalle_extra:
            detalle += " " + detalle_extra
        if propuesta_tvd:
            detalle += " " + propuesta_tvd
        if avisos:
            detalle += " " + " ".join(avisos)
        _huella(db, exp, Estado.HOJA_EN_ELABORACION, "levantar_hoja", detalle, quien)
        db.commit()
        return {"carpeta": exp.codigo_carpeta, "tramites": len(todos),
                "folios": ultimo_folio, "proveedores": sorted(set(proveedores)),
                "periodo": propuesta_periodo, "clasificacion": propuesta_tvd,
                "avisos": avisos}
    finally:
        db.close()


def _clasificar(db, exp, unidad, turno: int | None = None) -> tuple[str, str]:
    """
    Resuelve fechas extremas, periodo y subserie sin gastar modelo.

    Manda la fecha. El periodo sale de las fechas extremas que acaban de leerse del propio
    documento; el inventario de origen solo entra cuando no hay ninguna fecha legible, y en
    ese caso queda marcado como no verificado. Si el inventario decía otro periodo, gana la
    fecha y la diferencia queda escrita en la bitácora y en el tablero de calidad.

    La subserie SIEMPRE queda escogida. La escoge el modelo por el contenido que acaba de
    leer, dentro de la lista cerrada de la tabla de valoración del periodo; si el modelo no
    responde, se escoge por coincidencia de palabras; y si tampoco así, se propone la más
    usada del periodo. Nunca se deja la casilla vacía para que la llene la persona: la
    dirección del proyecto pidió que la plataforma clasifique y que la persona valide.

    Lo que trae el inventario no manda: sirve de contraste. Si el inventario y el contenido
    coinciden, la propuesta sube a confianza alta; si no coinciden, gana el contenido y la
    diferencia queda escrita, igual que se hace con el periodo.
    """
    from app.models import Periodo, Seccion, Serie, Subserie
    from app.services.clasificacion import OpcionTvd
    from app.services.periodos import RangoPeriodo, resolver_periodo

    # 1. Fechas extremas de lo leído, según sea libro empastado o carpeta suelta.
    from app.services.libros import resolver_fechas
    fi, ff, texto, enc, avisos_fechas = resolver_fechas(exp.tramites, unidad, exp.encuadernada)
    exp.fecha_inicial, exp.fecha_final, exp.fechas_texto = fi, ff, texto

    # 2. Periodo
    rangos = [RangoPeriodo(p.numero_romano, p.fecha_inicio, p.fecha_fin)
              for p in db.query(Periodo).order_by(Periodo.orden).all()]
    # La propuesta para una carpeta sin fecha sale de sus compañeras de caja, empezando por
    # la caja de origen que registra el inventario antiguo. Ninguna carpeta queda suelta.
    sugerencia = None
    if unidad:
        from app.routers.expedientes import _sugerir_periodo
        sugerencia = _sugerir_periodo(db, unidad)

    resuelto = resolver_periodo(unidad.periodo if unidad else "", fi, ff, rangos,
                                sugerencia_caja=sugerencia)
    aviso_periodo = " ".join(avisos_fechas)
    if aviso_periodo:
        aviso_periodo += " "
    if resuelto.resuelto:
        periodo = db.query(Periodo).filter(Periodo.numero_romano == resuelto.romano).first()
        if periodo:
            exp.periodo_id = periodo.id
            aviso_periodo += (f"Periodo {resuelto.romano} asignado por {resuelto.origen}."
                             + (" " + resuelto.aviso if resuelto.aviso else ""))
        else:
            aviso_periodo += (f"El periodo {resuelto.romano} que resulta de las fechas no está "
                             "cargado en la plataforma. Revíselo a mano.")
            return aviso_periodo, ""
    else:
        aviso_periodo += ("Sin periodo: el expediente no tiene fechas legibles ni periodo en el "
                         "inventario. " + (resuelto.aviso or "Asígnelo a mano en el editor."))
        return aviso_periodo, ""

    # 3. Subserie, de la lista cerrada del periodo
    # Con la oficina productora, que es lo que distingue dos filas de la tabla que traen los
    # mismos códigos de serie y de subserie.
    opciones = [OpcionTvd(resuelto.romano, se.codigo, se.nombre, su.codigo, su.nombre,
                          su.retencion_central_anios, su.disposicion_final,
                          sec.codigo_dependencia or "", sec.oficina_productora or "")
                for su, se, sec in db.query(Subserie, Serie, Seccion)
                                     .join(Serie, Subserie.serie_id == Serie.id)
                                     .join(Seccion, Serie.seccion_id == Seccion.id)
                                     .join(Periodo, Seccion.periodo_id == Periodo.id)
                                     .filter(Periodo.numero_romano == resuelto.romano).all()]
    if not opciones:
        return aviso_periodo, (f"El periodo {resuelto.romano} no tiene cargada su tabla de "
                               "valoración documental, así que no hay de dónde escoger la "
                               "subserie. Cárguela en Instrumentos.")

    eleccion = elegir_subserie_del_expediente(db, exp, unidad, resuelto.romano, opciones, turno)
    if not eleccion.hay:                       # no debería ocurrir; la red de seguridad igual
        return aviso_periodo, ("No fue posible proponer serie ni subserie. Elíjala en el editor.")

    from app.routers.expedientes import _subserie_de
    sub = _subserie_de(db, eleccion.opcion, resuelto.romano)
    if sub:
        exp.subserie_id = sub.id
    return aviso_periodo, eleccion.frase()


def subseries_mas_usadas(db, romano: str) -> dict:
    """
    Cuántos expedientes de este periodo se han clasificado ya en cada subserie.

    Es la última red: cuando ni el modelo ni las palabras dan una pista, se propone aquello
    en lo que viene cayendo el propio fondo. Vale más que dejar la casilla en blanco, y queda
    marcado como propuesta de confianza baja para que la persona la mire.
    """
    from sqlalchemy import func as f

    from app.models import Expediente, Periodo, Seccion, Serie, Subserie
    filas = (db.query(Seccion.codigo_dependencia, Serie.codigo, Subserie.codigo,
                      f.count(Expediente.id))
               .select_from(Expediente)
               .join(Subserie, Expediente.subserie_id == Subserie.id)
               .join(Serie, Subserie.serie_id == Serie.id)
               .join(Seccion, Serie.seccion_id == Seccion.id)
               .join(Periodo, Seccion.periodo_id == Periodo.id)
               .filter(Periodo.numero_romano == romano)
               .group_by(Seccion.codigo_dependencia, Serie.codigo, Subserie.codigo).all())
    return {f"{dep or ''}|{cs}|{csu}": n for dep, cs, csu, n in filas}


def elegir_subserie_del_expediente(db, exp, unidad, romano: str, opciones: list,
                                   turno: int | None = None, modelo: str = ""):
    """
    Escoge la subserie del expediente dentro de la lista cerrada del periodo. Siempre escoge.

    Tres fuentes, en este orden:

      1. El modelo, con lo que leyó del propio documento. Es la que manda, porque clasificar
         es un juicio sobre el contenido y el contenido es lo que él acaba de leer. Su
         respuesta se comprueba contra la tabla antes de aceptarse: si devuelve una subserie
         que no está en la lista, se descarta como si no hubiera respondido.
      2. La coincidencia de palabras entre lo leído y los nombres de las subseries, que es
         lo que se hacía antes y no gasta cuota.
      3. La subserie más usada del periodo, o la primera de la tabla.

    Lo que trae el inventario entra solo como contraste, nunca como decisión.
    """
    from app.services import modelos
    from app.services.clasificacion import (CONFIANZA_ALTA, Eleccion, Encabezado,
                                            asimilar_encabezado, elegir_de_la_lista,
                                            elegir_por_contenido)
    from app.services.lectura import instruccion_eleccion_subserie

    tramites = [{"no_item": t.no_item, "fecha": t.fecha_texto,
                 "tipo_documental": t.tipo_documental} for t in exp.tramites]

    # Lo que dice el inventario, solo para contrastar.
    del_inventario = None
    if unidad and (unidad.cod_serie or unidad.subserie):
        c = asimilar_encabezado(Encabezado(unidad.cod_serie or "", unidad.serie or "",
                                           unidad.cod_subserie or "", unidad.subserie or ""),
                                opciones)
        del_inventario = c.opcion

    eleccion = Eleccion()
    if tramites:
        contexto = {"codigo_carpeta": exp.codigo_carpeta, "periodo": romano,
                    "asunto": (unidad.asunto if unidad else ""),
                    "asunto_leido": (exp.titulo or "").replace(
                        "[PROPUESTA DEL MODELO, PENDIENTE DE REVISIÓN] ", ""),
                    "fechas_extremas": exp.fechas_texto}
        try:
            respuesta = modelos.elegir_subserie(
                db, instruccion_eleccion_subserie(contexto, opciones, tramites), turno,
                modelo=modelo)
        except Exception:                       # la clasificación no puede tumbar la lectura
            respuesta = None
        if respuesta:
            opcion = elegir_de_la_lista(opciones,
                                        respuesta.campos.get("cod_serie", ""),
                                        respuesta.campos.get("cod_subserie", ""),
                                        respuesta.campos.get("subserie", ""),
                                        respuesta.campos.get("codigo_dependencia", ""))
            if opcion:
                porque = (respuesta.campos.get("porque") or "").strip()
                seguridad = (respuesta.campos.get("seguridad") or "").strip().lower()
                if seguridad not in ("alta", "media", "baja"):
                    seguridad = "media"
                eleccion = Eleccion(opcion,
                                    porque or "por el contenido leído del expediente",
                                    seguridad, "modelo")

    if not eleccion.hay:
        eleccion = elegir_por_contenido(
            opciones,
            [(unidad.asunto if unidad else ""), (exp.titulo or "")] +
            [t["tipo_documental"] or "" for t in tramites],
            subseries_mas_usadas(db, romano))

    # Contraste con el inventario. Manda el contenido; la diferencia queda escrita.
    if del_inventario and eleccion.hay:
        misma = (del_inventario.cod_serie == eleccion.opcion.cod_serie
                 and del_inventario.cod_subserie == eleccion.opcion.cod_subserie)
        if misma:
            eleccion = Eleccion(eleccion.opcion,
                                eleccion.porque + "; coincide con lo que trae el inventario",
                                CONFIANZA_ALTA, eleccion.origen)
        else:
            eleccion = Eleccion(
                eleccion.opcion,
                eleccion.porque + (f"; el inventario decía {del_inventario.cod_serie} "
                                   f"{del_inventario.cod_subserie} {del_inventario.subserie}, "
                                   "manda el contenido"),
                eleccion.confianza, eleccion.origen)
    return eleccion


@celery_app.task(name="kustos.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="kustos.preparar_digitalizacion", bind=True, max_retries=1)
def preparar_digitalizacion(self, archivo_id: int) -> dict:
    """
    Construye la matriz de preservación y la copia de consulta de un archivo cargado.

    La matriz va a PDF/A con las imágenes intactas: es la reproducción fiel del original y
    es la que lee el modelo, porque conserva las manchas, los dobleces y la tinta desvanecida
    que alimentan las observaciones de la hoja de control.

    La copia de consulta se endereza, se le quitan los bordes del escáner, se rotan las
    páginas acostadas y se le agrega la capa de texto buscable. Nunca sustituye a la matriz.

    Si el equipo no tiene instalado el motor de imagen, la tarea lo deja anotado y no falla:
    el expediente sigue su curso con el archivo original, que es lo que importa.
    """
    from app.models import Archivo
    from app.services import digitalizacion as dig

    db = SesionLocal()
    try:
        a = db.get(Archivo, archivo_id)
        if not a:
            return {"error": "el archivo ya no existe"}
        origen = Path(a.ruta)
        if not origen.exists():
            a.error_proceso = "El archivo no está en el almacén."
            db.commit()
            return {"error": "sin archivo"}

        if not dig.disponible():
            a.error_proceso = ("El equipo no tiene instalado el motor de procesamiento de "
                               "imagen, así que no se generaron la matriz PDF/A ni la copia "
                               "de consulta. El expediente sigue su curso con el original.")
            db.commit()
            return {"error": "sin motor de imagen", "archivo": a.nombre_original}

        base = origen.parent / "preservacion"
        matriz = base / f"{origen.stem}_matriz.pdf"
        consulta = base / f"{origen.stem}_consulta.pdf"
        problemas = []

        bien, detalle = dig.matriz_de_preservacion(origen, matriz)
        if bien:
            a.ruta_matriz = str(matriz)
        else:
            problemas.append(f"Matriz de preservación: {detalle}")

        bien, detalle = dig.copia_de_consulta(origen, consulta, con_ocr=not a.tiene_capa_de_texto)
        if bien:
            a.ruta_consulta = str(consulta)
            texto = consulta.with_suffix(".txt")
            if texto.exists():
                a.ruta_texto = str(texto)
        else:
            problemas.append(f"Copia de consulta: {detalle}")

        a.procesado_en = datetime.now()
        a.error_proceso = " | ".join(problemas) or None
        db.commit()
        return {"archivo": a.nombre_original, "matriz": a.ruta_matriz,
                "consulta": a.ruta_consulta, "problemas": problemas}
    finally:
        db.close()


def _uno_a_uno(trozos, nombre: str, avisos: list):
    """
    Envuelve el recorrido de los bloques para que un archivo dañado a mitad de camino no
    tumbe la lectura entera: se anota hasta dónde se pudo leer y lo anterior se conserva.
    """
    from app.services.particion import DocumentoIlegible
    try:
        for bloque in trozos:
            yield bloque
    except DocumentoIlegible as e:
        avisos.append(f"{e} La lectura de {nombre} se detuvo ahí.")
    except Exception as e:                                  # archivo truncado a mitad
        avisos.append(f"No se pudo seguir leyendo {nombre}: {type(e).__name__}.")
