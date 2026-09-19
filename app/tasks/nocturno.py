"""
El turno de noche: tres tandas, por orden de utilidad.

POR QUÉ TRES Y NO UNA. De noche el computador puede hacer todo lo que sea texto contra texto,
que es más que solo redactar. Pero conviene no engañarse: más tareas NO es más rendimiento. La
máquina rinde lo que rinde, y agregar tareas reparte esa misma capacidad, no la multiplica.
Lo que sí cambia el resultado es el ORDEN, porque determina en qué se gasta la capacidad
cuando no alcanza para todo. Por eso las tandas van así:

  1. CLASIFICAR   los expedientes leídos que quedaron sin subserie o con la subserie dudosa.
                  Es la tanda más barata de las tres y la que desbloquea a las otras dos: sin
                  subserie no se puede describir, así que un expediente atascado aquí atasca
                  todo lo que viene detrás. Va primero por eso, no por rápida.
  2. DESCRIBIR    las hojas ya revisadas por una persona. Es el grueso y lo que usted espera
                  encontrar en la mañana.
  3. REVISAR      las descripciones que nunca pasaron por el revisor, empezando por las más
                  viejas. Es el relleno: si las dos primeras colas se vacían, la noche no se
                  desperdicia, y si no alcanza, no se pierde nada porque son descripciones
                  que ya estaban hechas.

MODELOS DISTINTOS PARA TAREAS DISTINTAS. Clasificar y revisar salen bien con un modelo
pequeño, que es alrededor del doble de rápido; la redacción conviene dejársela a uno más
grande, porque ahí sí se nota la prosa. Se configura con MODELO_CLASIFICAR, MODELO_DESCRIBIR
y MODELO_REVISAR en el archivo .env. Si el modelo pedido no está descargado no se falla: se
usa cualquiera de los locales.

LO QUE NO CAMBIA. No lee escaneos: eso necesita visión, sale a la nube, es la tarea cara, y
dejarla corriendo sin nadie delante es la forma más rápida de amanecer sin cuota. No aprueba
ni valida nada. Todo lo que produzca queda marcado como propuesta, esperando revisión de una
persona. Y si el modelo local no está disponible, el turno se detiene en vez de salir a la
nube.

LOS FRENOS. La ventana horaria, un tope por tanda, un presupuesto de minutos repartido entre
las tres, y los descansos que calcula app/services/ritmo.py según lo que costó cada llamada
y según si el equipo se está frenando por temperatura.
"""
from __future__ import annotations

import os
import time
from datetime import datetime

from app.core.celery_app import celery_app
from app.core.database import SesionLocal
from app.services.estados import Estado

# La ventana, en horas del reloj de la máquina. Arranca a las diez de la noche y para a las
# seis de la mañana; cruzar la medianoche es lo normal aquí y por eso se compara distinto.
HORA_INICIO = int(os.getenv("NOCTURNO_DESDE", "22"))
HORA_FIN = int(os.getenv("NOCTURNO_HASTA", "6"))
TOPE_POR_NOCHE = int(os.getenv("NOCTURNO_TOPE", "40"))
MINUTOS_DE_TURNO = int(os.getenv("NOCTURNO_MINUTOS", "420"))

# Qué tandas corre y en qué orden. Se cambia con NOCTURNO_TAREAS=describir,revisar para
# dejar solo dos, o para poner otra de primera.
TANDAS = tuple(x.strip() for x in
               os.getenv("NOCTURNO_TAREAS", "clasificar,describir,revisar").split(",")
               if x.strip())

# Cómo se reparte el presupuesto de tiempo entre las tandas. La descripción se lleva la mitad
# porque es la que a usted le importa encontrar hecha; clasificar es corta y no necesita más.
REPARTO = {"clasificar": float(os.getenv("NOCTURNO_PARTE_CLASIFICAR", "0.20")),
           "describir": float(os.getenv("NOCTURNO_PARTE_DESCRIBIR", "0.50")),
           "revisar": float(os.getenv("NOCTURNO_PARTE_REVISAR", "0.30"))}

# Un modelo local por tarea. Vacío significa cualquiera de los descargados.
MODELO = {"clasificar": os.getenv("MODELO_CLASIFICAR", ""),
          "describir": os.getenv("MODELO_DESCRIBIR", ""),
          "revisar": os.getenv("MODELO_REVISAR", "")}
ACTIVO = os.getenv("NOCTURNO_ACTIVO", "1") not in ("0", "no", "false", "")

# Los descansos ya no son un número fijo aquí: los calcula app/services/ritmo.py según lo
# que costó cada descripción, y los alarga solo cuando detecta que el equipo se está
# frenando por temperatura. Los diales están en ese módulo.


def en_la_ventana(ahora: datetime | None = None) -> bool:
    """Si estamos dentro del horario nocturno. La ventana cruza la medianoche."""
    hora = (ahora or datetime.now()).hour
    if HORA_INICIO == HORA_FIN:
        return True
    if HORA_INICIO < HORA_FIN:
        return HORA_INICIO <= hora < HORA_FIN
    return hora >= HORA_INICIO or hora < HORA_FIN


def _tomar_el_turno(segundos: int) -> object | None:
    """
    Un solo turno a la vez.

    El planificador despierta cada hora dentro de la ventana, así que si un turno todavía va
    corriendo a la hora siguiente arrancaría un segundo encima del primero: dos procesos
    peleando por el mismo modelo local, que ya de por sí va lento. El seguro se toma en
    Redis y se suelta al terminar; si el proceso muere, expira solo.
    """
    try:
        import redis
        from app.core.config import configuracion
        r = redis.Redis.from_url(configuracion.CELERY_BROKER_URL)
        seguro = r.lock("kustos:turno-de-noche", timeout=segundos + 600, blocking=False)
        return seguro if seguro.acquire(blocking=False) else None
    except Exception:
        # Sin Redis no hay seguro, pero tampoco hay planificador: se deja pasar, porque
        # entonces el turno solo puede haberlo lanzado una persona a mano.
        return object()


def _hay_modelo_local(db) -> bool:
    """
    Si el modelo local está disponible HOY y con cuota.

    Se pregunta por la fila de motores y no por si Ollama contesta, porque lo que importa es
    que el reparto lo pueda elegir: un modelo descargado pero excluido no sirve de nada.
    """
    from app.services import catalogo, modelos
    try:
        estado = {d["clave"]: d for d in modelos.disponibilidad(db)}
        return any(m["proveedor"] == catalogo.OLLAMA
                   and not (estado.get(m["clave"]) or {}).get("agotado", True)
                   for m in modelos.motores())
    except Exception:
        return False


@celery_app.task(name="kustos.turno_de_noche", bind=True, max_retries=0)
def turno_de_noche(self, tope: int = 0, minutos: int = 0, forzar: bool = False,
                   permitir_la_nube: bool = False, tandas: tuple = ()) -> dict:
    """
    Corre las tandas de la noche, en orden, hasta que se acabe la ventana o el tiempo.

    Una tanda que se queda sin trabajo no desperdicia su parte del presupuesto: lo que le
    sobra pasa a la siguiente. Así, una noche en la que no haya nada que describir termina
    revisando descripciones viejas en vez de apagarse.

    Y todo va de a uno. El trabajador corre con seis procesos en paralelo, pero seis llamadas
    simultáneas a un modelo que vive en el mismo computador no lo hacen más rápido: lo
    ahogan. Aquí el paralelismo no ayuda, porque el cuello de botella es la máquina.
    """
    arranque = time.time()
    tope = tope or TOPE_POR_NOCHE
    presupuesto = (minutos or MINUTOS_DE_TURNO) * 60
    lista = tuple(tandas) or TANDAS

    if not ACTIVO and not forzar:
        return {"omitido": "el turno de noche está apagado (NOCTURNO_ACTIVO=0)"}
    if not forzar and not en_la_ventana():
        return {"omitido": f"fuera de la ventana ({HORA_INICIO}:00 a {HORA_FIN}:00)"}

    seguro = _tomar_el_turno(presupuesto)
    if seguro is None:
        return {"omitido": "ya hay un turno de noche corriendo"}

    db = SesionLocal()
    try:
        if not permitir_la_nube and not _hay_modelo_local(db):
            return {"omitido": "no hay modelo local disponible; el turno no sale a la nube "
                               "para no amanecer sin cuota. Revise con revisar_ollama.py"}

        from app.services.ritmo import Ritmo, en_palabras
        ritmo = Ritmo()
        partes, detenido = {}, ""
        gastado = 0.0

        for nombre in lista:
            hacer = _TANDAS.get(nombre)
            if not hacer:
                partes[nombre] = {"omitida": "no existe esa tanda"}
                continue
            if not forzar and not en_la_ventana():
                detenido = "se acabó la ventana; el resto queda para mañana"
                break

            # Lo que le toca a esta tanda, más lo que le sobró a las anteriores.
            restante = presupuesto - (time.time() - arranque)
            if restante <= 30:
                detenido = "se acabó el presupuesto de tiempo del turno"
                break
            suyo = min(restante, presupuesto * REPARTO.get(nombre, 0.33))
            pendientes_de_otras = restante - sum(
                presupuesto * REPARTO.get(n, 0.33) for n in lista[lista.index(nombre):])
            suyo = max(suyo, min(restante, suyo + max(0.0, pendientes_de_otras)))

            partes[nombre] = hacer(db, ritmo, tope, suyo, forzar,
                                   permitir_la_nube, MODELO.get(nombre, ""))
            gastado = time.time() - arranque
            if partes[nombre].get("detenido_porque"):
                detenido = partes[nombre]["detenido_porque"]
                if "cuota" in detenido or "dejó de responder" in detenido:
                    break

        parte = ritmo.parte()
        return {"tandas": partes,
                "hecho": sum(p.get("hechos", 0) for p in partes.values()),
                "detenido_porque": detenido,
                "ritmo": parte, "como_le_fue": en_palabras(parte),
                "minutos": round(gastado / 60 or (time.time() - arranque) / 60, 1),
                "terminado": datetime.now().isoformat(timespec="minutes")}
    finally:
        db.close()
        try:
            seguro.release()
        except Exception:
            pass


def _corre(db, ritmo, tope: int, segundos: float, forzar: bool, cuantos: int,
           trabajo, etiqueta: str) -> dict:
    """
    El armazón común de las tres tandas: el reloj, la ventana, el tope y los descansos.

    Está aparte porque los frenos tienen que ser exactamente los mismos en las tres. Si cada
    tanda llevara su propio control, tarde o temprano una se quedaría sin alguno.
    """
    arranque = time.time()
    hechos, fallidos, detenido = 0, 0, ""
    for numero in range(cuantos):
        if not forzar and not en_la_ventana():
            detenido = "se acabó la ventana"
            break
        if time.time() - arranque > segundos:
            detenido = f"se acabó el tiempo de la tanda de {etiqueta}"
            break
        if hechos >= tope:
            detenido = f"tope de {tope} por noche en {etiqueta}"
            break

        empezo = time.time()
        resultado = trabajo(numero)
        if resultado == "sin_motor":
            detenido = "el modelo local dejó de responder"
            break
        if resultado == "fallo":
            fallidos += 1
            continue
        if resultado == "nada":
            continue
        hechos += 1

        ritmo.anotar(time.time() - empezo)
        descanso, porque = ritmo.descanso()
        if descanso and numero + 1 < cuantos:
            if ritmo.hay_calor:
                _nota_suelta(db, f"El turno bajó el ritmo en la tanda de {etiqueta}: {porque}.")
                db.commit()
            time.sleep(descanso)

    return {"hechos": hechos, "fallidos": fallidos, "detenido_porque": detenido,
            "minutos": round((time.time() - arranque) / 60, 1)}


def _nota_de_calor(db, exp, porque: str) -> None:
    """
    Queda escrito cuándo el equipo se frenó por temperatura.

    En la mañana hay que poder distinguir dos cosas que se ven igual: que el turno haya
    rendido poco porque el modelo es lento, o porque la máquina se estaba cocinando. La
    primera se arregla con otro modelo; la segunda, con ventilación.
    """
    from app.models import Trazabilidad
    db.add(Trazabilidad(
        expediente_id=exp.id, estado_anterior=exp.estado, estado_nuevo=exp.estado,
        accion="turno_de_noche", usuario="Turno de noche (automático)",
        motivo=f"El turno bajó el ritmo: {porque}."))


def _fallo(db, exp, error: Exception) -> None:
    from app.models import Trazabilidad
    db.add(Trazabilidad(
        expediente_id=exp.id, estado_anterior=exp.estado, estado_nuevo=exp.estado,
        accion="generar_isadg", usuario="Turno de noche (automático)",
        motivo=f"El turno de noche no pudo describirla: {type(error).__name__}: "
               f"{str(error)[:200]}. Queda como estaba, para hacerla a mano."))


def _nota_suelta(db, texto: str) -> None:
    """Una anotación de la noche que no es de ningún expediente en particular."""
    from app.models import Trazabilidad
    db.add(Trazabilidad(expediente_id=None, estado_anterior=None, estado_nuevo=None,
                        accion="turno_de_noche",
                        usuario="Turno de noche (automático)", motivo=texto[:500]))


# ---------------------------------------------------------------------------
# Tanda 1. Clasificar lo que quedó sin subserie
# ---------------------------------------------------------------------------
def _tanda_clasificar(db, ritmo, tope, segundos, forzar, permitir_la_nube, modelo) -> dict:
    """
    Los expedientes que el modelo ya leyó pero que quedaron sin subserie de la tabla.

    Va de primera porque atasca a las demás: sin subserie no se puede describir, así que uno
    de estos detenido detiene también su descripción y su revisión. Es además la tanda más
    barata, porque la consulta va sin documento adjunto y contra una lista cerrada.
    """
    from app.models import Expediente
    from app.tasks import elegir_subserie_del_expediente

    pendientes = (db.query(Expediente)
                    .filter(Expediente.subserie_id.is_(None))
                    .filter(Expediente.estado.in_([Estado.HOJA_EN_ELABORACION.value,
                                                   Estado.HOJA_POR_REVISAR.value,
                                                   Estado.HOJA_REVISADA.value]))
                    .order_by(Expediente.id).limit(tope * 2).all())
    if not pendientes:
        return {"hechos": 0, "fallidos": 0, "nada_que_hacer": True, "minutos": 0}

    def trabajo(i):
        exp = pendientes[i]
        try:
            from app.models import Periodo, UnidadInventario
            unidad = (db.query(UnidadInventario)
                        .filter(UnidadInventario.codigo_carpeta == exp.codigo_carpeta).first())
            periodo = db.get(Periodo, exp.periodo_id) if exp.periodo_id else None
            romano = periodo.numero_romano if periodo else (unidad.periodo if unidad else "")
            if not romano:
                return "nada"
            from app.routers.expedientes import _opciones_tvd
            opciones = _opciones_tvd(db, romano)
            if not opciones:
                return "nada"
            antes = exp.subserie_id
            elegir_subserie_del_expediente(db, exp, unidad, romano, opciones, modelo=modelo)
            db.commit()
            return "hecho" if exp.subserie_id and exp.subserie_id != antes else "nada"
        except Exception as e:
            db.rollback()
            _fallo(db, exp, e)
            db.commit()
            return "fallo"

    return _corre(db, ritmo, tope, segundos, forzar, len(pendientes), trabajo, "clasificación")


# ---------------------------------------------------------------------------
# Tanda 2. Describir las hojas ya revisadas
# ---------------------------------------------------------------------------
def _tanda_describir(db, ritmo, tope, segundos, forzar, permitir_la_nube, modelo) -> dict:
    """
    El grueso de la noche: la descripción ISAD(G) de las hojas que una persona ya revisó.

    A propósito NO se relee el escaneo. Eso necesita visión y saldría a la nube; de noche se
    redacta a partir de los trámites que la hoja de control ya levantó, que es justamente lo
    que el modelo local hace bien.
    """
    from app.models import Expediente
    from app.routers.expedientes import _contexto_para_el_modelo
    from app.services import modelos
    from app.services.descripcion import construir_descripcion
    from app.services.estados import Funcion, Rol
    from app.services.estados import Usuario as UsuarioCalculo

    pendientes = (db.query(Expediente)
                    .filter(Expediente.estado == Estado.HOJA_REVISADA.value)
                    .filter(Expediente.subserie_id.isnot(None))
                    .order_by(Expediente.id).limit(tope * 2).all())
    if not pendientes:
        return {"hechos": 0, "fallidos": 0, "nada_que_hacer": True, "minutos": 0}

    quien = UsuarioCalculo(nombre="Turno de noche (automático)",
                           correo="turno-de-noche@kustos.local",
                           rol=Rol.LIDER, funcion=Funcion.DESCRIPCION)

    def trabajo(i):
        exp = pendientes[i]
        try:
            contexto = _contexto_para_el_modelo(db, exp)
            propuesta = modelos.describir(db, contexto, modelo=modelo)
            if not propuesta and not permitir_la_nube:
                return "sin_motor"
            construir_descripcion(db, exp, quien, propuesta.campos if propuesta else None)
            if propuesta:
                exp.redactada_por = propuesta.proveedor
            exp.describio = quien.nombre
            _anotar(db, exp, propuesta)
            db.commit()
            return "hecho"
        except Exception as e:
            db.rollback()
            _fallo(db, exp, e)
            db.commit()
            return "fallo"

    return _corre(db, ritmo, tope, segundos, forzar, len(pendientes), trabajo, "descripción")


# ---------------------------------------------------------------------------
# Tanda 3. Revisar las descripciones que nunca pasó nadie
# ---------------------------------------------------------------------------
def _tanda_revisar(db, ritmo, tope, segundos, forzar, permitir_la_nube, modelo) -> dict:
    """
    El relleno de la noche, y el que más tranquilidad da.

    Hay descripciones hechas antes de que existiera el revisor, y ninguna ha pasado por él.
    Esta tanda las va tomando de las más viejas a las más nuevas. Si las otras dos colas se
    vaciaron, la noche no se desperdicia; y si no alcanza, no se pierde nada, porque son
    descripciones que ya estaban hechas.

    Lo que encuentre queda en la bitácora del expediente, marcado como opinión de un modelo,
    y aparece en la hoja de revisión cuando se expida la base. No cambia un solo campo.
    """
    from app.models import Expediente, Tramite
    from app.services import modelos, revisor

    pendientes = (db.query(Expediente)
                    .filter(Expediente.codigo_referencia.isnot(None))
                    .filter(Expediente.revisada_por_modelo.is_(None))
                    .filter(Expediente.estado.in_([Estado.PENDIENTE_REVISION.value,
                                                   Estado.DESCRIPCION_VALIDADA.value]))
                    .order_by(Expediente.id).limit(tope * 2).all())
    if not pendientes:
        return {"hechos": 0, "fallidos": 0, "nada_que_hacer": True, "minutos": 0}

    def trabajo(i):
        exp = pendientes[i]
        try:
            tramites = [{"no_item": t.no_item, "fecha": t.fecha_texto,
                         "tipo_documental": t.tipo_documental, "folio_desde": t.folio_desde,
                         "folio_hasta": t.folio_hasta, "observaciones": t.observaciones}
                        for t in db.query(Tramite)
                                  .filter(Tramite.expediente_id == exp.id)
                                  .order_by(Tramite.no_item).all()]
            unidad = {"codigo_referencia": exp.codigo_referencia, "titulo": exp.titulo,
                      "alcance": exp.alcance_contenido, "volumen": exp.volumen_folios,
                      "fecha_inicial": exp.fecha_inicial, "fecha_final": exp.fecha_final,
                      "subserie": _nombre_subserie(db, exp), "tramites": tramites}
            propuesta = modelos.revisar_descripcion(
                db, revisor.instruccion(unidad), redacto=exp.redactada_por or "",
                modelo=modelo)
            if not propuesta and not permitir_la_nube:
                return "sin_motor"
            hallazgos = revisor.hallazgos_de(unidad, propuesta.campos, propuesta.proveedor)
            exp.revisada_por_modelo = propuesta.proveedor
            _anotar_revision(db, exp, hallazgos, propuesta.proveedor)
            db.commit()
            return "hecho"
        except Exception as e:
            db.rollback()
            _fallo(db, exp, e)
            db.commit()
            return "fallo"

    return _corre(db, ritmo, tope, segundos, forzar, len(pendientes), trabajo, "revisión")


def _nombre_subserie(db, exp) -> str:
    from app.models import Serie, Subserie
    sub = db.get(Subserie, exp.subserie_id) if exp.subserie_id else None
    if not sub:
        return ""
    serie = db.get(Serie, sub.serie_id)
    return f"{serie.nombre} › {sub.nombre}" if serie else sub.nombre


def _anotar_revision(db, exp, hallazgos, proveedor: str) -> None:
    """
    Lo que encontró el revisor queda en la bitácora del expediente, no en el expediente.

    Es deliberado: un hallazgo de modelo es una opinión, y una opinión no puede quedar
    escrita como si fuera un dato de la descripción. Se lee en la bitácora y sale en la hoja
    de revisión de la base, donde una persona la confirma o la descarta.
    """
    from app.models import Trazabilidad
    if not hallazgos:
        motivo = (f"Revisada en el turno de noche por {proveedor}: sin reparos sobre el "
                  "título, el alcance ni la correspondencia con los trámites.")
    else:
        motivo = (f"Revisada en el turno de noche por {proveedor}. {len(hallazgos)} punto(s) "
                  "para mirar: " + " | ".join(h.que_pasa for h in hallazgos))
    db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                        estado_nuevo=exp.estado, accion="revisar_descripcion",
                        usuario="Turno de noche (automático)", motivo=motivo[:500]))


_TANDAS = {"clasificar": _tanda_clasificar,
           "describir": _tanda_describir,
           "revisar": _tanda_revisar}
