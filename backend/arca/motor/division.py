"""
División de documentos de gran volumen y control de la secuencia de un expediente partido.

Un expediente puede llegar de dos maneras y las dos tienen que terminar igual:

  1. Por partes, nombradas por quien digitalizó: CARPETA-00001-1, CARPETA-00001-2, ... Cada
     parte se registra con su número y se lee en ese orden, con la numeración de trámites y
     de folios corrida de una a la siguiente.

  2. Entero, en un solo archivo de mil imágenes o más. Ese archivo no lo admite ningún lector
     en una sola petición y tampoco conviene tenerlo así en el depósito. Aquí se divide SOLO
     el sistema, en partes consecutivas de un número fijo de páginas, y cada parte queda
     registrada con el rango de páginas del original que abarca, de modo que la secuencia
     se conserva y se puede demostrar.

En ambos casos, antes de leer se comprueba la secuencia: que no falte una parte en la
mitad (1, 2, 4) y que no haya llegado hace un instante otra parte que todavía no se ve.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import pikepdf

# Páginas por parte cuando el sistema divide un documento cargado entero. En cero no divide.
PAGINAS_POR_PARTE = int(os.getenv("PAGINAS_POR_PARTE", "250"))


@dataclass(frozen=True)
class Parte:
    numero: int
    ruta: Path
    pagina_inicial: int
    pagina_final: int
    tamano_bytes: int
    sha256: str

    @property
    def paginas(self) -> int:
        return self.pagina_final - self.pagina_inicial + 1


def hay_que_dividir(paginas: int, tope: int | None = None) -> bool:
    tope = PAGINAS_POR_PARTE if tope is None else tope
    return bool(tope) and paginas > tope


def _sha(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for trozo in iter(lambda: f.read(1024 * 1024), b""):
            h.update(trozo)
    return h.hexdigest()


def dividir(origen: Path, carpeta: str, destino_dir: Path, nombre_base: str,
            paginas_por_parte: int | None = None) -> list[Parte]:
    """
    Corta el documento en partes consecutivas y las escribe en el depósito.

    Las páginas se copian tal cual —sin recomprimir ni tocar la imagen—, de modo que la suma
    de las partes es el documento original página por página. El original no se borra aquí:
    quien llama decide qué hacer con él una vez las partes quedaron registradas.
    """
    tope = paginas_por_parte or PAGINAS_POR_PARTE
    partes: list[Parte] = []
    destino_dir.mkdir(parents=True, exist_ok=True)
    with pikepdf.open(str(origen)) as pdf:
        total = len(pdf.pages)
        numero = 0
        inicio = 0
        while inicio < total:
            fin = min(inicio + tope, total)
            numero += 1
            ruta = destino_dir / f"{carpeta}_{numero}_{nombre_base}"
            with pikepdf.Pdf.new() as trozo:
                trozo.pages.extend(pdf.pages[inicio:fin])
                trozo.save(str(ruta))
            partes.append(Parte(numero, ruta, inicio + 1, fin, ruta.stat().st_size, _sha(ruta)))
            inicio = fin
    return partes


def faltantes(fragmentos: list[int]) -> list[int]:
    """
    Qué números de parte faltan en la secuencia. [1, 2, 4] → [3]. Un expediente completo
    (fragmento 0) no tiene secuencia que comprobar.
    """
    numeros = sorted({f for f in fragmentos if f > 0})
    if not numeros:
        return []
    return [n for n in range(1, numeros[-1] + 1) if n not in numeros]


def describir_secuencia(fragmentos: list[int]) -> str:
    """Texto para la bitácora: «partes 1 a 4» o «parte única»."""
    numeros = sorted({f for f in fragmentos if f > 0})
    if not numeros:
        return "documento completo en un solo archivo"
    if len(numeros) == 1:
        return f"parte {numeros[0]}"
    return f"partes {numeros[0]} a {numeros[-1]} ({len(numeros)} archivos)"
