"""
Instrumentos archivísticos en Excel que NO tienen formato oficial del Servicio Geológico.

Aquí queda solo la base de descripción ISAD(G), que es un instrumento del contrato y no un
formato del sistema de gestión de calidad del Servicio Geológico.

El inventario F-GDM-003, la hoja de control F-GDM-007 y los dos rótulos F-GDM-006 y
F-GDM-008 NO se arman aquí: se llenan sobre las plantillas oficiales, en formatos_sgc.py.
Estuvieron un tiempo armados en este módulo con una estructura propia y eso fue un error,
porque lo que se entrega al Servicio Geológico tiene que ser su formato, no uno parecido.
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, Side

_borde = Border(*[Side(style="thin", color="B0B8C0")] * 4)


def _iso(f: date | None) -> str:
    return f.isoformat() if f else ""


def _escribir(hoja, coordenada: str, valor) -> None:
    """
    Escribe respetando las celdas combinadas del formato oficial: en una combinación el valor
    va en la celda de arriba a la izquierda, las demás son de solo lectura.
    """
    from openpyxl.utils import range_boundaries
    for rango in hoja.merged_cells.ranges:
        if coordenada in rango:
            min_col, min_fila, _, _ = range_boundaries(str(rango))
            hoja.cell(row=min_fila, column=min_col, value=valor)
            return
    hoja[coordenada] = valor


def generar_base_isadg(filas: list[dict], columnas: list[tuple[str, str]]) -> bytes:
    """
    Base de descripción con las 44 columnas de la plantilla del contrato: el código del
    elemento de la norma en la primera fila y su nombre en la segunda.
    """
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "BASE_ISADG"

    encabezado = Font(bold=True, color="FFFFFF", size=9)
    from openpyxl.styles import PatternFill
    fondo = PatternFill("solid", fgColor="12293F")

    for j, (codigo, nombre) in enumerate(columnas, start=1):
        c1 = hoja.cell(row=1, column=j, value=codigo)
        c2 = hoja.cell(row=2, column=j, value=nombre)
        for c in (c1, c2):
            c.font = encabezado
            c.fill = fondo
            c.alignment = Alignment(wrap_text=True, vertical="center")
        hoja.column_dimensions[c2.column_letter].width = max(14, min(46, len(nombre) + 4))
    hoja.freeze_panes = "A3"

    for i, f in enumerate(filas):
        for j, (_, nombre) in enumerate(columnas, start=1):
            valor = f.get(nombre)
            if valor not in (None, ""):
                hoja.cell(row=3 + i, column=j, value=valor).alignment = Alignment(
                    vertical="top", wrap_text=True)

    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


