"""Reconocer a qué unidad del inventario pertenece cada archivo de una carpeta cargada. Funciones puras.

Reciclado y generalizado de GEOLOGY (dominio/codigos.py): allí el prefijo del código era fijo; en ARCA el
identificador es el del inventario de cada proyecto y se compara por su clave normalizada.

Dos formas de entrega (decisión D-20):
- PDF por expediente: «CP-00374.pdf», «CARPETA_00374-2.pdf», «carpeta 374 parte 3.pdf» → unidad y parte.
- Una imagen por página: «CP-00374/0001.tif» (la subcarpeta es la unidad) o «CP-00374_0001.tif»
  (el nombre lleva la unidad y el número de página).
"""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from arca.modulos.m08_inventarios.fuid import clave_de

EXT_PDF = (".pdf",)
EXT_IMAGEN = (".tif", ".tiff", ".jpg", ".jpeg", ".png")

# Cada quien nombra las partes como le sale: «_5», «-5», «parte 5», «pte 5», «(5)». Todas deben entrar.
_PARTE = re.compile(r"(?:[-_ ]+(?:PARTE|PTE|PART|P)[-_ .]*|[-_ ]+|\s*\(\s*)(\d{1,3})\s*\)?$", re.IGNORECASE)
_PARTE_EXPLICITA = re.compile(r"\b(?:PARTE|PTE|PART)[-_ .]*(\d{1,3})\b", re.IGNORECASE)
_PAGINA = re.compile(r"(?:^|[-_ .])(\d{1,6})$")


@dataclass(frozen=True)
class Candidato:
    """Lo que se deduce de la ruta de un archivo, antes de buscarlo en el inventario."""

    modalidad: str  # pdf | imagen
    opciones: tuple[tuple[str, int], ...]  # (clave posible de la unidad, parte), en orden de preferencia
    pagina: int | None  # número de página de una imagen
    carpeta: str | None  # subcarpeta inmediata


def modalidad_de(nombre: str) -> str | None:
    n = nombre.lower()
    if n.endswith(EXT_PDF):
        return "pdf"
    if n.endswith(EXT_IMAGEN):
        return "imagen"
    return None


def _sin_extension(nombre: str) -> str:
    return nombre.rsplit(".", 1)[0] if "." in nombre else nombre


def _limpiar_ruta(ruta: str) -> PurePosixPath:
    partes = [p for p in ruta.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    return PurePosixPath(*partes) if partes else PurePosixPath("archivo")


def numero_final(clave: str) -> int | None:
    """El último grupo de dígitos de una clave: «CP374» → 374. Sirve cuando el prefijo del archivo no es el del FUID."""
    m = re.search(r"(\d+)$", clave or "")
    return int(m.group(1)) if m else None


def analizar(ruta: str, identificar_por: str = "archivo_o_carpeta") -> Candidato | None:
    camino = _limpiar_ruta(ruta)
    modalidad = modalidad_de(camino.name)
    if modalidad is None:
        return None
    base = _sin_extension(camino.name).strip()
    carpeta = camino.parent.name if len(camino.parts) > 1 else None
    opciones: list[tuple[str, int]] = []
    por_archivo = identificar_por in ("archivo_o_carpeta", "archivo")
    por_carpeta = identificar_por in ("archivo_o_carpeta", "carpeta") and carpeta

    if modalidad == "pdf":
        if por_archivo:
            # «… parte 3» se reconoce donde esté; el sufijo corto («-2», «_2») solo al final y puede ser parte del código.
            if m := _PARTE_EXPLICITA.search(base):
                opciones.append((clave_de((base[: m.start()] + base[m.end() :]).strip(" -_")), int(m.group(1))))
            elif m := _PARTE.search(base):
                opciones.append((clave_de(base[: m.start()]), int(m.group(1))))
            opciones.append((clave_de(base), 0))
        if por_carpeta:
            opciones.append((clave_de(carpeta), 0))
        return Candidato("pdf", tuple(dict.fromkeys(o for o in opciones if o[0])), None, carpeta)

    pagina = int(m.group(1)) if (m := _PAGINA.search(base)) else None
    if por_carpeta:
        opciones.append((clave_de(carpeta), 0))
    if por_archivo and m and (resto := base[: m.start()].strip(" -_.")):
        opciones.append((clave_de(resto), 0))
    return Candidato("imagen", tuple(dict.fromkeys(o for o in opciones if o[0])), pagina, carpeta)


def ordenar_natural(rutas: list[str]) -> list[str]:
    """«2.tif» antes que «10.tif»: el orden en que las ve una persona."""
    return sorted(rutas, key=lambda r: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", r)])


def saltos(numeros: list[int]) -> list[int]:
    """Los números que faltan entre el menor y el mayor (páginas o partes)."""
    if not numeros:
        return []
    presentes = set(numeros)
    return [n for n in range(min(presentes), max(presentes) + 1) if n not in presentes]
