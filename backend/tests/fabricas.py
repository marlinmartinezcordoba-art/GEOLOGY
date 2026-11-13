"""Archivos ficticios para las pruebas: FUID en Excel, PDF escaneados e imágenes por página."""

import io
import itertools

import openpyxl
from PIL import Image, ImageDraw


def fuid_xlsx(filas: list[list], con_identificador: bool = True) -> bytes:
    """FUID con membrete y encabezado de dos niveles, como el formato del AGN."""
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["FORMATO ÚNICO DE INVENTARIO DOCUMENTAL"])
    hoja.append(["ENTIDAD REMITENTE: Entidad Ficticia"])
    hoja.append([])
    arriba = ["Número de orden"] + (["Código de la carpeta"] if con_identificador else []) + [
        "Código", "Nombre de las series, subseries o asuntos", "Fechas extremas", "", "Unidad de conservación", "", "", "", "Número de folios", "Soporte", "Notas"]
    abajo = [""] + ([""] if con_identificador else []) + ["", "", "Inicial", "Final", "Caja", "Carpeta", "Tomo", "Otro", "", "", ""]
    hoja.append(arriba)
    hoja.append(abajo)
    for f in filas:
        hoja.append(f)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


_CONTADOR = itertools.count(1)


def imagen(dpi: int = 300, en_blanco: bool = False, modo: str = "L", formato: str = "TIFF", ancho_pulgadas: float = 2.0) -> bytes:
    """Cada llamada produce una imagen distinta (como dos hojas reales), salvo que se quiera un duplicado exacto."""
    lado = int(dpi * ancho_pulgadas)
    img = Image.new(modo, (lado, int(lado * 1.3)), "white")
    n = next(_CONTADOR)
    if not en_blanco:
        dibujo = ImageDraw.Draw(img)
        for i in range(0, lado, max(4, lado // 12)):
            dibujo.rectangle([i, i // 2, i + lado // 20, i // 2 + lado // 3], fill="black")
    # Una marca mínima en la esquina inferior hace única cada hoja, sin cambiar si está en blanco o no.
    img.putpixel((lado - 1 - n % 50, int(lado * 1.3) - 1 - (n // 50) % 50), 0 if not en_blanco else 250)
    salida = io.BytesIO()
    img.save(salida, formato, dpi=(dpi, dpi))
    return salida.getvalue()


def pdf_escaneado(paginas: int = 2, dpi: int = 300) -> bytes:
    hojas = [Image.open(io.BytesIO(imagen(dpi, formato="PNG"))).convert("RGB") for _ in range(paginas)]
    salida = io.BytesIO()
    hojas[0].save(salida, "PDF", resolution=dpi, save_all=True, append_images=hojas[1:])
    return salida.getvalue()


def pagina_con_texto(lineas: list[str]) -> Image.Image:
    """Una página escaneada ficticia con texto legible."""
    from PIL import ImageDraw, ImageFont

    img = Image.new("RGB", (1700, 2200), (250, 250, 250))
    d = ImageDraw.Draw(img)
    y = 180
    for i, linea in enumerate(lineas):
        fuente = ImageFont.truetype("DejaVuSans.ttf", 44 if i < 2 else 36)
        d.text((150, y), linea, fill=(20, 20, 20), font=fuente)
        y += 90 if i < 2 else 66
    return img


def pdf_con_texto(paginas: list[list[str]], dpi: int = 200, giro: int = 0) -> bytes:
    """PDF escaneado de documentos ficticios con texto legible, para probar el OCR (`giro`: páginas escaneadas giradas)."""
    hojas = [pagina_con_texto(lineas).rotate(giro, expand=True) for lineas in paginas]
    salida = io.BytesIO()
    hojas[0].save(salida, "PDF", resolution=dpi, save_all=True, append_images=hojas[1:])
    return salida.getvalue()
