"""Llenado de plantillas de Excel con marcadores. Funciones puras sobre los bytes del libro.

Reciclado de la idea de GEOLOGY (llenar el formato oficial en vez de imitarlo), generalizado: la entidad
pone en su formato marcadores {{campo}} y ARCA los reemplaza.

- `{{campo}}`: un dato del encabezado (entidad, proyecto, caja…). Si la celda solo tiene el marcador, el
  valor conserva su tipo (número o fecha); si el marcador va dentro de un texto, se reemplaza en el texto.
- `{{fila.campo}}`: la fila modelo de una tabla (los expedientes del FUID, las carpetas de una caja). Esa
  fila se repite una vez por elemento con su formato, y lo que está debajo (totales, firmas) baja con todo
  y sus celdas combinadas.
- En los rótulos, la hoja de la plantilla es UN rótulo: se copia una hoja por caja o por carpeta.
"""

import io
import re
from copy import copy
from datetime import date, datetime
from typing import Any

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from arca.nucleo.errores import DatosInvalidos

MARCADOR = re.compile(r"\{\{\s*(fila\.)?([a-z_][a-z0-9_]*)\s*\}\}")
MAX_ROTULOS = 1000


def marcadores(contenido: bytes) -> tuple[set[str], set[str]]:
    """(campos de encabezado, campos de fila) que aparecen en la primera hoja del libro."""
    hoja = _abrir(contenido).worksheets[0]
    encabezado, fila = set(), set()
    for celdas in hoja.iter_rows():
        for c in celdas:
            if isinstance(c.value, str):
                for es_fila, campo in MARCADOR.findall(c.value):
                    (fila if es_fila else encabezado).add(campo)
    return encabezado, fila


def _abrir(contenido: bytes) -> openpyxl.Workbook:
    try:
        return openpyxl.load_workbook(io.BytesIO(contenido))
    except Exception as e:  # noqa: BLE001
        raise DatosInvalidos("La plantilla no es un libro de Excel (.xlsx) legible") from e


def _valor(texto: str, datos: dict[str, Any], prefijo: bool) -> Any:
    unico = MARCADOR.fullmatch(texto.strip())
    if unico and bool(unico.group(1)) == prefijo:
        return datos.get(unico.group(2))

    def cambiar(m: re.Match) -> str:
        if bool(m.group(1)) != prefijo:
            return m.group(0)
        v = datos.get(m.group(2))
        if isinstance(v, date | datetime):
            return v.strftime("%Y-%m-%d")
        return "" if v is None else str(v)

    return MARCADOR.sub(cambiar, texto)


def _llenar_encabezado(hoja: Worksheet, datos: dict[str, Any]) -> None:
    for celdas in hoja.iter_rows():
        for c in celdas:
            if isinstance(c.value, str) and "{{" in c.value and MARCADOR.search(c.value):
                c.value = _valor(c.value, datos, prefijo=False)


def _fila_modelo(hoja: Worksheet) -> int | None:
    for celdas in hoja.iter_rows():
        for c in celdas:
            if isinstance(c.value, str) and "{{" in c.value and any(f for f, _ in MARCADOR.findall(c.value)):
                return c.row
    return None


def _llenar_filas(hoja: Worksheet, filas: list[dict[str, Any]]) -> None:
    modelo = _fila_modelo(hoja)
    if modelo is None:
        return
    plantilla = {c.column: (c.value, copy(c._style)) for c in hoja[modelo]}  # noqa: SLF001
    altura = hoja.row_dimensions[modelo].height
    extra = max(0, len(filas) - 1)
    if extra:
        # Las celdas combinadas debajo de la fila modelo (firmas, totales) bajan junto con su contenido.
        debajo = [r for r in hoja.merged_cells.ranges if r.min_row > modelo]
        for r in debajo:
            hoja.merged_cells.remove(r)
        hoja.insert_rows(modelo + 1, extra)
        for r in debajo:
            r.shift(row_shift=extra)
            hoja.merged_cells.add(r)
    for i, datos in enumerate(filas or [{}]):
        fila = modelo + i
        if altura:
            hoja.row_dimensions[fila].height = altura
        for columna, (valor, estilo) in plantilla.items():
            celda = hoja.cell(row=fila, column=columna)
            celda._style = copy(estilo)  # noqa: SLF001
            celda.value = _valor(valor, datos, prefijo=True) if isinstance(valor, str) else valor


def llenar(contenido: bytes, encabezado: dict[str, Any], filas: list[dict[str, Any]]) -> bytes:
    """Un documento: el FUID completo, con el encabezado y una fila por expediente."""
    libro = _abrir(contenido)
    hoja = libro.worksheets[0]
    _llenar_filas(hoja, filas)
    _llenar_encabezado(hoja, encabezado)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _titulo(texto: str, usados: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", "-", str(texto))[:28] or "Rotulo"
    titulo, n = base, 2
    while titulo in usados:
        titulo, n = f"{base[:25]}~{n}", n + 1
    usados.add(titulo)
    return titulo


def llenar_varios(contenido: bytes, elementos: list[tuple[str, dict[str, Any], list[dict[str, Any]]]]) -> bytes:
    """Rótulos: una hoja por elemento (nombre de la hoja, encabezado, filas), copiada de la hoja plantilla."""
    if not elementos:
        raise DatosInvalidos("No hay nada que rotular con ese filtro")
    if len(elementos) > MAX_ROTULOS:
        raise DatosInvalidos(f"Son {len(elementos)} rótulos; expida como máximo {MAX_ROTULOS} por archivo (filtre por lote o por cajas)")
    libro = _abrir(contenido)
    modelo = libro.worksheets[0]
    usados: set[str] = set()
    for nombre, encabezado, filas in elementos:
        hoja = libro.copy_worksheet(modelo)
        hoja.title = _titulo(nombre, usados)
        hoja.page_setup.orientation = modelo.page_setup.orientation
        hoja.print_area = modelo.print_area if modelo.print_area else None
        _llenar_filas(hoja, filas)
        _llenar_encabezado(hoja, encabezado)
    libro.remove(modelo)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def plantilla_base(titulo: str, encabezado: list[tuple[str, str]], filas: list[tuple[str, str]], pie: list[str]) -> bytes:
    """Un formato de partida, sin datos de nadie, para que la entidad lo ajuste a su imagen y lo suba."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: PLC0415

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Plantilla"
    fino = Side(style="thin", color="94A3B8")
    borde = Border(left=fino, right=fino, top=fino, bottom=fino)
    ancho = max(len(filas), 4)
    hoja.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ancho)
    hoja.cell(1, 1, titulo).font = Font(bold=True, size=14, color="17324D")
    fila = 3
    for etiqueta, campo in encabezado:
        hoja.cell(fila, 1, etiqueta).font = Font(bold=True)
        hoja.merge_cells(start_row=fila, start_column=2, end_row=fila, end_column=ancho)
        hoja.cell(fila, 2, "{{" + campo + "}}")
        fila += 1
    if filas:
        fila += 1
        for i, (etiqueta, _) in enumerate(filas, start=1):
            c = hoja.cell(fila, i, etiqueta)
            c.font, c.fill, c.border = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="17324D"), borde
            c.alignment = Alignment(wrap_text=True, vertical="center")
            hoja.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 18
        fila += 1
        for i, (_, campo) in enumerate(filas, start=1):
            hoja.cell(fila, i, "{{fila." + campo + "}}").border = borde
        fila += 2
    for texto in pie:
        hoja.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=ancho)
        hoja.cell(fila, 1, texto)
        fila += 1
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()
