"""
Cargue de archivos.

Hoy el archivo se sube al servidor y este lo guarda en disco. Cuando se conecte el
almacenamiento de objetos, el navegador subirá directo allá con una dirección prefirmada y
el servidor solo registrará el archivo; el resto de esta capa no cambia.

Lo que sí funciona desde ya, y es lo que evita cargar a ciegas: se reconoce el código de
carpeta del nombre, se comprueba contra el inventario de origen (R3), se detecta el archivo
repetido por su huella (R46) y se registra el expediente en cola con su trazabilidad.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from geology.nucleo.bd import obtener_sesion
from geology.modelos import Archivo, Expediente, Trazabilidad, UnidadInventario
from geology.rutas.cuentas import usuario_actual
from geology.dominio.codigos import partes_de_archivo
from geology.dominio.estados import Estado, Usuario, motivo_de_rechazo_de_carga

router = APIRouter(prefix="/cargue", tags=["Cargue"])

ALMACEN = Path("deposito")
TROZO = 1024 * 1024


def es_el_mismo_fichero(uno: Path, otro: str | Path) -> bool:
    """
    Si dos rutas señalan el mismo fichero del almacén.

    Se usa antes de borrar «la copia sobrante» de una carga repetida. Volver a subir el mismo
    archivo escribe sobre el mismo nombre, así que lo recién escrito y lo ya registrado son
    el mismo fichero: borrarlo ahí dejaba al expediente figurando cargado con el documento
    desaparecido del disco.
    """
    try:
        return uno.resolve() == Path(otro).resolve()
    except OSError:
        return str(uno) == str(otro)


def _limpiar(nombre: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", nombre.strip())[:120] or "archivo"


@router.post("/cargar", summary="Cargar un expediente digitalizado")
async def cargar(archivo: UploadFile = File(...), db: Session = Depends(obtener_sesion),
                 quien: Usuario = Depends(usuario_actual)) -> dict:
    if not quien.edita_hoja_control:
        raise HTTPException(403, "Su perfil es de consulta y no carga expedientes.")

    partes = partes_de_archivo(archivo.filename or "")
    if not partes.carpeta:
        raise HTTPException(422, f"El nombre «{archivo.filename}» no permite deducir el código de "
                                 "carpeta. Renómbrelo como AC-CP-00374.pdf, o CARPETA_00374.pdf.")
    carpeta = partes.carpeta

    unidad = db.query(UnidadInventario).filter(UnidadInventario.codigo_carpeta == carpeta).first()
    if not unidad:
        raise HTTPException(422, f"La carpeta {carpeta} no está en el inventario de origen del "
                                 "contrato, es decir no pertenece a la selección inventariada.")

    exp = db.query(Expediente).filter(Expediente.codigo_carpeta == carpeta).first()

    # Un expediente se carga entero o por partes, nunca de las dos maneras a la vez: si ya
    # hay partes registradas no entra un archivo entero, y si ya está el entero no entra una
    # parte suelta. Mezclarlos haría que la lectura tomara el mismo papel dos veces.
    existentes = db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta).all()
    existentes = [a for a in existentes if Path(a.ruta).exists()]
    if existentes and not partes.es_fragmento and any(a.fragmento > 0 for a in existentes):
        raise HTTPException(409, f"{carpeta} ya está cargada por partes "
                                 f"({len(existentes)} archivo(s)). Cargue la parte que falte con su "
                                 "número (por ejemplo CARPETA-00001-4.pdf) o retire el expediente "
                                 "para volver a cargarlo entero.")
    if existentes and partes.es_fragmento and any(a.fragmento == 0 for a in existentes):
        raise HTTPException(409, f"{carpeta} ya está cargada completa en un solo archivo. Si el "
                                 "expediente viene por partes, retire el expediente y cargue "
                                 "todas las partes numeradas.")

    if exp and not partes.es_fragmento:
        from geology.dominio.estados import Expediente as ExpedienteCalculo
        rechazo = motivo_de_rechazo_de_carga(
            ExpedienteCalculo(exp.codigo_carpeta, Estado(exp.estado), describio=exp.describio))
        if rechazo:
            raise HTTPException(409, rechazo)

    # Se guarda por trozos, de modo que un expediente grande no se cargue entero en memoria.
    ALMACEN.mkdir(parents=True, exist_ok=True)
    sufijo = f"_{partes.fragmento}" if partes.es_fragmento else ""
    destino = ALMACEN / f"{carpeta}{sufijo}_{_limpiar(archivo.filename or 'archivo')}"
    huella = hashlib.sha256()
    tamano = 0
    with destino.open("wb") as salida:
        while True:
            trozo = await archivo.read(TROZO)
            if not trozo:
                break
            huella.update(trozo)
            tamano += len(trozo)
            salida.write(trozo)
    sha = huella.hexdigest()

    # El guardián de duplicados no debe tropezar con fantasmas: un registro cuyo archivo ya no
    # está en el almacén no es un duplicado, es un rastro de una carga que se perdió. Si se
    # rechazara la nueva carga, la carpeta quedaría bloqueada para siempre sin forma de
    # arreglarla desde la interfaz.
    from sqlalchemy import or_ as _or
    repetido = db.query(Archivo).filter(_or(Archivo.sha256 == sha,
                                            Archivo.sha256_origen == sha)).first()
    if repetido and Path(repetido.ruta).exists():
        # OJO con este borrado. Volver a subir EL MISMO archivo escribe sobre el mismo
        # nombre en el almacén, de modo que lo que se acaba de escribir y lo que ya estaba
        # registrado son el mismo fichero. Borrar «la copia sobrante» borraba entonces el
        # original y dejaba el registro apuntando a la nada: el expediente aparecía cargado
        # y el archivo ya no estaba. Por eso solo se borra cuando de verdad son dos rutas
        # distintas, que es el caso de subir el mismo escaneo con otro nombre.
        if not es_el_mismo_fichero(destino, repetido.ruta):
            destino.unlink(missing_ok=True)
        raise HTTPException(409, f"DUPLICADO. Este mismo archivo ya se cargó como "
                                 f"«{repetido.nombre_original}» el "
                                 f"{repetido.subido_en:%Y-%m-%d a las %H:%M}. "
                                 f"El que ya estaba guardado no se tocó.")
    if repetido:
        db.delete(repetido)
        db.flush()

    # Y los demás rastros de esta misma carpeta cuyo archivo tampoco esté: se retiran, para
    # que el expediente no arrastre registros que apuntan a la nada.
    for viejo in db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta).all():
        if not Path(viejo.ruta).exists():
            db.delete(viejo)
    db.flush()

    if exp and exp.estado == Estado.DEVUELTO.value:
        # Estaba devuelto porque no había con qué leerlo. Ahora sí lo hay: vuelve a la cola.
        db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                            estado_nuevo=Estado.EN_COLA.value, accion="cargar",
                            usuario=quien.nombre,
                            motivo=f"Se cargó de nuevo el documento {archivo.filename}."))
        exp.estado = Estado.EN_COLA.value

    if not exp:
        exp = Expediente(codigo_carpeta=carpeta, estado=Estado.EN_COLA.value,
                         caja_origen=unidad.caja_origen, caja_trabajo=unidad.caja_trabajo,
                         responsable=quien.nombre, archivo_origen=archivo.filename)
        db.add(exp)
        db.flush()
        db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=None,
                            estado_nuevo=Estado.EN_COLA.value, accion="cargar",
                            usuario=quien.nombre,
                            motivo=f"Documento digitalizado {archivo.filename}"))

    # Recepción técnica. Se mide el archivo antes de que el expediente avance, porque la
    # resolución es un parámetro de captura: si llegó por debajo del mínimo hay que volver a
    # escanear, y eso conviene saberlo hoy y no cuando se entregue.
    from geology.dominio.recepcion_tecnica import UMBRAL_DPI, leer_ficha
    from geology.dominio import division
    ficha = leer_ficha(destino)

    # Un documento de gran volumen que llega entero —un libro de mil imágenes en un solo
    # archivo— se divide aquí en partes consecutivas. Cada parte queda registrada con el
    # rango de páginas del original que abarca, así que el orden de las imágenes se conserva
    # y se puede demostrar; la lectura después las toma en ese orden con la numeración de
    # trámites y folios corrida, exactamente igual que si hubieran llegado nombradas -1, -2.
    registros: list[Archivo] = []
    division_hecha = None
    if (not partes.es_fragmento and ficha.paginas and division.hay_que_dividir(ficha.paginas)
            and not db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta,
                                             Archivo.fragmento > 0).count()):
        try:
            cortadas = division.dividir(destino, carpeta, ALMACEN,
                                        _limpiar(archivo.filename or "archivo"))
        except Exception as e:
            cortadas = []
            print(f"AVISO. No se pudo dividir {archivo.filename}: {e}. Se registra entero.")
        if cortadas:
            for parte in cortadas:
                ficha_parte = leer_ficha(parte.ruta)
                registros.append(Archivo(
                    expediente_id=exp.id, codigo_carpeta=carpeta, fragmento=parte.numero,
                    nombre_original=f"{archivo.filename} (parte {parte.numero}, páginas "
                                    f"{parte.pagina_inicial}-{parte.pagina_final})",
                    ruta=str(parte.ruta), tamano_bytes=parte.tamano_bytes, sha256=parte.sha256,
                    sha256_origen=sha, subido_por=quien.nombre,
                    paginas=parte.paginas, dpi_minimo=ficha_parte.dpi_minimo,
                    dpi_medio=ficha_parte.dpi_medio, bits_por_color=ficha_parte.bits_por_color,
                    tiene_capa_de_texto=ficha_parte.tiene_capa_de_texto,
                    avisos_tecnicos=" | ".join(ficha_parte.avisos) or None,
                    pagina_inicial=parte.pagina_inicial, pagina_final=parte.pagina_final,
                    dividido_por_sistema=True))
            # El archivo entero ya está íntegro en sus partes, página por página; se retira
            # del depósito para no guardarlo dos veces. Su huella queda en cada parte.
            destino.unlink(missing_ok=True)
            division_hecha = (f"El documento {archivo.filename} tiene {ficha.paginas} páginas "
                              f"y el sistema lo dividió en {len(cortadas)} partes consecutivas "
                              f"de hasta {division.PAGINAS_POR_PARTE} páginas, conservando el "
                              f"orden de las imágenes. Huella del archivo entero: {sha[:16]}…")
    if not registros:
        registros.append(Archivo(
            expediente_id=exp.id, codigo_carpeta=carpeta, fragmento=partes.fragmento,
            nombre_original=archivo.filename or "", ruta=str(destino),
            tamano_bytes=tamano, sha256=sha, subido_por=quien.nombre,
            paginas=ficha.paginas or None, dpi_minimo=ficha.dpi_minimo, dpi_medio=ficha.dpi_medio,
            bits_por_color=ficha.bits_por_color,
            tiene_capa_de_texto=ficha.tiene_capa_de_texto,
            avisos_tecnicos=" | ".join(ficha.avisos) or None))
    db.add_all(registros)
    db.flush()
    registro = registros[0]

    if division_hecha:
        db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                            estado_nuevo=exp.estado, accion="dividir_documento",
                            usuario=quien.nombre, motivo=division_hecha))
    if ficha.avisos or ficha.error:
        db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                            estado_nuevo=exp.estado, accion="recepcion_tecnica",
                            usuario=quien.nombre,
                            motivo=(ficha.error + " " if ficha.error else "")
                                   + " ".join(ficha.avisos)))

    # Si llegó una parte y en la secuencia falta alguna, queda dicho desde ya.
    fragmentos = [a.fragmento for a in
                  db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta).all()]
    faltan = division.faltantes(fragmentos)
    if faltan:
        db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                            estado_nuevo=exp.estado, accion="secuencia",
                            usuario=quien.nombre,
                            motivo=f"Faltan las partes {', '.join(map(str, faltan))} de "
                                   f"{carpeta}. La lectura las toma en orden cuando lleguen."))
    db.commit()

    # La matriz de preservación y la copia de consulta se construyen en segundo plano: son
    # pesadas y no tienen por qué hacer esperar a quien está cargando.
    for r in registros:
        try:
            from geology.trabajos import preparar_digitalizacion
            preparar_digitalizacion.delay(r.id)
        except Exception as e:
            print(f"AVISO. No se pudo encolar la preparación del archivo {r.id}: {e}")

    # Y el levantamiento de la hoja de control arranca solo. Nadie tiene que pulsar nada: se
    # sube la carpeta y el modelo empieza a leerla.
    #
    # Se espera un poco antes de empezar. Un expediente partido llega como _1, _2 y _3 con
    # segundos de diferencia, y la tarea lee TODAS las partes que encuentre: sin esa espera se
    # leería tres veces, la primera con una sola parte. La espera se cambia con SEGUNDOS_ANTES
    # _DE_LEER y el arranque automático se apaga con LEVANTAR_AL_CARGAR=no.
    levantado = False
    if os.getenv("LEVANTAR_AL_CARGAR", "si").strip().lower() not in ("no", "0", "false"):
        if exp.estado in (Estado.EN_COLA.value, Estado.DEVUELTO.value,
                          Estado.HOJA_EN_ELABORACION.value):
            try:
                from geology.modelos import Trazabilidad as _T
                turno = (db.query(func.count(_T.id))
                           .filter(_T.accion == "levantar_hoja").scalar() or 0)
                from geology.trabajos import levantar_hoja_de_control
                levantar_hoja_de_control.apply_async(
                    args=[exp.id, quien.nombre, turno],
                    countdown=int(os.getenv("SEGUNDOS_ANTES_DE_LEER", "45")))
                levantado = True
            except Exception as e:
                print(f"AVISO. No se pudo encolar el levantamiento de {carpeta}: {e}")

    partes_cargadas = db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta).count()
    return {
        "carpeta": carpeta,
        "fragmento": partes.fragmento,
        "partes_cargadas": partes_cargadas,
        "dividido_por_sistema": bool(division_hecha),
        "partes_del_sistema": [{"parte": r.fragmento, "paginas": f"{r.pagina_inicial}-{r.pagina_final}"}
                               for r in registros] if division_hecha else [],
        "partes_faltantes": faltan,
        "estado": exp.estado,
        "tamano_mb": round(tamano / 1048576, 2),
        "periodo_inventario": unidad.periodo or "sin periodo (S/F)",
        "folios_inventario": unidad.folios,
        "asunto_inventario": unidad.asunto,
        "caja_origen": unidad.caja_origen,
        "ficha_tecnica": ficha.como_dict(),
        "levantamiento_automatico": levantado,
        "mensaje": (f"Expediente {carpeta} registrado. El modelo empieza a leerlo en unos "
                    "segundos y la hoja de control aparecerá diligenciada en «Hojas de control»."
                    if levantado else
                    f"Expediente {carpeta} registrado en cola. Diligencie su hoja de control en "
                    "la pestaña Hojas de control."),
    }


def _cuerpo_de(h, e: dict, nombre: str, quien, verificar: bool):
    """
    Arma la hoja de control a partir de lo que se leyó del libro.

    Va en su propia función para poder envolverla: aquí es donde cada casilla se comprueba, y
    una sola que no pase —un número donde iba texto, un campo más largo de lo que admite—
    levantaba una excepción que tumbaba la carga entera del lote sin decir cuál hoja fue.
    """
    from geology.rutas.unidades import HojaDeControl, TramiteEntrada
    return HojaDeControl(
        codigo_carpeta=h.codigo_carpeta, archivo_origen=nombre,
        codigo_serie=e.get("codigo_serie", ""), serie=e.get("serie", ""),
        codigo_subserie=e.get("codigo_subserie", ""), subserie=e.get("subserie", ""),
        nombre_expediente=e.get("nombre_expediente", ""),
        responsable=quien.nombre,
        fecha_diligenciamiento=e.get("fecha_diligenciamiento", ""),
        periodo_manual=e.get("periodo") or None,
        modo="verificar" if verificar else "avance",
        tramites=[TramiteEntrada(
            no_item=int(t["no_item"]) if str(t.get("no_item", "")).strip().isdigit() else None,
            fecha=t.get("fecha") or None, tipo_documental=t.get("tipo_documental", ""),
            folio_desde=t.get("folio_desde") or None, folio_hasta=t.get("folio_hasta") or None,
            no_radicado=t.get("no_radicado", ""),
            sistema_informacion=t.get("sistema_informacion", ""),
            expediente_sgdea=t.get("expediente_sgdea", ""),
            enlace_acceso=t.get("enlace_acceso", ""),
            observaciones=t.get("observaciones", ""), fila=t.get("fila"))
            for t in h.tramites])


@router.post("/hoja-de-control", summary="Importar hojas de control diligenciadas en Excel")
async def importar_hoja(archivo: UploadFile = File(...), verificar: bool = True,
                        db: Session = Depends(obtener_sesion),
                        quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    Sube un libro de cálculo con una o varias hojas de control ya diligenciadas y las mete al
    flujo, verificándolas con las mismas reglas que las que se diligencian aquí.

    El trabajo hecho fuera de la plataforma no se vuelve a escribir: se importa y se le hace
    calidad. Lo que esté mal sale señalado con el número del trámite y la fila del Excel.
    """
    if not quien.edita_hoja_control:
        raise HTTPException(403, "Su perfil es de consulta y no carga hojas de control.")

    nombre = archivo.filename or "hoja.xlsx"
    if not nombre.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(422, f"«{nombre}» no es un libro de cálculo. Se admiten .xlsx y .xlsm.")

    ALMACEN.mkdir(parents=True, exist_ok=True)
    destino = ALMACEN / f"hojas_{_limpiar(nombre)}"
    with destino.open("wb") as salida:
        while True:
            trozo = await archivo.read(TROZO)
            if not trozo:
                break
            salida.write(trozo)

    from geology.rutas.unidades import HojaDeControl, TramiteEntrada, cargar_hoja
    from geology.dominio.importar_hoja import leer_libro

    resultados, rechazadas = [], []

    # Leer el libro va aparte y con su propia red: un archivo dañado, protegido con
    # contraseña o con una hoja que openpyxl no entienda no puede llegar a la pantalla como
    # «Internal Server Error», que es un mensaje que no le sirve a nadie.
    try:
        hojas = leer_libro(destino, nombre)
    except Exception as ex:
        raise HTTPException(422, (
            f"No se pudo leer «{nombre}» ({type(ex).__name__}). Suele pasar cuando el "
            "archivo quedó a medio descargar, está protegido con contraseña, o se guardó en "
            "un formato que no es el actual de Excel. Ábralo, use «Guardar como» → Libro de "
            f"Excel (*.xlsx) y vuelva a subirlo. Detalle: {str(ex)[:180]}"))

    for h in hojas:
        if h.error:
            rechazadas.append({"hoja": h.hoja or nombre, "motivo": h.error})
            continue
        if not h.codigo_carpeta:
            rechazadas.append({"hoja": h.hoja, "motivo": " ".join(h.avisos)
                               or "No se pudo deducir el código de carpeta."})
            continue
        if not h.tramites:
            rechazadas.append({"hoja": h.hoja, "carpeta": h.codigo_carpeta,
                               "motivo": "La pestaña no trae trámites con datos."})
            continue

        e = h.encabezado
        try:
            cuerpo = _cuerpo_de(h, e, nombre, quien, verificar)
        except Exception as ex:
            # Armar el cuerpo valida cada casilla. Si una no pasa, se dice cuál hoja y por
            # qué, y se sigue con las demás: una hoja mala no puede tumbar el lote entero.
            rechazadas.append({
                "hoja": h.hoja, "carpeta": h.codigo_carpeta,
                "motivo": f"Los datos de esta hoja no pasaron la comprobación "
                          f"({type(ex).__name__}). Detalle: {str(ex)[:220]}"})
            continue
        try:
            r = cargar_hoja(cuerpo, db, quien)
            r["hoja"] = h.hoja
            r["avisos_de_lectura"] = h.avisos
            resultados.append(r)
        except HTTPException as ex:
            rechazadas.append({"hoja": h.hoja, "carpeta": h.codigo_carpeta,
                               "motivo": str(ex.detail)})
        except Exception as ex:
            db.rollback()
            rechazadas.append({
                "hoja": h.hoja, "carpeta": h.codigo_carpeta,
                "motivo": f"No se pudo guardar esta hoja ({type(ex).__name__}). "
                          f"Detalle: {str(ex)[:200]}"})

    con_errores = sum(1 for r in resultados if r.get("errores"))
    return {
        "archivo": nombre,
        "hojas_leidas": len(resultados) + len(rechazadas),
        "importadas": len(resultados),
        "con_errores": con_errores,
        "rechazadas": rechazadas,
        "resultados": resultados,
        "mensaje": (f"{len(resultados)} hoja(s) importada(s); {con_errores} con errores por "
                    f"corregir y {len(rechazadas)} que no se pudieron leer."),
    }


@router.get("/ver/{codigo_carpeta}", summary="El documento digitalizado, para verlo en pantalla")
def ver_documento(codigo_carpeta: str, parte: int = 0, copia: str = "original",
                  db: Session = Depends(obtener_sesion),
                  quien: Usuario = Depends(usuario_actual)):
    """
    Devuelve el expediente digitalizado para poder mirarlo mientras se corrige la hoja.

    Corregir una foliación o una fecha sin tener el papel a la vista es adivinar. Hasta ahora
    había que salir de la plataforma, buscar el archivo en el disco del servidor y abrirlo
    aparte; con esto se abre al lado de la hoja.

    Se puede pedir la copia de consulta, que está enderezada y con texto buscable, o el
    original tal como se cargó. Por omisión va el original, porque es contra el original que
    se comprueba lo que dice la hoja.
    """
    from fastapi.responses import FileResponse

    from geology.dominio.codigos import normalizar_codigo_carpeta

    carpeta = normalizar_codigo_carpeta(codigo_carpeta) or codigo_carpeta.upper()
    consulta = db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta)
    if parte:
        consulta = consulta.filter(Archivo.fragmento == parte)
    registro = consulta.order_by(Archivo.fragmento).first()
    if not registro:
        raise HTTPException(404, f"{carpeta} no tiene ningún documento cargado.")

    candidatas = []
    if copia == "consulta" and registro.ruta_consulta:
        candidatas.append(registro.ruta_consulta)
    candidatas += [registro.ruta, registro.ruta_matriz, registro.ruta_consulta]
    ruta = next((Path(r) for r in candidatas if r and Path(r).exists()), None)
    if not ruta:
        raise HTTPException(404, f"El archivo de {carpeta} figura cargado pero no está en el "
                                 "almacén del servidor. Vuelva a subirlo en la pantalla de Cargue.")

    return FileResponse(ruta, media_type="application/pdf",
                        headers={"Content-Disposition":
                                 f'inline; filename="{carpeta}.pdf"'})


@router.get("/partes/{codigo_carpeta}", summary="Cuántas partes tiene el expediente")
def partes_del_expediente(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
                          quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    """Los archivos de una carpeta, para poder pasar de una parte a otra en el visor."""
    from geology.dominio.codigos import normalizar_codigo_carpeta
    carpeta = normalizar_codigo_carpeta(codigo_carpeta) or codigo_carpeta.upper()
    return [{"fragmento": a.fragmento, "nombre": a.nombre_original,
             "paginas": a.paginas, "en_disco": Path(a.ruta).exists(),
             "tiene_copia_de_consulta": bool(a.ruta_consulta and Path(a.ruta_consulta).exists())}
            for a in db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta)
                       .order_by(Archivo.fragmento).all()]


@router.get("/estado-de-cargas",
            summary="Todo lo que se ha subido y en qué va cada cosa")
def estado_de_cargas(db: Session = Depends(obtener_sesion),
                     quien: Usuario = Depends(usuario_actual)) -> dict:
    """
    El recuento de todo lo cargado, para poder responder la pregunta que importa cuando se
    lleva días subiendo carpetas: ¿se perdió algo?

    Se cruzan tres cosas que hasta ahora solo se miraban por separado y por eso nadie sabía
    si cuadraban: lo que hay REGISTRADO en la base, lo que hay de verdad EN EL DISCO del
    servidor, y en qué ESTADO va cada expediente.

    De ese cruce salen las tres formas en que algo se puede «perder», y conviene distinguirlas
    porque se arreglan distinto:

      · Registrado pero sin archivo. El expediente figura cargado y el archivo no está en el
        almacén. Pasa cuando se reinstaló el contenedor sin conservar la carpeta, o cuando
        una carga quedó a medias. Se resuelve volviendo a subir ese archivo.
      · Archivo sin registrar. El documento está en el disco pero no le corresponde ningún
        expediente. Pasa cuando alguien copia archivos a mano a la carpeta del almacén en vez
        de subirlos por la plataforma. Se resuelve subiéndolo por la pantalla de Cargue.
      · Cargado pero sin leer. El archivo está y el expediente existe, pero nadie ha levantado
        su hoja de control. No está perdido: está esperando turno.
    """
    from geology.dominio.estados import Estado as E

    archivos = db.query(Archivo).order_by(Archivo.codigo_carpeta, Archivo.fragmento).all()
    expedientes = {e.codigo_carpeta: e for e in db.query(Expediente).all()}

    # Cuántos trámites tiene levantados cada expediente, en una sola consulta.
    from geology.modelos import Tramite
    conteo = dict(db.query(Tramite.expediente_id, func.count(Tramite.id))
                    .group_by(Tramite.expediente_id).all())

    detalle = []
    en_disco = faltan = 0
    rutas_registradas = set()

    for a in archivos:
        ruta = Path(a.ruta)
        existe = ruta.exists()
        rutas_registradas.add(ruta.name)
        if existe:
            en_disco += 1
        else:
            faltan += 1
        exp = expedientes.get(a.codigo_carpeta)
        ultimo = ""
        if exp and exp.trazabilidad:
            ultimo = (exp.trazabilidad[-1].motivo or "")[:160]
        detalle.append({
            "carpeta": a.codigo_carpeta,
            "archivo": a.nombre_original,
            "fragmento": a.fragmento,
            "mb": round((a.tamano_bytes or 0) / 1048576, 2),
            "paginas": a.paginas,
            "subido_por": a.subido_por or "",
            "subido_en": a.subido_en.isoformat(timespec="minutes") if a.subido_en else "",
            "en_disco": existe,
            "estado": exp.estado if exp else "sin expediente",
            "tramites": conteo.get(exp.id, 0) if exp else 0,
            "folios": (exp.volumen_folios if exp else None),
            "ultimo_movimiento": ultimo,
            "que_hacer": _que_hacer(existe, exp, conteo.get(exp.id, 0) if exp else 0),
        })

    # Lo que está en el disco y nadie registró.
    huerfanos = []
    if ALMACEN.exists():
        for ruta in sorted(ALMACEN.glob("*.pdf")) + sorted(ALMACEN.glob("*.PDF")):
            if ruta.name not in rutas_registradas:
                huerfanos.append({"archivo": ruta.name,
                                  "mb": round(ruta.stat().st_size / 1048576, 2),
                                  "que_hacer": "Está en el disco pero no se registró. Súbalo "
                                               "por la pantalla de Cargue para que entre al flujo."})

    fechas = sorted(d["subido_en"] for d in detalle if d["subido_en"])
    sin_leer = sum(1 for d in detalle if d["en_disco"] and d["tramites"] == 0)
    carpetas = {d["carpeta"] for d in detalle}
    terminadas = sum(1 for c in carpetas
                     if c in expedientes and expedientes[c].estado in
                     (E.ARCHIVADO.value, E.EN_INVENTARIO.value))

    return {
        "resumen": {
            "archivos_cargados": len(archivos),
            "carpetas_distintas": len(carpetas),
            "en_disco": en_disco,
            "faltan_en_disco": faltan,
            "sin_registrar": len(huerfanos),
            "sin_leer": sin_leer,
            "terminadas": terminadas,
            # Entre qué fechas se subió todo esto. Es lo que permite decir «el sistema tiene
            # esto» en una frase, sin tener que recorrer la lista.
            "primera_carga": fechas[0] if fechas else "",
            "ultima_carga": fechas[-1] if fechas else "",
            "folios_registrados": sum((expedientes[c].volumen_folios or 0)
                                      for c in carpetas if c in expedientes),
        },
        "detalle": detalle,
        "huerfanos": huerfanos,
    }


def _que_hacer(existe: bool, exp, tramites: int) -> str:
    """Una frase por renglón que diga qué sigue, sin obligar a interpretar el estado."""
    from geology.dominio.estados import Estado as E
    if not exp:
        return ("El archivo está registrado pero no le corresponde ningún expediente. "
                "Vuelva a subirlo por la pantalla de Cargue.")
    if not existe:
        return ("El archivo NO está en el almacén del servidor. Vuelva a subirlo en Cargue: "
                "el registro se reemplaza y no se duplica.")
    if exp.estado == E.EN_PROCESAMIENTO.value:
        return "El modelo lo está leyendo en este momento. Espere."
    if exp.estado == E.DEVUELTO.value:
        return "Tiene errores señalados. Ábralo en Hojas de control y corrija."
    if tramites == 0:
        return "Está cargado pero nadie ha levantado su hoja. Pulse «Levantar con el modelo»."
    if exp.estado == E.HOJA_EN_ELABORACION.value:
        return "El modelo propuso la hoja. Revísela y pulse «Guardar y verificar»."
    if exp.estado == E.HOJA_POR_REVISAR.value:
        return "Espera que una persona la revise y pulse «Marcar revisada»."
    if exp.estado == E.HOJA_REVISADA.value:
        return "Lista para generar el ISAD(G)."
    if exp.estado == E.DESCRIPCION_POR_VALIDAR.value:
        return "Espera validación de la descripción."
    if exp.estado == E.DESCRIPCION_VALIDADA.value:
        return "Espera aprobación de la dirección o la líder."
    if exp.estado == E.ARCHIVADO.value:
        return "Aprobada. Falta asignarle caja definitiva en Reubicación."
    if exp.estado == E.EN_INVENTARIO.value:
        return "Terminada: ya está en el inventario de salida."
    return "En cola."


@router.get("/de/{codigo_carpeta}", summary="Archivos cargados de una carpeta")
def de_carpeta(codigo_carpeta: str, db: Session = Depends(obtener_sesion),
               quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    carpeta = (partes_de_archivo(codigo_carpeta).carpeta or codigo_carpeta.upper())
    return [{"nombre": a.nombre_original, "parte": a.fragmento,
             "tamano_mb": round(a.tamano_bytes / 1048576, 2),
             "subido_por": a.subido_por, "subido_en": a.subido_en.isoformat(timespec="minutes")}
            for a in db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta)
                       .order_by(Archivo.fragmento).all()]
