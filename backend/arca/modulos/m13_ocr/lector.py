"""M13 · Lectura OCR local con Tesseract (D-21: los documentos no salen del servidor).

Se llama al programa `tesseract` instalado en el servidor (paquetes `tesseract-ocr` y `tesseract-ocr-spa`), con
salida TSV para tener cada palabra con su confianza. No se usa ningún servicio externo.
"""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from arca.nucleo.errores import DatosInvalidos


@dataclass
class Linea:
    texto: str
    confianza: float  # 0 a 100, promedio de sus palabras


@dataclass
class Lectura:
    texto: str
    confianza: float | None
    palabras: int
    lineas: list[Linea] = field(default_factory=list)


def _entorno() -> dict[str, str]:
    """Hilos por proceso de Tesseract (ARCA_HILOS_OCR, 1 por defecto): con varios trabajadores en paralelo, más hilos
    por proceso no aceleran y saturan los núcleos (una página puede pasar del límite de tiempo)."""
    from arca.nucleo.config import ajustes  # noqa: PLC0415

    return {**os.environ, "OMP_THREAD_LIMIT": str(max(1, ajustes().hilos_ocr))}


def disponible() -> bool:
    return shutil.which("tesseract") is not None


@lru_cache(maxsize=1)
def version() -> str:
    if not disponible():
        return ""
    salida = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=20)
    return (salida.stdout or salida.stderr).splitlines()[0].strip() if (salida.stdout or salida.stderr) else "tesseract"


@lru_cache(maxsize=1)
def idiomas() -> tuple[str, ...]:
    if not disponible():
        return ()
    salida = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=20)
    return tuple(x.strip() for x in salida.stdout.splitlines()[1:] if x.strip())


def exigir(idioma: str = "spa") -> None:
    if not disponible():
        raise DatosInvalidos("El OCR no está disponible en este servidor: instale los paquetes tesseract-ocr y tesseract-ocr-spa")
    if idioma not in idiomas():
        raise DatosInvalidos(f"El idioma «{idioma}» no está instalado para el OCR (instalados: {', '.join(idiomas()) or 'ninguno'})")


def orientacion(imagen_png: bytes, tiempo_maximo: int = 60) -> tuple[int, float]:
    """(grados que está girada la página, confianza) según el modo OSD de Tesseract. (0, 0) si no se pudo saber."""
    if not disponible() or "osd" not in idiomas():
        return 0, 0.0
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "pagina.png"
        ruta.write_bytes(imagen_png)
        r = subprocess.run(["tesseract", str(ruta), "stdout", "--psm", "0"], capture_output=True, text=True, timeout=tiempo_maximo, env=_entorno())
    giro, confianza = 0, 0.0
    for linea in (r.stdout or "").splitlines():
        if linea.startswith("Rotate:"):
            giro = int(linea.split(":")[1].strip() or 0)
        elif linea.startswith("Orientation confidence:"):
            confianza = float(linea.split(":")[1].strip() or 0)
    return (giro if giro in (90, 180, 270) else 0), confianza


def leer(imagen_png: bytes, idioma: str = "spa", tiempo_maximo: int = 180) -> Lectura:
    """Lee una página. Devuelve el texto por líneas, cada una con la confianza promedio de sus palabras."""
    exigir(idioma)
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "pagina.png"
        ruta.write_bytes(imagen_png)
        r = subprocess.run(["tesseract", str(ruta), "stdout", "-l", idioma, "--psm", "3", "tsv"], capture_output=True, text=True, timeout=tiempo_maximo, env=_entorno())
    if r.returncode != 0:
        raise DatosInvalidos(f"El OCR no pudo leer la página: {(r.stderr or '').strip()[:200]}")
    grupos: dict[tuple[int, int, int], list[tuple[str, float]]] = {}
    orden: list[tuple[int, int, int]] = []
    for fila in r.stdout.splitlines()[1:]:
        partes = fila.split("\t")
        if len(partes) < 12 or partes[0] != "5":
            continue
        texto = partes[11].strip()
        if not texto:
            continue
        clave = (int(partes[2]), int(partes[3]), int(partes[4]))  # bloque, párrafo, línea
        if clave not in grupos:
            grupos[clave] = []
            orden.append(clave)
        grupos[clave].append((texto, max(0.0, float(partes[10]))))
    lineas = [Linea(" ".join(p for p, _ in grupos[c]), round(sum(x for _, x in grupos[c]) / len(grupos[c]), 1)) for c in orden]
    palabras = sum(len(grupos[c]) for c in orden)
    confianza = round(sum(x for c in orden for _, x in grupos[c]) / palabras, 1) if palabras else None
    texto, anterior = [], None
    for c, linea in zip(orden, lineas, strict=True):
        if anterior is not None and c[:2] != anterior[:2]:
            texto.append("")  # cambio de párrafo
        texto.append(linea.texto)
        anterior = c
    return Lectura(texto="\n".join(texto), confianza=confianza, palabras=palabras, lineas=lineas)


def pdf_buscable(imagen_png: bytes, idioma: str = "spa", tiempo_maximo: int = 180) -> bytes:
    """La página como PDF con su imagen y, debajo, el texto reconocido: se puede buscar y copiar (renderizador PDF de Tesseract)."""
    exigir(idioma)
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "pagina.png"
        ruta.write_bytes(imagen_png)
        r = subprocess.run(["tesseract", str(ruta), str(Path(carpeta) / "salida"), "-l", idioma, "pdf"], capture_output=True, text=True, timeout=tiempo_maximo, env=_entorno())
        destino = Path(carpeta) / "salida.pdf"
        if r.returncode != 0 or not destino.exists():
            raise DatosInvalidos(f"No se pudo generar el PDF con texto: {(r.stderr or '').strip()[:200]}")
        return destino.read_bytes()
