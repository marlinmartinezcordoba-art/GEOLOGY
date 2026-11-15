"""Prueba de carga de ARCA: mide, en ESTE servidor, cuánto tarda cada etapa por página y cuántos núcleos hacen falta.

Usa páginas ficticias generadas aquí (no necesita datos de nadie). Mide por separado:

- recepción: control de calidad de la imagen + huella + guardado en el almacén (cifrado si hay llave);
- OCR: Tesseract en español, con detección de orientación (la etapa más pesada);
- PDF/A: la página con su capa de texto y la conversión validada (paquete de entrega).

Luego proyecta, con N procesos en paralelo, cuántas páginas por día procesa el servidor y cuántos núcleos harían
falta para una meta diaria (por defecto 500.000).

Uso:  python scripts/prueba_carga.py --paginas 40 --procesos 4 --meta 500000
"""

import argparse
import io
import math
import statistics
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LINEAS = ["ENTIDAD FICTICIA NACIONAL", "RESOLUCIÓN N.º 101 DE 2015", "Ciudad Ficticia, 2 de enero de 2015",
          "Por la cual se nombra a una persona ficticia en el cargo de profesional", "identificada con C.C. 52.123.456",
          "Que el presente acto se expide en uso de las facultades legales y reglamentarias."] + ["Texto ficticio de relleno para la página."] * 18


def _pagina(n: int) -> bytes:
    from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415

    img = Image.new("L", (2480, 3508), 250)  # A4 a 300 ppp
    d = ImageDraw.Draw(img)
    try:
        fuente = ImageFont.truetype("DejaVuSans.ttf", 42)
    except OSError:
        fuente = ImageFont.load_default()
    y = 250
    for i, linea in enumerate(LINEAS):
        d.text((220, y), f"{linea} {n if i == 1 else ''}", fill=20, font=fuente)
        y += 110
    salida = io.BytesIO()
    img.save(salida, "PNG", dpi=(300, 300))
    return salida.getvalue()


def _medir(n: int) -> dict[str, float]:
    from arca.modulos.entrega import pdfa  # noqa: PLC0415
    from arca.modulos.m10_digitalizacion import calidad  # noqa: PLC0415
    from arca.modulos.m13_ocr import lector  # noqa: PLC0415
    from arca.nucleo import almacen  # noqa: PLC0415

    imagen = _pagina(n)
    t0 = time.perf_counter()
    calidad.ficha_imagen(imagen, 0.995)
    almacen.huella(imagen)
    almacen.guardar(uuid.UUID(int=0), imagen)
    t1 = time.perf_counter()
    lector.orientacion(imagen)
    lector.leer(imagen, "spa")
    t2 = time.perf_counter()
    import pikepdf  # noqa: PLC0415

    pdfa.convertir(pikepdf.open(io.BytesIO(lector.pdf_buscable(imagen))), f"Página {n}")
    t3 = time.perf_counter()
    return {"recepcion": t1 - t0, "ocr": t2 - t1, "pdfa": t3 - t2}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--paginas", type=int, default=24)
    p.add_argument("--procesos", type=int, default=4)
    p.add_argument("--meta", type=int, default=500_000, help="páginas por día que se quieren procesar")
    p.add_argument("--horas", type=float, default=24, help="horas de operación por día")
    a = p.parse_args()

    from arca.modulos.m13_ocr import lector  # noqa: PLC0415

    if not lector.disponible():
        sys.exit("Este servidor no tiene Tesseract: instálelo para medir el OCR.")
    inicio = time.perf_counter()
    with ProcessPoolExecutor(max_workers=a.procesos) as grupo:
        medidas = list(grupo.map(_medir, range(a.paginas)))
    total = time.perf_counter() - inicio
    etapas = {k: statistics.mean(m[k] for m in medidas) for k in medidas[0]}
    por_pagina = sum(etapas.values())  # segundos de un núcleo por página
    paginas_dia = a.paginas / total * 3600 * a.horas
    nucleos = math.ceil(a.meta * por_pagina / (3600 * a.horas))
    print(f"Páginas de prueba: {a.paginas} (A4, 300 ppp) · procesos en paralelo: {a.procesos}")
    for k, v in etapas.items():
        print(f"  {k:<10} {v:6.2f} s por página")
    print(f"Un núcleo, por página, todo el recorrido: {por_pagina:.2f} s")
    print(f"Este servidor ({a.procesos} procesos): {a.paginas / total * 3600:,.0f} páginas por hora · {paginas_dia:,.0f} por día de {a.horas:g} h")
    print(f"Para {a.meta:,} páginas por día hacen falta unos {nucleos} núcleos dedicados (sin contar la base de datos ni la interfaz).")


if __name__ == "__main__":
    main()
