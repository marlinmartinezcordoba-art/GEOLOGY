"""Las páginas de un expediente digitalizado, en orden, y la imagen de cada una (para el visor y el OCR).

Los PDF se ordenan por su parte y las imágenes sueltas por su número de página. No cuentan los archivos reemplazados
por una recaptura, los rechazados ni los que no se pudieron asociar.
"""

import io
from typing import Any

from sqlalchemy import select

from arca.modelos import ArchivoDigital, EstadoRecurso, RecursoDigital, UnidadDocumental
from arca.nucleo import almacen
from arca.nucleo.errores import DatosInvalidos, NoEncontrado, TransicionInvalida

NO_CUENTAN = (EstadoRecurso.REEMPLAZADO.value, EstadoRecurso.RECHAZADO.value, EstadoRecurso.SIN_IDENTIFICAR.value)



def paginas(ctx, unidad: UnidadDocumental) -> list[dict[str, Any]]:
    """Las páginas del expediente en orden: los PDF por su parte y las imágenes por su número de página."""
    recursos = list(ctx.db.scalars(select(RecursoDigital).where(RecursoDigital.unidad_id == unidad.id, RecursoDigital.estado.not_in(NO_CUENTAN))))
    recursos.sort(key=lambda r: (r.modalidad != "pdf", r.parte or 0, r.pagina or 0, r.creado_en))
    salida, n = [], 0
    for r in recursos:
        for i in range(max(1, r.paginas or 1)):
            n += 1
            salida.append({"n": n, "recurso_id": r.id, "pagina_en_archivo": i + 1, "archivo": r.ruta_original.rsplit("/", 1)[-1], "estado": r.estado, "modalidad": r.modalidad})
    return salida


def imagen_pagina(ctx, unidad: UnidadDocumental, n: int, ancho: int = 1400, corregir: bool = True) -> bytes:
    """La página n como PNG. `ancho` es el máximo: nunca se amplía (para el OCR se pide el tamaño original)."""
    """La página n del expediente como PNG, para el visor. Se lee del original verificado contra su huella."""
    lista = paginas(ctx, unidad)
    if not 1 <= n <= len(lista):
        raise NoEncontrado("La página no existe en el expediente")
    p = lista[n - 1]
    r = ctx.db.get(RecursoDigital, p["recurso_id"])
    a = ctx.db.get(ArchivoDigital, r.archivo_id)
    contenido = almacen.leer(a.clave_almacen, ctx.tenant_id)
    if almacen.huella(contenido) != a.sha256:
        raise TransicionInvalida("ALERTA DE INTEGRIDAD: el archivo no coincide con su huella")
    from PIL import Image  # noqa: PLC0415

    if r.modalidad == "pdf":
        import pikepdf  # noqa: PLC0415
        from pikepdf import PdfImage  # noqa: PLC0415

        with pikepdf.open(io.BytesIO(contenido)) as pdf:
            pagina = pdf.pages[p["pagina_en_archivo"] - 1]
            imagenes = list(pagina.get_images().values())
            if not imagenes:
                raise DatosInvalidos("Esa página del PDF no es una imagen escaneada: ábrala en el original")
            img = PdfImage(imagenes[0]).as_pil_image()
    else:
        img = Image.open(io.BytesIO(contenido))
        img.seek(0)
    img = img.convert("L" if img.mode in ("1", "L", "I;16", "I") else "RGB")
    if corregir:
        from arca.modelos import TextoPagina  # noqa: PLC0415

        giro = ctx.db.scalar(select(TextoPagina.rotacion).where(TextoPagina.recurso_id == p["recurso_id"], TextoPagina.pagina == p["pagina_en_archivo"])) or 0
        if giro:
            img = img.rotate(-giro, expand=True)  # se muestra derecha; el original queda como llegó
    img.thumbnail((ancho, ancho * 2))
    salida = io.BytesIO()
    img.save(salida, "PNG", optimize=True)
    return salida.getvalue()
