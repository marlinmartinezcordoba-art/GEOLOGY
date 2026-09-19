"""
Reparto del trabajo entre todos los modelos de lenguaje disponibles.

Trabajan Claude, Gemini y ChatGPT, y de cada uno TODOS los modelos que la cuenta admita: la
plataforma le pregunta a cada proveedor qué modelos tiene (véase catalogo.py) y arma con
ellos una sola fila de motores.

Todos hacen EXACTAMENTE EL MISMO TRABAJO, que es leer el expediente y redactar los elementos
narrativos de la descripción. No se reparten tareas distintas: se reparten expedientes, que
es lo que evita que uno solo agote su cuota diaria y deje la producción detenida.

El reparto tiene dos criterios. Por tamaño, los expedientes de más folios van a los modelos
de más aliento y los de menos folios a los ligeros. Por carga, entre los del mismo nivel
entra el que más cuota le quede hoy. Si uno falla o se agota, el expediente pasa al siguiente
sin que nadie tenga que intervenir.

Al modelo se le encarga solo lo que exige leer, es decir el título atribuido, el alcance y
contenido, la organización y las notas. Todo lo verificable, que es el código de referencia,
la valoración de la tabla convalidada, el periodo, las fechas extremas y los folios, lo
resuelve el código y el modelo no lo toca.

Regla que no se negocia: si ningún modelo tiene cuota o todos fallan, esta capa devuelve None.
Nunca inventa una descripción. Un expediente sin describir espera; un expediente con una
descripción fabricada contamina el fondo y nadie se entera.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.services import catalogo

CLAUDE = "claude"
GEMINI = "gemini"
OPENAI = "openai"
OLLAMA = "ollama"        # el modelo local del equipo; no gasta cuota de nadie

PROVEEDORES = {
    CLAUDE: {
        "llave": "ANTHROPIC_API_KEY",
        "cuota_por_modelo": int(os.getenv("CUOTA_CLAUDE", "1000")),
        "url": "https://api.anthropic.com/v1/messages",
    },
    GEMINI: {
        "llave": "GEMINI_API_KEY",
        "cuota_por_modelo": int(os.getenv("CUOTA_GEMINI", "500")),
        "url": "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
    },
    OPENAI: {
        "llave": "OPENAI_API_KEY",
        "cuota_por_modelo": int(os.getenv("CUOTA_OPENAI", "500")),
        "url": "https://api.openai.com/v1/responses",
    },
    OLLAMA: {
        "llave": "OLLAMA_URL",
        # Corre en el computador del equipo: no hay cuota que gastar ni factura que llegue.
        # El número es alto para que nunca se marque agotado, no porque haya un límite.
        "cuota_por_modelo": int(os.getenv("CUOTA_OLLAMA", "1000000")),
        "url": "{llave}/api/chat",
    },
}

# Las tres tareas que hace la plataforma no son iguales y por eso no van al mismo sitio.
#
# LEER el expediente digitalizado es visión sobre manuscrito histórico en tinta ferrogálica
# y mecanografiado de los años cuarenta. Ahí el modelo local queda muy por debajo, y el
# riesgo no es que falle sino que falle de forma verosímil: una transcripción que parece
# correcta y no lo es contamina el fondo sin que nadie se entere. Esa tarea no se le da.
#
# ELEGIR LA SUBSERIE contra la tabla de valoración y REDACTAR el ISAD(G) a partir de los
# trámites ya levantados son, en cambio, texto contra texto, sin documento adjunto. Ahí el
# modelo local rinde bien, y son cerca de dos llamadas por carpeta: sobre las 7.699 del
# contrato, unas quince mil llamadas que dejan de gastar la cuota de las llaves del equipo.
# Además no salen del computador, que para la documentación del Servicio Geológico importa
# tanto como el ahorro.
SIN_MODELO_LOCAL = (OLLAMA,)

# EL REPARTO POR TAREA, EN UN SOLO SITIO
#
# Las cuatro cosas que se le piden a un modelo en esta plataforma no son la misma cosa, y
# mandarlas todas al mismo motor es desperdiciar cuota en unas y arriesgar calidad en otras.
#
#   LEER        el expediente digitalizado. Visión sobre manuscrito en tinta ferrogálica.
#               Es la tarea cara y la única que necesita el modelo de más aliento. Nunca al
#               modelo local: falla de forma verosímil y eso contamina el fondo.
#   CLASIFICAR  a qué subserie de la tabla convalidada pertenece. Texto contra una lista
#               cerrada, sin documento adjunto. Barata; primero el modelo local, que no
#               gasta cuota de nadie.
#   REDACTAR    título, alcance, organización y notas. Necesita prosa en español, y por eso
#               se reparte por tamaño: el expediente de muchos folios al modelo de aliento.
#   REVISAR     mirar lo redactado como lo miraría la interventoría. Barata, y con una
#               condición que no es técnica sino archivística: el revisor tiene que ser de
#               un proveedor DISTINTO al que redactó. Un modelo revisando su propia
#               redacción la encuentra excelente, que es la misma razón por la que aquí
#               nadie aprueba su propio trabajo.
LEER, CLASIFICAR, REDACTAR, REVISAR = "leer", "clasificar", "redactar", "revisar"

CAMPOS = ("titulo", "alcance_contenido", "organizacion", "notas")

# Reparto por tamaño del expediente. Los grandes traen más trámites y más contexto que leer
# y van a los modelos de más aliento; los pequeños, a los ligeros, que son los de cuota más
# ajustada. El corte se cambia con la variable UMBRAL_FOLIOS sin tocar código.
UMBRAL_FOLIOS = int(os.getenv("UMBRAL_FOLIOS", "100"))
ORDEN_GRANDES = (catalogo.ALTO, catalogo.MEDIO, catalogo.BAJO)
ORDEN_PEQUENOS = (catalogo.BAJO, catalogo.MEDIO, catalogo.ALTO)
MARCA = "[PROPUESTA DEL MODELO, PENDIENTE DE REVISIÓN] "


def motores(forzar: bool = False) -> list[dict]:
    """
    La fila completa de motores disponibles hoy: un renglón por cada combinación de llave y
    modelo de cada proveedor que tenga algo escrito en el archivo .env.

    Si en una variable hay varias llaves separadas por comas, cada una entra con su propia
    cuota diaria. Dos llaves de Gemini con cinco modelos cada una son diez motores, y la
    capacidad del día se dobla sin tocar nada más.

    El valor de la llave viaja dentro del motor pero NUNCA sale en la clave de consumo ni en
    el tablero: allí solo se ve el número de orden, "llave 1", "llave 2".
    """
    salida: list[dict] = []
    for proveedor, cfg in PROVEEDORES.items():
        llaves = catalogo.claves_de(proveedor)
        modelos_disponibles = catalogo.modelos_de(proveedor, forzar) if llaves else []
        for orden, llave_api in enumerate(llaves, start=1):
            etiqueta = proveedor if len(llaves) == 1 else f"{proveedor}#{orden}"
            for modelo in modelos_disponibles:
                salida.append({"clave": f"{etiqueta}/{modelo}", "proveedor": proveedor,
                               "modelo": modelo, "nivel": catalogo.nivel(modelo),
                               "llave_api": llave_api, "orden_llave": orden,
                               "total_llaves": len(llaves),
                               "cuota_diaria": cfg["cuota_por_modelo"]})
    return salida


class DocumentoRechazado(Exception):
    """
    El documento en sí es el problema, no el motor.

    Un 400 o un 413 con el documento adjunto puede querer decir dos cosas muy distintas: que
    ese modelo no admite documentos portátiles, o que el archivo enviado no le sirve a nadie
    porque pesa de más, está cifrado o llegó corrupto. Distinguirlas importa: si se confunde
    lo segundo con lo primero, un solo tomo mal escaneado va apagando motor tras motor y deja
    a todo el equipo sin producción por el resto del día.
    """


class SinCuota(Exception):
    """Ningún proveedor tiene cuota disponible hoy."""


@dataclass
class Propuesta:
    proveedor: str
    campos: dict
    modelo: str = ""

    def marcada(self, campo: str) -> str | None:
        valor = (self.campos.get(campo) or "").strip()
        return (MARCA + valor) if valor else None


# ---------------------------------------------------------------------------
# Cuota
# ---------------------------------------------------------------------------
def _primera_llave(proveedor: str) -> str:
    llaves = catalogo.claves_de(proveedor)
    return llaves[0] if llaves else ""


def _registro(db: Session, clave: str):
    """La fila de consumo de hoy de un motor. La clave es proveedor/modelo."""
    from app.models import ConsumoModelo
    hoy = date.today()
    fila = db.query(ConsumoModelo).filter_by(fecha=hoy, proveedor=clave).first()
    if not fila:
        fila = ConsumoModelo(fecha=hoy, proveedor=clave, peticiones=0)
        db.add(fila)
        db.flush()
    return fila


def disponibilidad(db: Session, forzar: bool = False) -> list[dict]:
    """Cuánto le queda hoy a cada modelo. Es lo que alimenta el tablero."""
    salida = []
    for m in motores(forzar):
        fila = _registro(db, m["clave"])
        restante = max(0, m["cuota_diaria"] - fila.peticiones)
        salida.append({
            "clave": m["clave"],
            "proveedor": m["proveedor"],
            "modelo": m["modelo"],
            "nivel": m["nivel"],
            "llave": (f"llave {m['orden_llave']} de {m['total_llaves']}"
                      if m["total_llaves"] > 1 else "única"),
            "configurado": True,          # sin llave el motor ni siquiera aparece
            "usadas": fila.peticiones,
            "cuota_diaria": m["cuota_diaria"],
            "restantes": 0 if fila.agotado_en else restante,
            "agotado": bool(fila.agotado_en) or restante == 0,
            "ultimo_error": fila.ultimo_error,
        })
    if not salida:
        # Ni una sola llave escrita: el tablero tiene que decirlo, no quedarse en blanco.
        for proveedor, cfg in PROVEEDORES.items():
            salida.append({"clave": proveedor, "proveedor": proveedor, "modelo": "—",
                           "nivel": "—", "llave": "—", "configurado": False, "usadas": 0,
                           "cuota_diaria": cfg["cuota_por_modelo"], "restantes": 0,
                           "agotado": True,
                           "ultimo_error": f"Falta {cfg['llave']} en el archivo .env."})
    return salida


def elegir_motor(db: Session, folios: int | None = None,
                 excluir: set[str] | None = None, turno: int | None = None,
                 sin_proveedor: tuple = (), preferir: str = "",
                 modelo: str = "") -> dict | None:
    """
    Elige el modelo que atiende este expediente, en dos tiempos.

    Primero por tamaño: los expedientes de muchos folios van a los modelos de más aliento y
    los de pocos a los ligeros. Segundo, dentro del mismo nivel entra el que más cuota le
    quede hoy, y si en ese nivel no queda ninguno se baja al siguiente. Eso es lo que evita
    que un día de puros expedientes pequeños sature a un solo modelo y deje a los demás sin
    usar, o al revés.

    Encima de eso hay dos filtros por tarea. sin_proveedor deja fuera a un proveedor que no
    sirve para lo que se está pidiendo —el modelo local no lee expedientes digitalizados—, y
    preferir lo pone de primero cuando sí sirve, para que la tarea de texto se resuelva en el
    computador del equipo y no gaste cuota de la nube. En los dos casos los demás motores
    siguen ahí detrás: si el preferido no contesta, el expediente pasa al siguiente.
    """
    estado = {d["clave"]: d for d in disponibilidad(db)}
    libres = []
    for m in motores():
        d = estado.get(m["clave"])
        if not d or d["agotado"] or m["clave"] in (excluir or set()):
            continue
        if m["proveedor"] in sin_proveedor:
            continue
        libres.append({**m, "restantes": d["restantes"]})
    if not libres:
        return None

    if preferir:
        caseros = [d for d in libres if d["proveedor"] == preferir]
        if modelo:
            # Un modelo concreto, pedido por la tarea. Sirve sobre todo de noche: clasificar
            # y revisar salen bien con un modelo pequeño, que es dos veces más rápido, y la
            # redacción conviene dejársela a uno más grande. Si el pedido no está descargado
            # no se falla: se sigue con cualquiera del proveedor preferido.
            exactos = [d for d in caseros if d["modelo"] == modelo
                       or d["modelo"].startswith(modelo + ":")]
            if exactos:
                return _repartir(exactos, turno)
        if caseros:
            return _repartir(caseros, turno)

    orden = ORDEN_GRANDES if (folios or 0) >= UMBRAL_FOLIOS else ORDEN_PEQUENOS
    for nivel in orden:
        delnivel = [d for d in libres if d["nivel"] == nivel]
        if delnivel:
            return _repartir(delnivel, turno)
    return _repartir(libres, turno)


def _repartir(candidatos: list[dict], turno: int | None) -> dict:
    """
    A cada expediente su motor, por turnos.

    Cuando se procesan varios expedientes al mismo tiempo, escoger siempre «el que más cuota
    le queda» hace que todos salgan por la misma llave: el contador solo sube cuando la
    llamada termina, así que los que arrancan juntos ven el mismo estado y se amontonan.

    Con el turno del expediente —su posición en la cola de cargue— cada uno entra por una
    llave distinta y se reparten de verdad. Sin turno se conserva el criterio de siempre.
    """
    if turno is None:
        return max(candidatos, key=lambda d: d["restantes"])
    ordenados = sorted(candidatos, key=_orden_natural)
    return ordenados[turno % len(ordenados)]


def _orden_natural(motor: dict):
    """
    Ordena llave 2 antes que llave 10. Comparando como texto, «#10» va antes que «#2» y el
    reparto queda desordenado a la vista aunque funcione.
    """
    import re as _re
    partes = _re.split(r"(\d+)", motor["clave"])
    return [int(p) if p.isdigit() else p for p in partes]


def elegir_proveedor(db: Session, folios: int | None = None,
                     excluir: set[str] | None = None) -> str | None:
    """Compatibilidad con lo anterior: devuelve solo el nombre del proveedor elegido."""
    m = elegir_motor(db, folios, excluir)
    return m["proveedor"] if m else None


def _sumar(db: Session, clave: str) -> None:
    _registro(db, clave).peticiones += 1


def _agotar(db: Session, clave: str, motivo: str) -> None:
    """
    Marca el motor como no utilizable por hoy y deja escrito el porqué.

    El texto pasa por el tapado antes de guardarse: un error del proveedor puede traer de
    vuelta la dirección completa con la llave dentro, y esa no puede quedar escrita en la
    base ni aparecer en el tablero, que lo ve todo el equipo.
    """
    fila = _registro(db, clave)
    fila.agotado_en = datetime.now()
    fila.ultimo_error = catalogo.tapar(motivo)[:500]


# ---------------------------------------------------------------------------
# La instrucción al modelo
# ---------------------------------------------------------------------------
def construir_instruccion(contexto: dict) -> str:
    """
    El modelo recibe hechos verificados, no adivina ninguno. La clasificación, el periodo y
    la valoración le llegan resueltos y su tarea es exclusivamente redactar.
    """
    tramites = "\n".join(
        f"  {t['no_item']}. {t.get('fecha') or 'sin fecha'} · {t.get('tipo_documental') or 'sin tipo'} "
        f"· folios {t.get('folio_desde')} a {t.get('folio_hasta')}"
        f"{' · ' + t['observaciones'] if t.get('observaciones') else ''}"
        for t in contexto.get("tramites", []))
    return f"""Usted es archivista y redacta la descripción de una unidad documental conforme a
la norma ISAD(G) segunda edición y a la norma técnica colombiana 4095 de 2013, para el fondo
acumulado del Servicio Geológico Colombiano, contrato 733 de 2026.

Datos ya verificados, que NO debe modificar ni contradecir:
  Código de carpeta: {contexto.get('codigo_carpeta')}
  Periodo institucional: {contexto.get('periodo')} ({contexto.get('rango_periodo')})
  Entidad productora: {contexto.get('entidad_productora')}
  Oficina productora: {contexto.get('oficina_productora')}
  Serie y subserie: {contexto.get('serie')} › {contexto.get('subserie')}
  Fechas extremas: {contexto.get('fechas_extremas')}
  Folios: {contexto.get('folios')}
  Asunto según el inventario de origen: {contexto.get('asunto_inventario')}

Trámites de la hoja de control F-GDM-007:
{tramites or '  (sin trámites registrados)'}

Redacte únicamente estos cuatro elementos, en español, en prosa sobria de archivo, sin
viñetas, sin adjetivos de valoración y sin repetir información que ya esté en otros
elementos de la descripción:

  titulo             elemento 3.1.2, título atribuido. Una línea. Sin comillas.
  alcance_contenido  elemento 3.3.1. Qué contiene la unidad y de qué trata, en dos a cuatro
                     frases, apoyándose solo en los trámites listados.
  organizacion       elemento 3.3.4. Cómo está ordenada la unidad.
  notas              elemento 3.6.1. Solo si hay algo que advertir; si no, cadena vacía.

Reglas estrictas. No invente fechas, nombres de personas, lugares ni cifras que no aparezcan
arriba. No proponga serie ni subserie: ya están asignadas. Si la información es insuficiente
para un elemento, devuelva ese elemento como cadena vacía en lugar de suponer.

Responda EXCLUSIVAMENTE un objeto JSON con esas cuatro claves, sin texto adicional."""


# ---------------------------------------------------------------------------
# Los transportes. Mismo trabajo, distinto proveedor.
# ---------------------------------------------------------------------------
def _peticion(url: str, cuerpo: dict, cabeceras: dict, segundos: int = 90) -> dict:
    datos = json.dumps(cuerpo).encode("utf-8")
    peticion = urllib.request.Request(url, data=datos, headers=cabeceras, method="POST")
    with urllib.request.urlopen(peticion, timeout=segundos) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def _llamar_claude(instruccion: str, documento: bytes | None = None,
                   campos: tuple = CAMPOS, max_tokens: int = 1500,
                   modelo: str = "", llave_api: str = "") -> dict:
    cfg = PROVEEDORES[CLAUDE]
    clave = (llave_api or "").strip() or _primera_llave(CLAUDE)
    if not clave:
        raise SinCuota("Claude no tiene credencial configurada.")

    contenido: list = []
    if documento:
        # El documento va tal cual, sin extraerle el texto antes: así el modelo también ve
        # el estado del papel, que es lo que permite anotar manchas, rasgaduras y tinta débil.
        contenido.append({"type": "document",
                          "source": {"type": "base64", "media_type": "application/pdf",
                                     "data": base64.standard_b64encode(documento).decode("ascii")}})
    contenido.append({"type": "text", "text": instruccion})

    respuesta = _peticion(cfg["url"], {
        "model": modelo, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": contenido}],
    }, {"content-type": "application/json", "x-api-key": clave,
        "anthropic-version": "2023-06-01"}, segundos=600)
    return _extraer_json("".join(b.get("text", "") for b in respuesta.get("content", [])), campos)


def _llamar_gemini(instruccion: str, documento: bytes | None = None,
                   campos: tuple = CAMPOS, max_tokens: int = 1500,
                   modelo: str = "", llave_api: str = "") -> dict:
    cfg = PROVEEDORES[GEMINI]
    clave = (llave_api or "").strip() or _primera_llave(GEMINI)
    if not clave:
        raise SinCuota("Gemini no tiene credencial configurada.")
    url = cfg["url"].format(modelo=modelo) + f"?key={clave}"

    partes: list = []
    if documento:
        partes.append({"inline_data": {"mime_type": "application/pdf",
                                       "data": base64.standard_b64encode(documento).decode("ascii")}})
    partes.append({"text": instruccion})

    respuesta = _peticion(url, {
        "contents": [{"parts": partes}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2,
                             "maxOutputTokens": max_tokens},
    }, {"content-type": "application/json"}, segundos=600)
    devueltas = respuesta.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])
    return _extraer_json("".join(p.get("text", "") for p in devueltas), campos)


def _llamar_ollama(instruccion: str, documento: bytes | None = None,
                   campos: tuple = CAMPOS, max_tokens: int = 1500,
                   modelo: str = "", llave_api: str = "") -> dict:
    """
    El modelo que corre en el computador del equipo, por medio de Ollama.

    No lleva credencial: la «llave» es la dirección donde escucha. Y no se le manda el
    expediente digitalizado —el reparto ya se encarga de no darle esa tarea—, así que si
    llegara un documento se ignora antes que arriesgar una transcripción inventada.

    Se espera con holgura: sin tarjeta gráfica dedicada, un modelo de siete mil millones de
    parámetros puede tardar varios minutos en contestar, y cortarlo antes solo lograría que
    el trabajo se pierda después de haberlo hecho.
    """
    direccion = (llave_api or "").strip().rstrip("/")
    if not direccion:
        raise SinCuota("No está configurada la dirección del modelo local (OLLAMA_URL).")
    if documento:
        raise SinCuota("Al modelo local no se le encarga leer documentos digitalizados.")

    respuesta = _peticion(direccion + "/api/chat", {
        "model": modelo,
        "messages": [{"role": "user", "content": instruccion}],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": max_tokens},
    }, {"content-type": "application/json"},
        segundos=int(os.getenv("ESPERA_OLLAMA", "900")))
    return _extraer_json((respuesta.get("message") or {}).get("content", ""), campos)


def _llamar_openai(instruccion: str, documento: bytes | None = None,
                   campos: tuple = CAMPOS, max_tokens: int = 1500,
                   modelo: str = "", llave_api: str = "") -> dict:
    """
    Tercer proveedor. Entra por la misma puerta que los otros dos: recibe la misma
    instrucción, devuelve el mismo objeto y gasta de su propia cuota diaria.

    Se usa la interfaz de respuestas, que es la que admite el documento portátil completo
    sin extraerle antes el texto, igual que los otros dos, para que el modelo también vea el
    estado del papel y pueda anotar manchas, rasgaduras y tinta desvanecida.
    """
    cfg = PROVEEDORES[OPENAI]
    clave = (llave_api or "").strip() or _primera_llave(OPENAI)
    if not clave:
        raise SinCuota("OpenAI no tiene credencial configurada.")

    contenido: list = []
    if documento:
        b64 = base64.standard_b64encode(documento).decode("ascii")
        contenido.append({"type": "input_file", "filename": "expediente.pdf",
                          "file_data": f"data:application/pdf;base64,{b64}"})
    contenido.append({"type": "input_text", "text": instruccion})

    respuesta = _peticion(cfg["url"], {
        "model": modelo,
        "input": [{"role": "user", "content": contenido}],
        "max_output_tokens": max_tokens,
    }, {"content-type": "application/json", "authorization": "Bearer " + clave}, segundos=600)
    return _extraer_json(_texto_openai(respuesta), campos)


def _texto_openai(respuesta: dict) -> str:
    """Junta el texto de la respuesta, que viene repartido en bloques."""
    if isinstance(respuesta.get("output_text"), str):
        return respuesta["output_text"]
    partes = []
    for item in respuesta.get("output", []):
        for bloque in item.get("content", []) or []:
            if isinstance(bloque, dict) and isinstance(bloque.get("text"), str):
                partes.append(bloque["text"])
    return "".join(partes)


TRANSPORTES = {CLAUDE: _llamar_claude, GEMINI: _llamar_gemini,
               OPENAI: _llamar_openai, OLLAMA: _llamar_ollama}


def _extraer_json(texto: str, campos: tuple = CAMPOS) -> dict:
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):]
    inicio, fin = t.find("{"), t.rfind("}")
    if inicio < 0 or fin < 0:
        raise ValueError("El modelo no devolvió un objeto JSON.")
    crudo = json.loads(t[inicio:fin + 1])
    if campos is None:                      # se devuelve el objeto tal cual
        return crudo
    return {c: str(crudo.get(c, "") or "").strip() for c in campos}


# ---------------------------------------------------------------------------
# Entrada única
# ---------------------------------------------------------------------------
def leer_documento(db: Session, documento: bytes, instruccion: str,
                   folios_estimados: int | None = None,
                   turno: int | None = None) -> Propuesta | None:
    """
    Manda el documento completo al proveedor con cuota y devuelve lo que leyó.

    A diferencia de la descripción, aquí el reparto por tamaño se hace por folios del
    expediente: los grandes a Claude y los pequeños a Gemini, con paso automático al otro
    cuando al preferido se le acaba la cuota. Si ninguno responde, devuelve None y el
    expediente se queda esperando; nunca se inventa una hoja de control.

    Si lo que falla es el archivo y no los motores, levanta DocumentoRechazado en vez de
    devolver None, para que la plataforma pueda decir qué pasa con ese documento en vez de
    dejarlo esperando una cuota que no lo va a arreglar.
    """
    return _intentar(db, instruccion, documento, folios_estimados, None, 8000, turno,
                     sin_proveedor=SIN_MODELO_LOCAL)


def elegir_subserie(db: Session, instruccion: str, turno: int | None = None,
                    modelo: str = "") -> Propuesta | None:
    """
    Segunda consulta, corta y sin documento adjunto: a qué subserie de la tabla pertenece
    lo que ya se leyó.

    Va sin el expediente digitalizado a cuestas porque no hace falta volver a leerlo: le
    basta la lista de trámites que salió de la primera pasada. Por eso es barata y por eso
    puede hacerse en todos los expedientes sin comerse la cuota del día.

    Si ningún motor responde devuelve None y la plataforma propone la subserie por
    coincidencia de palabras, que es lo que hacía antes. Nunca se queda sin proponer.
    """
    from app.services.lectura import CAMPOS_ELECCION
    return _intentar(db, instruccion, None, 0, CAMPOS_ELECCION, 500, turno,
                     preferir=OLLAMA, modelo=modelo)


def revisar_descripcion(db: Session, instruccion: str, redacto: str = "",
                        turno: int | None = None, modelo: str = "") -> Propuesta | None:
    """
    Cuarta tarea. Un modelo distinto mira lo que redactó el otro y dice qué le devolverían.

    Va sin documento adjunto: le basta lo que ya se describió y la lista de trámites que
    salió de la hoja de control. Por eso es barata y por eso el modelo local la puede asumir
    completa, salvo cuando fue él mismo quien redactó.

    NUNCA corrige ni aprueba. Devuelve hallazgos, que entran a la hoja de revisión marcados
    como lo que son: una opinión de máquina que una persona tiene que confirmar. El día que
    un agente apruebe lo de otro agente, se perdió el punto de control humano que sostiene
    el contrato.
    """
    from app.services.revisor import CAMPOS_REVISION

    # El que redactó no se revisa a sí mismo. Si fue el local, la revisión sale a la nube.
    fuera = tuple(x for x in (redacto,) if x)
    preferido = "" if OLLAMA in fuera else OLLAMA
    return _intentar(db, instruccion, None, 0, CAMPOS_REVISION, 700, turno,
                     sin_proveedor=fuera, preferir=preferido, modelo=modelo)


def describir(db: Session, contexto: dict, turno: int | None = None,
              modelo: str = "") -> Propuesta | None:
    """
    Pide la redacción al proveedor con más cuota. Si ese falla o se queda sin cuota, intenta
    con el otro. Si ninguno responde, devuelve None y el expediente queda esperando: jamás
    se fabrica una descripción.
    """
    return _intentar(db, construir_instruccion(contexto), None, contexto.get("folios"),
                     CAMPOS, 1500, turno, preferir=OLLAMA, modelo=modelo)


def _intentar(db: Session, instruccion: str, documento: bytes | None,
              folios: int | None, campos, max_tokens: int,
              turno: int | None = None, sin_proveedor: tuple = (),
              preferir: str = "", modelo: str = "") -> Propuesta | None:
    """
    Recorre la fila de motores hasta que uno responda.

    Cada fallo se anota en la fila de ese motor y el expediente pasa al siguiente, así que un
    modelo retirado o una cuota agotada no detienen la producción. Si se acaban todos los
    motores devuelve None: el expediente espera, y nunca se fabrica un texto.
    """
    intentados: set[str] = set()
    rechazos: list[str] = []
    for _ in range(len(motores()) + 1):
        m = elegir_motor(db, folios, excluir=intentados, turno=turno,
                         sin_proveedor=sin_proveedor, preferir=preferir, modelo=modelo)
        if not m:
            break
        intentados.add(m["clave"])
        try:
            # Se aparta la cuota antes de llamar. Si se contara al terminar, dos expedientes
            # que arrancan a la vez verían el mismo saldo y saldrían por la misma llave.
            _sumar(db, m["clave"])
            db.commit()
            crudo = TRANSPORTES[m["proveedor"]](instruccion, documento, campos, max_tokens,
                                                m["modelo"], m.get("llave_api", ""))
            return Propuesta(m["proveedor"], crudo, m["modelo"])
        except urllib.error.HTTPError as e:
            cuerpo = ""
            try:
                cuerpo = e.read().decode("utf-8", "ignore")[:300]
            except Exception:
                pass
            if e.code in (429, 529):
                _agotar(db, m["clave"], f"Cuota o capacidad agotada ({e.code}).")
            elif documento and e.code in (400, 413):
                # Con documento adjunto, un rechazo de este tipo casi siempre es del archivo.
                # No se apaga la llave: se prueba con otro proveedor, y si dos proveedores
                # distintos lo rechazan, el problema es el documento y se dice así.
                rechazos.append(f"{m['proveedor']} ({e.code}): {cuerpo}")
                if len({r.split(" (")[0] for r in rechazos}) >= 2 or len(rechazos) >= 3:
                    raise DocumentoRechazado(catalogo.tapar(" | ".join(rechazos))[:400])
            elif e.code in (400, 404):
                _agotar(db, m["clave"],
                        f"El proveedor no admite este modelo para esta tarea ({e.code}). {cuerpo}")
            else:
                _agotar(db, m["clave"], f"Error {e.code} del proveedor. {cuerpo}")
        except SinCuota as e:
            _agotar(db, m["clave"], str(e))
        except Exception as e:                                   # red, tiempo de espera, JSON
            _agotar(db, m["clave"], f"{type(e).__name__}: {e}")
    return None
