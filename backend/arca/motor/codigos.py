"""
Códigos de referencia y comparación de textos archivísticos. Funciones puras, recicladas de GEOLOGY.

El reconocimiento del identificador del expediente en el nombre de los archivos vive en
`arca.modulos.m10_digitalizacion.identificacion`, generalizado para cualquier inventario.
"""
from __future__ import annotations

import re
import unicodedata


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
                                consecutivo: int = 1, pais: str = "CO", entidad: str = "ENT", archivo: str = "AC") -> str:
    """
    R4. Código de referencia del elemento 3.1.1 de la norma.
    Formato:  {país}-{entidad}-{archivo}-P{periodo}-S{subserie o serie}-{consecutivo de cinco dígitos}

    >>> construir_codigo_referencia("Periodo II", codigo_subserie="01", consecutivo=7, entidad="ENT")
    'CO-ENT-AC-PII-S01-00007'
    """
    serie = re.sub(r"\s", "", str(codigo_subserie or codigo_serie or "SS"))
    return f"{pais}-{entidad}-{archivo}-P{_romano_del_periodo(periodo)}-S{serie}-{max(1, consecutivo):05d}"


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
