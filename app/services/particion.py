"""
Partición de documentos extensos para la lectura.

Los tomos encuadernados de este fondo —los libros de oficios despachados, los de
correspondencia recibida— pasan con frecuencia de los quinientos folios. Ningún proveedor
de modelos acepta un documento portátil de ese tamaño en una sola petición: hay un tope de
páginas y un tope de peso, y por encima de cualquiera de los dos la petición se rechaza.

Hasta ahora eso obligaba a la archivista a partir el tomo a mano antes de cargarlo. No es
razonable: el expediente es uno solo, la unidad documental no se parte porque el transporte
no dé, y quien tiene que acomodarse es el sistema.

Aquí el archivo se corta en bloques SOLO para efectos de la lectura. El documento en el
almacén no se toca: los bloques viven en memoria mientras dura la petición y se descartan.
La numeración de trámites y de folios sigue corrida de un bloque al siguiente, de modo que
la hoja de control resultante es una sola y no se nota por dónde se cortó.

El corte es por páginas primero y por peso después: un bloque que cumple el tope de páginas
pero pesa de más se vuelve a partir por la mitad, y así hasta que entre o hasta que quede en
una sola página. Una página suelta que aun así pese de más se informa y se salta: eso ya no
es un problema de partición sino de captura, y hay que volver a escanear esa hoja.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pikepdf

# Resolución a la que se aligera la copia que ve el modelo.
#
# 150 puntos por pulgada no es un recorte de calidad: es dejar de mandar lo que el proveedor
# bota. Todos ellos reducen la imagen a unos 1.568 píxeles por el lado largo antes de
# mirarla, y una hoja tamaño carta a 150 puntos da 1.650. Mandarla a 300 significa subir
# cuatro veces más bytes para que al otro lado los descarten.
#
# Y el ahorro no es de bytes nada más. Las llaves gratuitas se limitan por NÚMERO DE
# PETICIONES al día, no por peso. Si en cada bloque caben cuatro veces más páginas, el mismo
# tomo se lee con cuatro veces menos peticiones, y la cuota del día rinde cuatro veces más.
PUNTOS_POR_PULGADA = int(os.getenv("DPI_PARA_EL_MODELO", "150"))
ALIGERAR = os.getenv("ALIGERAR_PARA_EL_MODELO", "1") not in ("0", "no", "false", "")
SEGUNDOS_ALIGERAR = int(os.getenv("SEGUNDOS_ALIGERAR", "900"))


@dataclass(frozen=True)
class Bloque:
    """Un trozo del archivo, listo para enviarse al modelo."""
    numero: int                 # 1, 2, 3... en el orden del documento
    pagina_inicial: int         # numeración de página dentro del ARCHIVO, empieza en 1
    pagina_final: int
    contenido: bytes

    @property
    def paginas(self) -> int:
        return self.pagina_final - self.pagina_inicial + 1

    @property
    def megas(self) -> float:
        return len(self.contenido) / 1048576


class DocumentoIlegible(Exception):
    """El archivo no se puede abrir: está cifrado, truncado o no es un documento portátil."""


def aligerar(origen: Path, destino: Path, dpi: int = 0) -> tuple[bool, str]:
    """
    Una copia liviana del documento, SOLO para mandársela al modelo.

    El archivo del almacén no se toca nunca. Esta copia vive en una carpeta temporal mientras
    dura la lectura y se borra al terminar; la matriz de preservación, que es la reproducción
    fiel y la que hay que poder demostrar que nadie alteró, sigue exactamente donde estaba y
    exactamente como estaba.

    Lo que se quita no es información que el modelo fuera a ver. Los proveedores reducen la
    imagen a unos 1.568 píxeles por el lado largo antes de procesarla, y a 150 puntos por
    pulgada una hoja carta ya llega a 1.650. Lo que se manda de más, se bota al otro lado.

    Si el motor de imagen no está o falla, se devuelve que no se pudo y la lectura sigue con
    el archivo original. Aligerar es una optimización, nunca un requisito.
    """
    if not shutil.which("gs"):
        return False, "no está el motor de imagen (ghostscript)"
    dpi = dpi or PUNTOS_POR_PULGADA
    orden = [
        "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5",
        "-dNOPAUSE", "-dBATCH", "-dQUIET", "-dSAFER",
        # Se reduce la resolución de las imágenes, que es donde está todo el peso.
        "-dDownsampleColorImages=true", f"-dColorImageResolution={dpi}",
        "-dColorImageDownsampleType=/Average",
        "-dDownsampleGrayImages=true", f"-dGrayImageResolution={dpi}",
        "-dGrayImageDownsampleType=/Average",
        # El blanco y negro se deja al doble: ahí es donde vive el trazo fino de la pluma y
        # bajarlo sí borraría lo que hay que leer.
        "-dDownsampleMonoImages=true", f"-dMonoImageResolution={dpi * 2}",
        "-dColorConversionStrategy=/LeaveColorUnchanged",
        f"-sOutputFile={destino}", str(origen),
    ]
    try:
        r = subprocess.run(orden, capture_output=True, text=True, timeout=SEGUNDOS_ALIGERAR)
    except subprocess.TimeoutExpired:
        return False, "el aligerado tardó demasiado"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    if r.returncode != 0 or not destino.exists() or destino.stat().st_size == 0:
        return False, (r.stderr or "el motor de imagen no produjo nada")[:160]

    # Dos comprobaciones antes de fiarse: que no haya perdido páginas y que de verdad pese
    # menos. Un documento ya liviano puede salir más pesado del tratamiento, y en ese caso
    # lo sensato es quedarse con el original.
    try:
        with pikepdf.open(str(origen)) as a, pikepdf.open(str(destino)) as b:
            if len(a.pages) != len(b.pages):
                return False, "el aligerado cambió el número de páginas"
    except Exception as e:
        return False, f"el aligerado quedó ilegible: {type(e).__name__}"
    if destino.stat().st_size >= origen.stat().st_size:
        return False, "el aligerado no quedó más liviano"
    return True, (f"{origen.stat().st_size / 1048576:.0f} MB → "
                  f"{destino.stat().st_size / 1048576:.0f} MB a {dpi} puntos por pulgada")


def contar_paginas(ruta: Path) -> int:
    """Cuántas páginas tiene el archivo. Sirve además de comprobación de que se puede abrir."""
    try:
        with pikepdf.open(str(ruta)) as pdf:
            return len(pdf.pages)
    except Exception as e:
        raise DocumentoIlegible(
            f"No se pudo abrir {Path(ruta).name}: {type(e).__name__}.") from e


def _serializar(pdf: pikepdf.Pdf, desde: int, hasta: int) -> bytes:
    """Devuelve las páginas [desde, hasta) como un documento portátil independiente."""
    memoria = io.BytesIO()
    with pikepdf.Pdf.new() as trozo:
        trozo.pages.extend(pdf.pages[desde:hasta])
        trozo.save(memoria)
    return memoria.getvalue()


def bloques(ruta: Path, tope_paginas: int = 100, tope_mb: int = 30,
            avisos: list[str] | None = None, aligerando: bool | None = None) -> Iterator[Bloque]:
    """
    Recorre el archivo entregando bloques que sí caben en una petición.

    Se entregan de a uno y se sueltan de la memoria en cuanto el bloque anterior se usó: un
    tomo de ochocientas páginas nunca está entero en memoria dos veces.

    Cuando el archivo ya cabe se entrega tal cual viene, sin volver a escribirlo. Eso importa:
    reescribir el documento cambiaría su huella y el modelo leería algo que no es byte por
    byte lo que está guardado en el almacén.
    """
    anotar = avisos if avisos is not None else []
    ruta = Path(ruta)

    # Primero se aligera el documento ENTERO, una sola vez, y después se corta. Hacerlo al
    # revés —aligerar cada bloque— costaría una pasada del motor de imagen por bloque, y en
    # un tomo de ochocientas páginas eso son decenas de pasadas para el mismo resultado.
    temporal = None
    trabajo = ruta
    if (ALIGERAR if aligerando is None else aligerando):
        temporal = Path(tempfile.mkdtemp(prefix="kustos-liviano-"))
        liviano = temporal / ruta.name
        bien, detalle = aligerar(ruta, liviano)
        if bien:
            trabajo = liviano
            anotar.append(f"Para leerlo se usó una copia liviana de {ruta.name} ({detalle}). "
                          "El archivo del almacén no se tocó.")
        else:
            shutil.rmtree(temporal, ignore_errors=True)
            temporal = None

    peso = trabajo.stat().st_size

    try:
        pdf = pikepdf.open(str(trabajo))
    except Exception as e:
        if temporal:
            shutil.rmtree(temporal, ignore_errors=True)
        raise DocumentoIlegible(f"No se pudo abrir {ruta.name}: {type(e).__name__}") from e

    try:
      with pdf:
          total = len(pdf.pages)
          if total == 0:
              raise DocumentoIlegible(f"{ruta.name} no tiene páginas.")

          # El caso corriente: una carpeta normal que cabe entera.
          if total <= tope_paginas and peso <= tope_mb * 1048576:
              yield Bloque(1, 1, total, trabajo.read_bytes())
              return

          numero = 0
          pendientes: list[tuple[int, int]] = []           # tramos [desde, hasta) por procesar
          inicio = 0
          while inicio < total:
              pendientes.append((inicio, min(inicio + tope_paginas, total)))
              inicio += tope_paginas

          for desde, hasta in pendientes:
              # Cada tramo se vuelve a partir por la mitad mientras pese de más.
              cola = [(desde, hasta)]
              while cola:
                  a, b = cola.pop(0)
                  contenido = _serializar(pdf, a, b)
                  if len(contenido) <= tope_mb * 1048576 or b - a == 1:
                      if len(contenido) > tope_mb * 1048576:
                          anotar.append(
                              f"La página {a + 1} de {ruta.name} pesa "
                              f"{len(contenido) / 1048576:.0f} MB ella sola y no se pudo enviar. "
                              "Hay que volver a capturar esa hoja con menos resolución o en "
                              "escala de grises.")
                          continue
                      numero += 1
                      yield Bloque(numero, a + 1, b, contenido)
                  else:
                      mitad = a + (b - a) // 2
                      cola.insert(0, (mitad, b))
                      cola.insert(0, (a, mitad))
    finally:
        # La copia liviana se borra siempre: no es un archivo del proyecto, es un andamio.
        if temporal:
            shutil.rmtree(temporal, ignore_errors=True)
