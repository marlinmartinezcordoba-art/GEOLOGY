"""
Códigos, cajas y expedientes fraccionados.  Reglas R1 a R5.

Transcripción de partesDeArchivo_, codigoCarpetaDeArchivo_, normalizarCodigoCarpeta_,
normalizarCodigoCajaTrabajo_ y construirCodigoReferencia_ del motor anterior.
Son funciones puras: no tocan la base de datos y se prueban solas.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

PREFIJO_CARPETA = "AC-CP"
PAIS = "CO"
ENTIDAD = "SGC"
ARCHIVO = "AC"

# Las tres numeraciones de caja que conviven (R5)
CAJA_ORIGEN = "AC-CJ"        # caja de origen del archivo central del Servicio Geológico
CAJA_TRABAJO = "733-CJ"      # caja de trabajo del contrato 733
CAJA_DEFINITIVA = "AH-CJ"    # caja definitiva X-100

# Un libro empastado de mil folios se sube por partes, y cada quien las nombra como le sale:
# «_5», «-5», «parte 5», «pte 5», «p5», «(5)». Todas quieren decir lo mismo y todas tienen que
# entrar, porque obligar a renombrar cien archivos antes de subirlos es trabajo inventado.
_SEPARADOR_PARTE = r"(?:[-_ ]+(?:PARTE|PTE|PART|P)?[-_ .]*|\s*\(\s*)"
_PARTE = rf"(?:{_SEPARADOR_PARTE}(\d{{1,3}})\s*\)?)?"

_PATRONES_CARPETA = (
    re.compile(rf"AC[-_ ]?CP[-_ ]?(\d{{1,6}}){_PARTE}$"),
    re.compile(rf"CARPETA[-_ ]?(\d{{1,6}}){_PARTE}$"),
    re.compile(rf"^(\d{{1,6}}){_PARTE}$"),
)
_EXTENSIONES = re.compile(r"\.(PDF|XLSX|XLS|CSV|GSHEET)$")


@dataclass(frozen=True)
class PartesArchivo:
    """Resultado de descomponer el nombre de un archivo cargado."""
    carpeta: str | None      # 'AC-CP-93608'
    fragmento: int           # 0 cuando el expediente viene completo, 1..n cuando viene por partes

    @property
    def es_fragmento(self) -> bool:
        return self.fragmento > 0


def partes_de_archivo(nombre_archivo: str) -> PartesArchivo:
    """
    R1 y R2. Deduce el código de carpeta y el número de parte del nombre del archivo.

    >>> partes_de_archivo("CARPETA_093608-2.pdf")
    PartesArchivo(carpeta='AC-CP-93608', fragmento=2)
    >>> partes_de_archivo("AC-CP-00374.pdf")
    PartesArchivo(carpeta='AC-CP-00374', fragmento=0)
    >>> partes_de_archivo("CARPETA 93072 parte 7.pdf")
    PartesArchivo(carpeta='AC-CP-93072', fragmento=7)
    """
    texto = _EXTENSIONES.sub("", str(nombre_archivo or "").upper()).strip()
    for patron in _PATRONES_CARPETA:
        encontrado = patron.search(texto)
        if encontrado:
            consecutivo = int(encontrado.group(1))
            fragmento = int(encontrado.group(2)) if encontrado.group(2) else 0
            return PartesArchivo(f"{PREFIJO_CARPETA}-{consecutivo:05d}", fragmento)

    # Último intento, para los nombres que llevan además el título del tomo: «AC-CP-00808 TOMO
    # XV PARTE 3». Aquí el código se busca donde sea y la parte solo se acepta si viene dicha
    # con todas sus letras, que es la única forma de no confundirla con un año o un folio.
    codigo = re.search(r"(?:AC[-_ ]?CP[-_ ]?|CARPETA[-_ ]?)(\d{1,6})", texto)
    if codigo:
        parte = re.search(r"\b(?:PARTE|PTE|PART)[-_ .]*(\d{1,3})\b", texto)
        return PartesArchivo(f"{PREFIJO_CARPETA}-{int(codigo.group(1)):05d}",
                             int(parte.group(1)) if parte else 0)
    return PartesArchivo(None, 0)


def codigo_carpeta_de_archivo(nombre_archivo: str) -> str | None:
    """R1. Solo el código de carpeta, sin el número de parte."""
    return partes_de_archivo(nombre_archivo).carpeta


def normalizar_codigo_carpeta(codigo: str) -> str | None:
    """R1. Lleva cualquier forma escrita a AC-CP-#####."""
    return codigo_carpeta_de_archivo(codigo)


def normalizar_codigo_caja(codigo: str) -> str | None:
    """
    R5. Reconoce las tres numeraciones y las devuelve normalizadas a cinco dígitos.
    Un número suelto no se acepta, porque no permite saber de cuál de las tres se trata.
    """
    texto = str(codigo or "").upper().strip().replace("_", "-").replace(" ", "")
    encontrado = re.fullmatch(r"(AC-?CJ|733-?CJ|AH-?CJ)-?(\d{1,5})", texto)
    if not encontrado:
        return None
    tipo = encontrado.group(1).replace("ACCJ", "AC-CJ").replace("733CJ", "733-CJ").replace("AHCJ", "AH-CJ")
    if "-" not in tipo:
        tipo = {"ACCJ": CAJA_ORIGEN, "733CJ": CAJA_TRABAJO, "AHCJ": CAJA_DEFINITIVA}.get(tipo, tipo)
    return f"{tipo}-{int(encontrado.group(2)):05d}"


def tipo_de_caja(codigo: str) -> str | None:
    """R5. Dice a cuál de las tres numeraciones pertenece un código de caja."""
    normalizado = normalizar_codigo_caja(codigo)
    return normalizado.rsplit("-", 1)[0] if normalizado else None


def _romano_del_periodo(valor: str) -> str:
    """
    R4. Extrae el numeral del periodo de un texto libre.  Transcripción de extraerPeriodo_.
    Devuelve 'SP' cuando no se puede determinar.
    """
    texto = unicodedata.normalize("NFD", str(valor or "").upper())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    for patron in (r"PERIODO\s+([IVX]{1,6})\b", r"\b([IVX]{1,6})\b"):
        encontrado = re.search(patron, texto)
        if encontrado:
            return encontrado.group(1)
    for patron in (r"\bPERIODO\s*(\d{1,2})\b", r"\bP\s*(\d{1,2})\b"):
        encontrado = re.search(patron, texto)
        if encontrado:
            return encontrado.group(1)
    encontrado = re.search(r"\b(1[89]\d{2}|20\d{2})\b", texto)
    return encontrado.group(1) if encontrado else "SP"


def construir_codigo_referencia(periodo: str, codigo_subserie: str = "", codigo_serie: str = "",
                                consecutivo: int = 1) -> str:
    """
    R4. Código de referencia del elemento 3.1.1 de la norma.
    Formato vigente:  CO-SGC-AC-P{periodo}-S{subserie o serie}-{consecutivo de cinco dígitos}

    >>> construir_codigo_referencia("Periodo II", codigo_subserie="01", consecutivo=7)
    'CO-SGC-AC-PII-S01-00007'
    """
    serie = re.sub(r"\s", "", str(codigo_subserie or codigo_serie or "SS"))
    return f"{PAIS}-{ENTIDAD}-{ARCHIVO}-P{_romano_del_periodo(periodo)}-S{serie}-{max(1, consecutivo):05d}"


def normalizar_texto(valor: str) -> str:
    """Sin tildes, sin signos y en mayúsculas. Se usa para comparar nombres de series."""
    texto = unicodedata.normalize("NFD", str(valor or ""))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]", "", texto.upper())


# Palabras que no distinguen nada: aparecen en casi todos los asuntos y en casi todos los
# nombres de subserie, así que contarlas produce coincidencias falsas.
VACIAS = {"DE", "DEL", "LA", "LAS", "EL", "LOS", "Y", "EN", "CON", "POR", "PARA", "NO", "AL",
          "UN", "UNA", "SOBRE", "ANO", "ANOS", "ENTRE", "DESDE", "HASTA", "SUS", "SU",
          "GENERAL", "GENERALES", "VARIOS", "VARIAS", "OTROS", "OTRAS"}


def palabras_significativas(texto: str, minimo: int = 4) -> set[str]:
    """
    Las palabras con las que vale la pena comparar dos textos.

    HALLAZGO. Antes esto se hacía normalizando el texto entero y partiéndolo por un separador
    puesto a mano, pero normalizar_texto borra todo lo que no sea letra o número, incluido ese
    separador: el resultado era una sola palabra pegada y la comparación nunca encontraba nada.
    Por eso la propuesta automática de subserie por coincidencia con el asunto no proponía
    nunca. Aquí se normaliza palabra por palabra.
    """
    salida = set()
    for bruta in str(texto or "").replace("/", " ").replace("-", " ").split():
        limpia = normalizar_texto(bruta)
        if len(limpia) >= minimo and limpia not in VACIAS:
            salida.add(limpia)
    return salida
