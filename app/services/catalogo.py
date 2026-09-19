"""
Qué modelos tiene disponibles cada proveedor, preguntándoselo a ellos.

En vez de dejar escritos en el código los nombres de los modelos, que cambian cada pocos
meses y quedan desactualizados sin que nadie se dé cuenta, la plataforma le pregunta a cada
proveedor qué modelos admite la cuenta cuya llave está en el archivo .env. Así, el día que
salga uno nuevo entra solo al reparto y el día que retiren uno viejo deja de intentarse.

El catálogo se consulta una vez y se guarda en memoria unas horas, porque preguntar en cada
expediente sería gastar llamadas en algo que casi nunca cambia.

Si quiere fijar la lista a mano, escriba en el .env MODELOS_CLAUDE, MODELOS_GEMINI o
MODELOS_OPENAI con los nombres separados por comas y esa lista manda sobre lo que responda
el proveedor. EXCLUIR_MODELOS saca de la rotación los que no quiera usar.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import time
import urllib.error
import urllib.request

CLAUDE = "claude"
GEMINI = "gemini"
OPENAI = "openai"
# El cuarto proveedor no está en la nube: corre en el computador del equipo, con Ollama.
# No gasta cuota de nadie y, sobre todo, el documento no sale de la máquina.
OLLAMA = "ollama"

HORAS_DE_CACHE = float(os.getenv("HORAS_CATALOGO", "6"))

# Nivel del modelo. Sirve para mandarle los expedientes gordos a los modelos de más aliento
# y los delgados a los ligeros, que es lo que hace que ninguno se sature.
ALTO, MEDIO, BAJO = "alto", "medio", "bajo"

# Se comparan por pieza del nombre, no por pedazo de texto suelto. Buscar "mini" dentro de
# la palabra encuentra "geMINIi" y clasifica un modelo grande como ligero, que es justo al
# revés de lo que se quiere.
_PISTAS_ALTO = {"opus", "ultra", "pro", "max", "o1", "o3", "thinking", "reasoning"}
_PISTAS_BAJO = {"haiku", "flash", "mini", "nano", "lite", "8b", "small", "turbo", "tiny"}

# Lo que no sirve para leer expedientes: audio, música, video, imagen, robótica,
# incrustaciones, moderación, voz y herramientas de programación.
_NO_SIRVEN = ("embedding", "embed", "tts", "whisper", "audio", "realtime", "moderation",
              "image", "dall-e", "sora", "veo", "imagen", "transcribe", "search",
              "codex", "computer-use", "aqa", "gemma", "learnlm", "lyria", "robotics",
              "clip", "antigravity", "live", "dialog", "music", "speech", "guard")

# Cada proveedor nombra sus modelos de lectura con un prefijo reconocible. Pedir el prefijo
# evita que entren al reparto los modelos de música, robótica o video que el catálogo
# devuelve mezclados. Si algún día sale uno con otro nombre, se fija a mano con la variable
# MODELOS_GEMINI, MODELOS_CLAUDE o MODELOS_OPENAI del archivo .env.
# Ollama no aparece aquí a propósito: los modelos locales se llaman como quiera quien los
# descargue —llama3.1:8b, qwen2.5, mistral, un modelo propio— y no hay prefijo que valga.
_PREFIJOS = {CLAUDE: ("claude",), GEMINI: ("gemini",), OPENAI: ("gpt", "o1", "o3", "o4")}

_cache: dict[str, tuple[float, list[str]]] = {}


def _piezas(modelo: str) -> set[str]:
    """El nombre del modelo partido en piezas: gemini-2.5-pro da gemini, 2, 5, pro."""
    return {p for p in re.split(r"[^a-z0-9]+", (modelo or "").lower()) if p}


def nivel(modelo: str) -> str:
    piezas = _piezas(modelo)
    if piezas & _PISTAS_BAJO:
        return BAJO
    if piezas & _PISTAS_ALTO:
        return ALTO
    return MEDIO


def _sirve(modelo: str, proveedor: str = "") -> bool:
    m = (modelo or "").lower()
    if not m:
        return False
    if any(p in m for p in _NO_SIRVEN):
        return False
    prefijos = _PREFIJOS.get(proveedor)
    if prefijos and not m.startswith(prefijos):
        return False
    return True


def _excluidos() -> set[str]:
    return {x.strip().lower() for x in os.getenv("EXCLUIR_MODELOS", "").split(",") if x.strip()}


def _pedir(url: str, cabeceras: dict, segundos: int = 30) -> dict:
    peticion = urllib.request.Request(url, headers=cabeceras, method="GET")
    with urllib.request.urlopen(peticion, timeout=segundos) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def _de_claude(clave: str) -> list[str]:
    datos = _pedir("https://api.anthropic.com/v1/models?limit=100",
                   {"x-api-key": clave, "anthropic-version": "2023-06-01"})
    return [m["id"] for m in datos.get("data", []) if m.get("id")]


def _de_gemini(clave: str) -> list[str]:
    datos = _pedir(f"https://generativelanguage.googleapis.com/v1beta/models?key={clave}"
                   "&pageSize=200", {})
    salida = []
    for m in datos.get("models", []):
        metodos = m.get("supportedGenerationMethods") or m.get("supportedActions") or []
        if metodos and "generateContent" not in metodos:
            continue
        nombre = (m.get("name") or "").split("/")[-1]
        if nombre:
            salida.append(nombre)
    return salida


def _de_openai(clave: str) -> list[str]:
    datos = _pedir("https://api.openai.com/v1/models", {"authorization": "Bearer " + clave})
    return [m["id"] for m in datos.get("data", [])
            if m.get("id", "").startswith(("gpt-", "o1", "o3", "o4"))]


def _de_ollama(direccion: str) -> list[str]:
    """
    Los modelos que el equipo tenga descargados. La «llave» de este proveedor no es una
    credencial sino la dirección donde escucha Ollama, porque es local y no autentica.

    Se espera poco: si Ollama no está instalado o está apagado, la conexión se rechaza en
    seguida y el proveedor simplemente no entra al reparto. Nadie tiene que apagar nada.
    """
    datos = _pedir(direccion.rstrip("/") + "/api/tags", {}, segundos=5)
    return [m["name"] for m in datos.get("models", []) if m.get("name")]


_CONSULTAS = {CLAUDE: _de_claude, GEMINI: _de_gemini, OPENAI: _de_openai, OLLAMA: _de_ollama}
_VARIABLE_LLAVE = {CLAUDE: "ANTHROPIC_API_KEY", GEMINI: "GEMINI_API_KEY",
                   OPENAI: "OPENAI_API_KEY", OLLAMA: "OLLAMA_URL"}
_VARIABLE_LISTA = {CLAUDE: "MODELOS_CLAUDE", GEMINI: "MODELOS_GEMINI",
                   OPENAI: "MODELOS_OPENAI", OLLAMA: "MODELOS_OLLAMA"}

# KUSTOS corre dentro de un contenedor y Ollama corre en Windows, así que desde aquí NO se
# llega por «localhost»: ese localhost es el del contenedor, no el del computador. El nombre
# host.docker.internal es el que Docker reserva para decir «la máquina de afuera».
# Para apagar el modelo local basta con dejar OLLAMA_URL vacío en el archivo .env.
OLLAMA_POR_OMISION = "http://host.docker.internal:11434"


# Hasta cuántas llaves numeradas se buscan por proveedor: GEMINI_API_KEY_1 … _30.
LLAVES_NUMERADAS = 30

# Dónde puede estar el archivo de configuración, en orden de preferencia. El primero es el
# sitio donde queda montado dentro del contenedor; el segundo, la raíz del proyecto cuando
# se ejecuta fuera de Docker.
_RUTAS_ENV = (Path("/code/.env"),
              Path(__file__).resolve().parent.parent.parent / ".env")


def _leer_archivo_env() -> dict[str, str]:
    """
    Lee el archivo .env por su cuenta, sin pasar por Docker.

    HALLAZGO del 10 de septiembre de 2026, y costó una jornada entera. Docker entrega las
    variables del archivo .env al contenedor UNA SOLA VEZ, cuando lo crea. Un
    «docker compose restart» no las vuelve a leer, y según la versión, un «up -d» tampoco
    siempre. El resultado es que se agregan ocho llaves al archivo, se reinicia, y la
    plataforma sigue viendo una sola sin decir por qué.

    Depender de eso es frágil. Aquí se lee el archivo directamente: lo que Docker haya
    entregado manda, y lo que falte se completa con lo que diga el archivo. Así, agregar una
    llave y reiniciar funciona siempre, y si un día el archivo no está montado, la
    plataforma sigue andando con lo que Docker le haya pasado.
    """
    salida: dict[str, str] = {}
    for ruta in _RUTAS_ENV:
        try:
            if not ruta.is_file():
                continue
            for renglon in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
                limpio = renglon.strip()
                if not limpio or limpio.startswith("#") or "=" not in limpio:
                    continue
                nombre, _, valor = limpio.partition("=")
                nombre = nombre.strip()
                valor = valor.strip().strip('"').strip("'")
                if nombre and valor and nombre not in salida:
                    salida[nombre] = valor
            break
        except OSError:
            continue
    return salida


def _valor(nombre: str) -> str:
    """El valor de una variable, primero de Docker y si no, del archivo."""
    return (os.getenv(nombre, "") or _leer_archivo_env().get(nombre, "")).strip()


def claves_de(proveedor: str) -> list[str]:
    """
    Las llaves de un proveedor. Se pueden escribir de dos maneras y se pueden mezclar.

    La primera, todas en un renglón separadas por comas:

        GEMINI_API_KEY=AIza_la_primera,AIza_la_segunda,AIza_la_tercera

    La segunda, y la que conviene cuando son muchas, una por renglón numerada:

        GEMINI_API_KEY_1=AIza_la_de_Camila
        GEMINI_API_KEY_2=AIza_la_de_Maritza
        GEMINI_API_KEY_3=AIza_la_de_Wilmar

    Con diez llaves en un solo renglón basta una coma mal puesta para perder una y no
    enterarse. Numeradas se leen de a una, se puede anotar de quién es cada una encima con
    un signo de número, y para sacar una del reparto se le pone ese signo delante en lugar
    de andar cortando y pegando dentro de una línea larguísima.

    Se conserva el orden —primero el renglón con comas, luego las numeradas de la 1 en
    adelante— y se quitan las repetidas, así que una misma llave escrita dos veces no cuenta
    dos veces ni duplica su cuota.
    """
    variable = _VARIABLE_LLAVE[proveedor]
    if proveedor == OLLAMA:
        # Si nadie escribió nada se intenta la dirección de siempre; si la escribió vacía a
        # propósito, se respeta y el modelo local queda fuera del reparto.
        crudo = _valor(variable)
        if crudo.strip():
            return [crudo.strip()]
        return [] if variable in _leer_archivo_env() or variable in os.environ \
            else [OLLAMA_POR_OMISION]
    crudos = [_valor(variable)]
    for numero in range(1, LLAVES_NUMERADAS + 1):
        crudos.append(_valor(f"{variable}_{numero}"))

    vistas: list[str] = []
    for crudo in crudos:
        for pedazo in re.split(r"[,\s]+", crudo or ""):
            llave = pedazo.strip()
            if llave and llave not in vistas:
                vistas.append(llave)
    return vistas


def modelos_de(proveedor: str, forzar: bool = False) -> list[str]:
    """
    Los modelos utilizables de un proveedor. Devuelve lista vacía si no hay llave o si el
    proveedor no responde: en ese caso ese proveedor simplemente no entra al reparto.

    La lista se pide con la PRIMERA llave del proveedor. Si otra llave es de una cuenta con
    menos modelos habilitados, los que no le sirvan fallarán en su primer intento y quedarán
    marcados; no hay que hacer nada.
    """
    fijos = [x.strip() for x in os.getenv(_VARIABLE_LISTA[proveedor], "").split(",") if x.strip()]
    if fijos:
        return [m for m in fijos if m.lower() not in _excluidos()]

    llaves = claves_de(proveedor)
    if not llaves:
        return []
    clave = llaves[0]

    guardado = _cache.get(proveedor)
    if guardado and not forzar and (time.time() - guardado[0]) < HORAS_DE_CACHE * 3600:
        return guardado[1]

    try:
        crudos = _CONSULTAS[proveedor](clave)
    except Exception:
        # Si el proveedor no contesta se conserva lo último que se supo, y si nunca se supo
        # nada se devuelve vacío. Nunca se inventa un nombre de modelo.
        return guardado[1] if guardado else []

    fuera = _excluidos()
    utiles = sorted({m for m in crudos if _sirve(m, proveedor) and m.lower() not in fuera})
    _cache[proveedor] = (time.time(), utiles)
    return utiles


def catalogo(forzar: bool = False) -> dict[str, list[str]]:
    """Todos los modelos disponibles, por proveedor."""
    return {p: modelos_de(p, forzar) for p in (CLAUDE, GEMINI, OPENAI, OLLAMA)}


def olvidar() -> None:
    """Borra lo guardado para que la próxima consulta vuelva a preguntarle a los proveedores."""
    _cache.clear()


def tapar(texto: str) -> str:
    """
    Quita de un texto cualquier cosa que se parezca a una llave, antes de guardarlo en la
    bitácora o mostrarlo en pantalla. Un mensaje de error de un proveedor puede traer de
    vuelta la dirección completa con la llave dentro, y esa no puede quedar escrita en
    ningún lado.
    """
    limpio = str(texto or "")
    for proveedor in (CLAUDE, GEMINI, OPENAI):
        for llave in claves_de(proveedor):
            if len(llave) > 8:
                limpio = limpio.replace(llave, "«llave oculta»")
    # Por si aparece una que no está configurada aquí, se tapan las formas conocidas.
    limpio = re.sub(r"(sk-[A-Za-z0-9_\-]{12,}|AIza[A-Za-z0-9_\-]{20,}|AQ\.[A-Za-z0-9_\-]{20,})",
                    "«llave oculta»", limpio)
    return limpio
