"""
Los formatos oficiales del Servicio Geológico Colombiano, llenados desde Python.

REGLA QUE NO SE NEGOCIA. La plataforma NO dibuja formatos. El Servicio Geológico entregó
sus plantillas —F-GDM-003 versión 9, F-GDM-006 versión 5, F-GDM-007 versión 4 y F-GDM-008
versión 5— y son las que hay que entregar: mismo encabezado, mismo logotipo, mismos campos
numerados y en el mismo orden. Aquí no se reconstruye ninguna: se abre la plantilla oficial,
se escribe en sus celdas y se guarda. Todo lo que no sea un dato del expediente queda
exactamente como venía.

Esto corrige un error propio: se había armado una hoja de control con columnas parecidas
pero estructura distinta, y esa hoja no sirve para entregarle al Servicio Geológico.

Dónde va cada dato en cada plantilla está escrito abajo, celda por celda, a partir de la
lectura de los propios archivos. Si el Servicio Geológico publica una versión nueva del
formato, se reemplaza el archivo en datos/formatos_sgc y se ajusta el mapa; no se toca nada
más.
"""
from __future__ import annotations

import io
import zipfile
from datetime import date, datetime
from pathlib import Path

import openpyxl
from openpyxl.utils import range_boundaries

CARPETA = Path(__file__).resolve().parent.parent.parent / "datos" / "formatos_sgc"

FUID = CARPETA / "F-GDM-003_FUID_v9.xlsx"
ROTULO_CARPETA = CARPETA / "F-GDM-006_rotulo_carpeta_v5.xlsx"
HOJA_DE_CONTROL = CARPETA / "F-GDM-007_hoja_de_control_v4.xlsx"
ROTULO_CAJA = CARPETA / "F-GDM-008_rotulo_cajas_v5.xlsx"

# La caja X-100 del contrato mide 26 de alto por 11 de ancho por 40 de largo, en
# centímetros exteriores. El rótulo va en la cara frontal, que es la de 11 por 26, así que
# se imprime a 10,4 por 25 centímetros para que quepa con margen y no se doble en el borde.
X100_ANCHO_CM = 10.4
X100_ALTO_CM = 25.0

# El rótulo de carpeta va pegado en la tapa de la carpeta de archivo, que es tamaño oficio,
# de unos 35 por 25 centímetros. El Archivo General de la Nación normaliza la carpeta —el
# material, el pH y la medida— pero NO fija un tamaño de rótulo, así que se usa el de la
# práctica corriente, 17 por 13 centímetros, que es el que pidió la dirección del proyecto y
# el que deja margen suficiente en la tapa.
CARPETA_ANCHO_CM = 17.0
CARPETA_ALTO_CM = 13.0


class FaltaLaPlantilla(FileNotFoundError):
    """La plantilla oficial no está en datos/formatos_sgc."""


def _abrir(ruta: Path):
    if not ruta.exists():
        raise FaltaLaPlantilla(
            f"Falta la plantilla oficial {ruta.name} en datos/formatos_sgc. Sin ella no se "
            "puede entregar en el formato del Servicio Geológico, y la plataforma no dibuja "
            "formatos por su cuenta.")
    return openpyxl.load_workbook(ruta)


def _escribir(hoja, coordenada: str, valor) -> None:
    """
    Escribe respetando las celdas combinadas del formato oficial.

    En una combinación el valor va en la celda de arriba a la izquierda; las demás son de
    solo lectura y escribir en ellas revienta el archivo.
    """
    if valor is None:
        return
    for rango in hoja.merged_cells.ranges:
        if coordenada in rango:
            min_col, min_fila, _, _ = range_boundaries(str(rango))
            hoja.cell(row=min_fila, column=min_col, value=valor)
            return
    hoja[coordenada] = valor


def _ajustar_al_texto(hoja, fila: int, columnas) -> None:
    """
    Deja que la fila crezca con el texto que se le escriba.

    Excel solo ajusta el alto de una fila cuando el texto va con ajuste de línea y la fila
    NO tiene un alto fijo escrito en el archivo. Las plantillas traen alturas fijas pensadas
    para el renglón de ejemplo, y con un tipo documental largo el texto quedaba cortado. Se
    activa el ajuste de línea en las casillas y se le quita el alto fijo a la fila.

    El resto del estilo —bordes, fuente, alineación vertical— se conserva tal cual.
    """
    from copy import copy
    for letra in columnas:
        celda = hoja[f"{letra}{fila}"]
        alineacion = copy(celda.alignment)
        alineacion.wrap_text = True
        if not alineacion.vertical:
            alineacion.vertical = "center"
        celda.alignment = alineacion
    # Poner la altura en None deja de escribir customHeight en el archivo, que es lo que
    # hace que Excel vuelva a calcular el alto según el texto.
    hoja.row_dimensions[fila].height = None


def _guardar(libro) -> bytes:
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _texto_fecha(valor, formato: str = "%d/%m/%Y") -> str:
    if isinstance(valor, (date, datetime)):
        return valor.strftime(formato)
    return str(valor or "")


def _cm_a_ancho(cm: float) -> float:
    """Centímetros a unidades de ancho de columna de Excel."""
    pixeles = cm / 2.54 * 96
    return max(1.0, (pixeles - 5) / 7)


def _cm_a_alto(cm: float) -> float:
    """Centímetros a puntos, que es como Excel mide el alto de fila."""
    return cm / 2.54 * 72


def _ancho_en_px(hoja, columnas: str) -> float:
    predeterminado = hoja.sheet_format.defaultColWidth or 8.43
    total = 0.0
    for letra in columnas:
        dim = hoja.column_dimensions.get(letra)
        ancho = dim.width if dim and dim.width else predeterminado
        total += 7 * ancho + 5
    return total


def _alto_en_pt(hoja, filas: range) -> float:
    predeterminado = hoja.sheet_format.defaultRowHeight or 15.0
    total = 0.0
    for fila in filas:
        dim = hoja.row_dimensions.get(fila)
        total += dim.height if dim and dim.height else predeterminado
    return total


def _escalar(hoja, columnas: str, filas: range, ancho_cm: float, alto_cm: float) -> None:
    """
    Lleva el bloque del formato al tamaño físico que se necesita, sin deformarlo.

    No se reescriben las medidas a mano: se mide lo que hoy ocupa el formato y se multiplica
    todo por un mismo factor, de modo que la proporción entre las casillas —y por tanto el
    diseño que aprobó el Servicio Geológico— queda igual, solo que más pequeño. El logotipo
    se escala con el mismo factor para que no quede desproporcionado.
    """
    predeterminado_ancho = hoja.sheet_format.defaultColWidth or 8.43
    predeterminado_alto = hoja.sheet_format.defaultRowHeight or 15.0

    factor_ancho = (ancho_cm / 2.54 * 96) / max(1.0, _ancho_en_px(hoja, columnas))
    factor_alto = (alto_cm / 2.54 * 72) / max(1.0, _alto_en_pt(hoja, filas))

    for letra in columnas:
        dim = hoja.column_dimensions[letra]
        actual = dim.width if dim.width else predeterminado_ancho
        dim.width = max(1.0, ((7 * actual + 5) * factor_ancho - 5) / 7)
    for fila in filas:
        dim = hoja.row_dimensions[fila]
        actual = dim.height if dim.height else predeterminado_alto
        dim.height = max(4.0, actual * factor_alto)
    for imagen in getattr(hoja, "_images", []):
        imagen.width = int(imagen.width * factor_ancho)
        imagen.height = int(imagen.height * factor_alto)
    # La letra se achica con el rótulo. Si el bloque se reduce y la letra se queda del mismo
    # tamaño, el texto no cabe en la casilla y sale cortado o pisando el borde. Manda el
    # factor más pequeño de los dos, que es el que decide si un renglón de texto cabe.
    _escalar_letra(hoja, columnas, filas, min(factor_ancho, factor_alto))


def _escalar_letra(hoja, columnas, filas, factor: float) -> None:
    """Reduce el tamaño de la letra en el mismo factor en que se redujo el rótulo."""
    from copy import copy
    if factor >= 0.99:
        return
    for letra in columnas:
        for fila in filas:
            celda = hoja[f"{letra}{fila}"]
            fuente = copy(celda.font)
            tamano = fuente.size or 11
            fuente.size = max(4.0, round(tamano * factor, 1))
            celda.font = fuente


def _preparar_impresion(hoja, area: str, orientacion: str) -> None:
    """
    Deja la hoja lista para imprimir el rótulo a tamaño real.

    Sin escalado y con márgenes cortos: el rótulo tiene que salir de la impresora con las
    medidas que se calcularon, porque si Excel lo ajusta a la página deja de coincidir con
    la cara de la caja o con la tapa de la carpeta.

    El ajuste de página se escribe con cuidado: openpyxl solo admite fitToPage cuando la
    hoja trae sus propiedades de página, y las plantillas del Servicio Geológico no siempre
    las traen.
    """
    hoja.print_area = area
    hoja.page_setup.orientation = orientacion
    hoja.page_setup.scale = 100
    try:
        if hoja.sheet_properties.pageSetUpPr is not None:
            hoja.page_setup.fitToPage = False
    except AttributeError:
        pass
    hoja.page_margins.left = hoja.page_margins.right = 0.3
    hoja.page_margins.top = hoja.page_margins.bottom = 0.3


# ---------------------------------------------------------------------------
# F-GDM-007 versión 4 · Hoja de control
# ---------------------------------------------------------------------------
# Campos 1 a 7 en el encabezado, los trámites en las filas 11 a 29 y los campos 15 y 16 al
# pie. Las columnas de trámite son B número, C radicado, D fecha, E tipo documental
# (combinada con F), G folio desde, H folio hasta, I sistema, J expediente SGDEA, K enlace
# y L observaciones.
HC_HOJA = "Hoja Control"
HC_ENCABEZADO = {"codigo_dependencia": "D6", "dependencia": "F6",
                 "codigo_serie": "I6", "serie": "K6",
                 "codigo_subserie": "I7", "subserie": "K7",
                 "nombre_expediente": "D8"}
HC_PRIMERA_FILA = 11
HC_ULTIMA_FILA = 29
HC_COLUMNAS = {"no_item": "B", "no_radicado": "C", "fecha": "D", "tipo_documental": "E",
               "folio_desde": "G", "folio_hasta": "H", "sistema_informacion": "I",
               "expediente_sgdea": "J", "enlace_acceso": "K", "observaciones": "L"}
HC_RESPONSABLE = "F30"
HC_FECHA = "D33"


def hoja_de_control(expediente: dict) -> bytes:
    """
    Una hoja de control F-GDM-007 versión 4 llena, en el formato oficial.

    Recibe el expediente con sus trámites y devuelve el archivo. No cambia una sola línea
    del formato: escribe en sus casillas y ya.
    """
    libro = _abrir(HOJA_DE_CONTROL)
    hoja = libro[HC_HOJA] if HC_HOJA in libro.sheetnames else libro.worksheets[0]

    for clave, celda in HC_ENCABEZADO.items():
        _escribir(hoja, celda, expediente.get(clave) or "")

    tramites = list(expediente.get("tramites") or [])
    _limpiar_tramites(hoja)
    # Cuántas filas se insertaron para que quepan los trámites. El pie del formato —los
    # campos 15 y 16— baja esa misma cantidad, y si no se tiene en cuenta, el nombre del
    # responsable termina escrito encima de un trámite. Pasó, y por eso queda anotado.
    desplazamiento = _estirar_si_no_caben(hoja, len(tramites))

    for i, t in enumerate(tramites):
        fila = HC_PRIMERA_FILA + i
        _escribir(hoja, f"{HC_COLUMNAS['no_item']}{fila}", t.get("no_item") or i + 1)
        _escribir(hoja, f"{HC_COLUMNAS['no_radicado']}{fila}", t.get("no_radicado") or "N/A")
        _escribir(hoja, f"{HC_COLUMNAS['fecha']}{fila}", _texto_fecha(t.get("fecha")))
        _escribir(hoja, f"{HC_COLUMNAS['tipo_documental']}{fila}", t.get("tipo_documental") or "")
        _escribir(hoja, f"{HC_COLUMNAS['folio_desde']}{fila}", t.get("folio_desde"))
        _escribir(hoja, f"{HC_COLUMNAS['folio_hasta']}{fila}", t.get("folio_hasta"))
        _escribir(hoja, f"{HC_COLUMNAS['sistema_informacion']}{fila}", t.get("sistema_informacion") or "N/A")
        _escribir(hoja, f"{HC_COLUMNAS['expediente_sgdea']}{fila}", t.get("expediente_sgdea") or "N/A")
        _escribir(hoja, f"{HC_COLUMNAS['enlace_acceso']}{fila}", t.get("enlace_acceso") or "N/A")
        _escribir(hoja, f"{HC_COLUMNAS['observaciones']}{fila}", t.get("observaciones") or "")
        # El renglón crece con el texto: un tipo documental de veinticinco palabras no cabe
        # en la altura que trae la plantilla para su renglón de ejemplo.
        _ajustar_al_texto(hoja, fila, "BCDEFGHIJKL")

    # Campo 15. El responsable de la hoja de control es QUIEN LA REVISA, no quien la
    # diligencia: es la firma que da fe de que lo escrito corresponde al expediente, y el
    # propio formato dice que la hoja se firma al cierre del expediente. Mientras nadie la
    # haya revisado, el campo va en blanco, que es lo correcto: una hoja sin revisar no
    # tiene responsable. Quien la diligenció queda igualmente registrado en la bitácora.
    _escribir(hoja, _bajar(HC_RESPONSABLE, desplazamiento),
              expediente.get("reviso_hoja") or "")
    _escribir(hoja, _bajar(HC_FECHA, desplazamiento),
              _texto_fecha(expediente.get("fecha_revision")
                           or expediente.get("fecha_diligenciamiento")))
    return _guardar(libro)


def _desplazar_combinadas(hoja, desde_fila: int, cuantas: int) -> None:
    """Baja las celdas combinadas que están de esta fila en adelante, tantas filas."""
    from openpyxl.worksheet.cell_range import CellRange
    # Se trabaja sobre la lista de rangos y no con unmerge_cells, porque ese método intenta
    # borrar celdas que en una plantilla recién insertada todavía no existen y revienta.
    for rango in [r for r in list(hoja.merged_cells.ranges) if r.min_row >= desde_fila]:
        hoja.merged_cells.ranges.remove(rango)
        hoja.merged_cells.ranges.add(CellRange(
            min_col=rango.min_col, min_row=rango.min_row + cuantas,
            max_col=rango.max_col, max_row=rango.max_row + cuantas))


def _bajar(celda: str, filas: int) -> str:
    """La misma celda, tantas filas más abajo. «F30» con 6 es «F36»."""
    letras = "".join(c for c in celda if c.isalpha())
    numero = int("".join(c for c in celda if c.isdigit()))
    return f"{letras}{numero + filas}"


def _limpiar_tramites(hoja) -> None:
    """Quita el renglón de ejemplo que trae la plantilla, sin tocar su formato."""
    for fila in range(HC_PRIMERA_FILA, HC_ULTIMA_FILA + 1):
        for columna in HC_COLUMNAS.values():
            _escribir(hoja, f"{columna}{fila}", "")


def _estirar_si_no_caben(hoja, cuantos: int) -> int:
    """
    La plantilla trae diecinueve renglones de trámite. Un expediente puede traer más.

    En ese caso se insertan renglones ANTES del pie, copiando el formato del primer renglón
    de trámite para que la tabla siga viéndose igual. Nunca se recorta la hoja de control:
    dejar trámites por fuera sería falsear el instrumento.

    Devuelve cuántas filas se insertaron, para poder bajar el pie del formato lo mismo.
    """
    disponibles = HC_ULTIMA_FILA - HC_PRIMERA_FILA + 1
    if cuantos <= disponibles:
        return 0
    from copy import copy
    faltan = cuantos - disponibles
    hoja.insert_rows(HC_ULTIMA_FILA + 1, faltan)
    # HALLAZGO. insert_rows mueve el contenido de las filas, pero NO mueve las celdas
    # combinadas: la nota del pie, que va combinada de B a L, se quedaba donde estaba y se
    # tragaba el último trámite, que desaparecía de la hoja sin decir nada. Hay que
    # desplazarlas a mano.
    _desplazar_combinadas(hoja, HC_ULTIMA_FILA + 1, faltan)
    for nueva in range(HC_ULTIMA_FILA + 1, HC_ULTIMA_FILA + 1 + faltan):
        hoja.row_dimensions[nueva].height = hoja.row_dimensions[HC_PRIMERA_FILA].height
        for columna in HC_COLUMNAS.values():
            modelo = hoja[f"{columna}{HC_PRIMERA_FILA}"]
            celda = hoja[f"{columna}{nueva}"]
            celda._style = copy(modelo._style)
        hoja.merge_cells(f"E{nueva}:F{nueva}")
    return faltan


# ---------------------------------------------------------------------------
# F-GDM-006 versión 5 · Rótulo de carpeta
# ---------------------------------------------------------------------------
RC_HOJA = "Rotulo Carpeta"
RC_CELDAS = {"codigo_dependencia_productora": "C6", "dependencia_productora": "D7",
             "codigo_serie": "C8", "serie": "D9",
             "codigo_subserie": "C10", "subserie": "D11",
             "nombre_expediente": "C13",
             "no_carpeta": "C15", "tomo": "E15", "no_folios": "G15", "no_caja": "I15",
             "fecha_inicial": "E16", "fecha_final": "H16"}


def rotulo_de_carpeta(rotulo: dict, a_tamano_real: bool = True) -> bytes:
    """
    Un rótulo de carpeta F-GDM-006 versión 5 lleno, del tamaño de un rótulo de carpeta.

    El diseño es el oficial y no se le cambia ni un campo: lo único que se ajusta es el
    tamaño de impresión, 17 por 13 centímetros, que es el que se pega en la tapa de una
    carpeta tamaño oficio dejando margen. El Archivo General de la Nación normaliza la
    carpeta pero no el rótulo, así que esta medida es de práctica y queda en una constante
    por si el Servicio Geológico pide otra.

    Las fechas extremas van escritas en la forma del propio formato, DD__ MM__ AAAA__, con
    los números puestos en su sitio.
    """
    libro = _abrir(ROTULO_CARPETA)
    hoja = libro[RC_HOJA] if RC_HOJA in libro.sheetnames else libro.worksheets[0]
    datos = dict(rotulo)
    datos.setdefault("fecha_inicial", _dia_mes_ano(rotulo.get("fecha_inicial_fecha")))
    datos.setdefault("fecha_final", _dia_mes_ano(rotulo.get("fecha_final_fecha")))
    for clave, celda in RC_CELDAS.items():
        if clave in datos:
            _escribir(hoja, celda, datos.get(clave) if datos.get(clave) is not None else "")
    if a_tamano_real:
        _escalar(hoja, "BCDEFGHI", range(3, 17), CARPETA_ANCHO_CM, CARPETA_ALTO_CM)
    _preparar_impresion(hoja, "B3:I16", "landscape")
    return _guardar(libro)


def _dia_mes_ano(valor) -> str:
    """Escribe la fecha como la pide el formato: DD__ MM__ AAAA__."""
    if not isinstance(valor, (date, datetime)):
        return "DD____ MM____ AAAA______"
    return f"DD {valor.day:02d}  MM {valor.month:02d}  AAAA {valor.year}"


# ---------------------------------------------------------------------------
# F-GDM-008 versión 5 · Rótulo de caja, ajustado a la caja X-100
# ---------------------------------------------------------------------------
RCJ_HOJA = "Rotulo Caja"
RCJ_CELDAS = {"codigo_dependencia": "C5", "dependencia": "C6", "serie": "C7",
              "subserie": "C8", "no_caja": "C9"}
RCJ_PRIMERA_LINEA = 11
RCJ_ULTIMA_LINEA = 19
RCJ_FECHA_INICIAL = "E20"
RCJ_FECHA_FINAL = "E21"


def rotulo_de_caja(rotulo: dict, para_x100: bool = True) -> bytes:
    """
    Un rótulo de caja F-GDM-008 versión 5 lleno, del tamaño de la caja X-100.

    El formato es el oficial y no se le cambia ni un campo. Lo único que se ajusta es el
    tamaño de impresión: la X-100 del contrato mide 11 centímetros de ancho por 26 de alto
    en su cara frontal, la mitad de una X-200, y el rótulo tal como viene se sale de esa
    cara. Se reparten los anchos de columna y los altos de fila para que la etiqueta salga
    de 10,4 por 25 centímetros y se pegue sin doblar el borde.

    El contenido son las carpetas que quedaron en la caja, una por renglón, en los nueve
    renglones que el formato reserva. Si hay más carpetas que renglones, se agrupan por
    rango para no dejar ninguna sin nombrar.
    """
    libro = _abrir(ROTULO_CAJA)
    hoja = libro[RCJ_HOJA] if RCJ_HOJA in libro.sheetnames else libro.worksheets[0]

    for clave, celda in RCJ_CELDAS.items():
        _escribir(hoja, celda, rotulo.get(clave) or "")

    for i, linea in enumerate(_lineas_de_contenido(rotulo)):
        fila = RCJ_PRIMERA_LINEA + i
        if fila > RCJ_ULTIMA_LINEA:
            break
        _escribir(hoja, f"B{fila}", linea)

    _escribir(hoja, RCJ_FECHA_INICIAL, _dia_mes_ano(rotulo.get("fecha_inicial_fecha")))
    _escribir(hoja, RCJ_FECHA_FINAL, _dia_mes_ano(rotulo.get("fecha_final_fecha")))

    if para_x100:
        _ajustar_a_x100(hoja)
    return _guardar(libro)


def _lineas_de_contenido(rotulo: dict) -> list[str]:
    """
    El contenido de la caja, un renglón por carpeta.

    Cuando hay más carpetas que renglones disponibles, los últimos se juntan en un rango,
    de modo que el rótulo siga diciendo qué hay dentro sin salirse del formato.
    """
    carpetas = list(rotulo.get("carpetas") or [])
    if not carpetas:
        texto = str(rotulo.get("contenido") or "")
        return [t.strip() for t in texto.split(";") if t.strip()][:RCJ_ULTIMA_LINEA - RCJ_PRIMERA_LINEA + 1]

    cupo = RCJ_ULTIMA_LINEA - RCJ_PRIMERA_LINEA + 1
    if len(carpetas) <= cupo:
        return carpetas
    ultimas = len(carpetas) - (cupo - 1)
    return carpetas[:cupo - 1] + [f"y {ultimas} carpetas más, según el inventario de la caja"]


def _ajustar_a_x100(hoja) -> None:
    """Lleva el rótulo al tamaño de la cara frontal de la caja X-100, sin deformarlo."""
    _escalar(hoja, "BCDEFGH", range(2, 22), X100_ANCHO_CM, X100_ALTO_CM)
    _preparar_impresion(hoja, "B2:H21", "portrait")


# ---------------------------------------------------------------------------
# F-GDM-003 versión 9 · Formato único de inventario documental
# ---------------------------------------------------------------------------
FUID_HOJA = "FUID"
FUID_PRIMERA_FILA = 15
FUID_ENCABEZADO = {"entidad_remitente": "D5", "entidad_productora": "D6",
                   "unidad_administrativa": "D7", "oficina_productora": "D8",
                   "objeto": "D9"}
FUID_COL = {"orden": 1, "codigo": 2, "serie_subserie": 3, "unidad_documental": 4,
            "fecha_inicial": 5, "fecha_final": 6, "soporte_fisico": 7, "soporte_electronico": 8,
            "caja": 9, "carpeta": 10, "correlativo": 11, "folios": 12, "tipo_otro": 13,
            "cantidad_otro": 14, "ubicacion": 15, "cant_electronicos": 16,
            "tamano_electronicos": 17, "ddhh": 18, "publico": 19, "publico_clasificado": 20,
            "reservado": 21, "notas": 22}


def fuid(filas: list[dict], encabezado: dict) -> bytes:
    """
    El inventario de salida en el formato oficial F-GDM-003 versión 9.

    Se abre la plantilla del Servicio Geológico, se le quitan los renglones de ejemplo y se
    escriben los expedientes desde la fila 15, que es donde el formato empieza los datos.
    """
    libro = _abrir(FUID)
    hoja = libro[FUID_HOJA] if FUID_HOJA in libro.sheetnames else libro.worksheets[0]
    for nombre in list(libro.sheetnames):
        if nombre not in (hoja.title, "Instructivo"):
            del libro[nombre]

    for clave, celda in FUID_ENCABEZADO.items():
        _escribir(hoja, celda, encabezado.get(clave) or "")

    ultima = max(hoja.max_row, FUID_PRIMERA_FILA)
    for fila in range(FUID_PRIMERA_FILA, ultima + 1):
        for columna in range(1, max(FUID_COL.values()) + 1):
            celda = hoja.cell(row=fila, column=columna)
            if celda.value is not None:
                celda.value = None

    _estirar_fuid(hoja, len(filas), ultima)
    for i, datos in enumerate(filas):
        fila = FUID_PRIMERA_FILA + i
        for clave, columna in FUID_COL.items():
            if clave in datos and datos[clave] not in (None, ""):
                hoja.cell(row=fila, column=columna, value=datos[clave])
        _ajustar_al_texto(hoja, fila, [chr(64 + n) for n in range(1, max(FUID_COL.values()) + 1)])
    return _guardar(libro)


def _estirar_fuid(hoja, cuantas: int, ultima_con_formato: int) -> None:
    """
    Añade renglones al inventario cuando hacen falta, con el mismo formato de los de arriba.

    La plantilla del Servicio Geológico trae muchos renglones ya formateados, así que casi
    nunca hace falta; pero si un inventario los supera, se copian los bordes y la fuente del
    primer renglón de datos para que los nuevos no salgan sin cuadrícula.
    """
    from copy import copy
    disponibles = max(0, ultima_con_formato - FUID_PRIMERA_FILA + 1)
    if cuantas <= disponibles:
        return
    ultimo = max(FUID_COL.values())
    for fila in range(FUID_PRIMERA_FILA + disponibles, FUID_PRIMERA_FILA + cuantas):
        for columna in range(1, ultimo + 1):
            modelo = hoja.cell(row=FUID_PRIMERA_FILA, column=columna)
            hoja.cell(row=fila, column=columna)._style = copy(modelo._style)


# ---------------------------------------------------------------------------
# Varios archivos en uno solo
# ---------------------------------------------------------------------------
def paquete(archivos: dict[str, bytes]) -> bytes:
    """
    Junta varios formatos oficiales en un comprimido.

    Se entrega así, y no como un libro con muchas pestañas, porque cada hoja de control y
    cada rótulo es un formato completo con su encabezado y su logotipo, y copiarlos como
    pestañas dentro de un mismo libro los deja sin el logotipo del Servicio Geológico.
    """
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, contenido in archivos.items():
            z.writestr(nombre, contenido)
    return salida.getvalue()

# ---------------------------------------------------------------------------
# Varios rótulos de carpeta en una misma hoja oficio
# ---------------------------------------------------------------------------
# Una caja lleva varias carpetas y sacar un archivo por rótulo es impráctico: hay que
# imprimir de a uno y se desperdicia papel. Cuando la caja trae más de una carpeta, los
# rótulos salen repartidos en la hoja, cuatro por página, todos de la misma caja.
#
# El tamaño manda sobre el número: un rótulo de 17 por 13 centímetros NO cabe cuatro veces
# en una hoja oficio, que mide 21,6 por 33. Para que quepan cuatro hay que bajarlos a unos
# 15,4 por 9,7 e imprimir la hoja acostada. Por eso el reparto queda a elección: uno o dos
# por página conservan el tamaño completo; cuatro por página lo reducen.
BLOQUE_FILAS = range(3, 17)          # el rótulo ocupa de la fila 3 a la 16
BLOQUE_COLUMNAS = range(2, 10)       # y de la columna B a la I
SEPARACION_FILAS = 1
SEPARACION_COLUMNAS = 1

DISPOSICIONES = {
    1: {"columnas": 1, "filas": 1, "orientacion": "portrait", "ancho": 17.0, "alto": 13.0},
    2: {"columnas": 1, "filas": 2, "orientacion": "portrait", "ancho": 17.0, "alto": 13.0},
    4: {"columnas": 2, "filas": 2, "orientacion": "landscape", "ancho": 15.4, "alto": 9.7},
}
OFICIO = 14                          # tamaño de papel «Folio 8½ × 13» de Excel


def pliego_de_rotulos_de_carpeta(rotulos: list[dict], por_pagina: int = 4) -> bytes:
    """
    Los rótulos de las carpetas de una caja, repartidos en hojas oficio para imprimir.

    Con un solo rótulo se devuelve el rótulo solo, a tamaño completo. Con varios se reparten
    según `por_pagina`, respetando el diseño del formato oficial: se replica el bloque
    entero con sus bordes, sus casillas combinadas y el logotipo del Servicio Geológico, y
    se le cambia únicamente el tamaño.
    """
    if not rotulos:
        raise ValueError("No hay rótulos que imprimir.")
    if len(rotulos) == 1:
        return rotulo_de_carpeta(rotulos[0])
    if por_pagina not in DISPOSICIONES:
        por_pagina = 4
    d = DISPOSICIONES[por_pagina]

    libro = _abrir(ROTULO_CARPETA)
    hoja = libro[RC_HOJA] if RC_HOJA in libro.sheetnames else libro.worksheets[0]
    for nombre in list(libro.sheetnames):
        if nombre != hoja.title:
            del libro[nombre]

    plantilla = _fotografiar_bloque(hoja)
    logo = _logo_del_bloque(hoja, ROTULO_CARPETA)
    hoja._images = []                                  # se vuelven a poner, uno por rótulo
    # Se sueltan las combinaciones del bloque original antes de empezar: el primer rótulo se
    # pega encima de él, y en una celda combinada no se puede escribir. Hay que usar
    # unmerge_cells y no quitar el rango de la lista, porque solo ese método devuelve las
    # celdas a su estado normal; quitando el rango se quedan como celdas de solo lectura.
    for rango in list(hoja.merged_cells.ranges):
        try:
            hoja.unmerge_cells(str(rango))
        except KeyError:
            hoja.merged_cells.ranges.remove(rango)

    alto_bloque = len(BLOQUE_FILAS) + SEPARACION_FILAS
    ancho_bloque = len(BLOQUE_COLUMNAS) + SEPARACION_COLUMNAS
    # Cuánto se achica el rótulo respecto de lo que mide el formato tal como viene. La letra
    # se achica lo mismo, para que el texto siga cabiendo en su casilla.
    factor_letra = min(d["ancho"] / BLOQUE_ANCHO_NATURAL_CM,
                       d["alto"] / BLOQUE_ALTO_NATURAL_CM, 1.0)

    for i, rotulo in enumerate(rotulos):
        columna = i % d["columnas"]
        fila_en_pagina = (i // d["columnas"]) % d["filas"]
        pagina = i // (d["columnas"] * d["filas"])
        fila0 = BLOQUE_FILAS.start + (pagina * d["filas"] + fila_en_pagina) * alto_bloque
        col0 = BLOQUE_COLUMNAS.start + columna * ancho_bloque
        _pegar_bloque(hoja, plantilla, fila0, col0, factor_letra)
        _llenar_bloque(hoja, rotulo, fila0, col0)
        if logo is not None:
            _pegar_logo(hoja, logo, fila0, col0, d)

    _dimensionar_pliego(hoja, len(rotulos), d, alto_bloque, ancho_bloque)
    _cortes_de_pagina(hoja, len(rotulos), d, alto_bloque)
    return _guardar(libro)


def _fotografiar_bloque(hoja) -> dict:
    """Guarda el bloque del formato —valores, estilos, medidas y combinaciones— para copiarlo."""
    from copy import copy
    celdas = {}
    for fila in BLOQUE_FILAS:
        for columna in BLOQUE_COLUMNAS:
            celda = hoja.cell(row=fila, column=columna)
            celdas[(fila - BLOQUE_FILAS.start, columna - BLOQUE_COLUMNAS.start)] = (
                celda.value, copy(celda._style))
    combinadas = [(r.min_row - BLOQUE_FILAS.start, r.min_col - BLOQUE_COLUMNAS.start,
                   r.max_row - BLOQUE_FILAS.start, r.max_col - BLOQUE_COLUMNAS.start)
                  for r in hoja.merged_cells.ranges
                  if r.min_row >= BLOQUE_FILAS.start and r.max_row < BLOQUE_FILAS.stop
                  and r.min_col >= BLOQUE_COLUMNAS.start and r.max_col < BLOQUE_COLUMNAS.stop]
    altos = [hoja.row_dimensions[f].height or (hoja.sheet_format.defaultRowHeight or 15.0)
             for f in BLOQUE_FILAS]
    anchos = [(hoja.column_dimensions[chr(64 + c)].width
               or (hoja.sheet_format.defaultColWidth or 8.43)) for c in BLOQUE_COLUMNAS]
    return {"celdas": celdas, "combinadas": combinadas, "altos": altos, "anchos": anchos}


def _logo_del_bloque(hoja, plantilla: Path):
    """
    El logotipo del Servicio Geológico, para volver a ponerlo en cada rótulo del pliego.

    Se copian los BYTES de la imagen, no el objeto que trae el libro abierto: ese objeto
    apunta a un archivo que openpyxl cierra al terminar de leer, y al guardar el pliego
    revienta con «operación sobre un archivo cerrado». Tampoco sirve el nombre interno que
    reporta openpyxl, porque es el nombre con el que la va a escribir, no con el que la
    leyó.
    """
    for imagen in getattr(hoja, "_images", []):
        anclaje = getattr(imagen, "anchor", None)
        if getattr(anclaje, "_from", None) is None or anclaje._from.row >= 8:
            continue          # las de más abajo son adornos de la plantilla, no el logotipo
        referencia = getattr(imagen, "ref", None)
        datos = None
        if hasattr(referencia, "getvalue"):
            try:
                datos = referencia.getvalue()
            except ValueError:
                datos = None
        if not datos:
            continue
        return {"datos": datos, "anclaje": imagen.anchor,
                "ancho": imagen.width, "alto": imagen.height}
    return None


def _pegar_bloque(hoja, plantilla: dict, fila0: int, col0: int,
                  factor_letra: float = 1.0) -> None:
    from copy import copy
    for (df, dc), (valor, estilo) in plantilla["celdas"].items():
        celda = hoja.cell(row=fila0 + df, column=col0 + dc)
        celda.value = valor
        celda._style = copy(estilo)
        if factor_letra < 0.99:
            fuente = copy(celda.font)
            fuente.size = max(4.0, round((fuente.size or 11) * factor_letra, 1))
            celda.font = fuente
    for f1, c1, f2, c2 in plantilla["combinadas"]:
        hoja.merge_cells(start_row=fila0 + f1, start_column=col0 + c1,
                         end_row=fila0 + f2, end_column=col0 + c2)


def _llenar_bloque(hoja, rotulo: dict, fila0: int, col0: int) -> None:
    datos = dict(rotulo)
    datos.setdefault("fecha_inicial", _dia_mes_ano(rotulo.get("fecha_inicial_fecha")))
    datos.setdefault("fecha_final", _dia_mes_ano(rotulo.get("fecha_final_fecha")))
    for clave, celda in RC_CELDAS.items():
        if clave not in datos:
            continue
        letras = "".join(x for x in celda if x.isalpha())
        numero = int("".join(x for x in celda if x.isdigit()))
        destino = hoja.cell(row=fila0 + (numero - BLOQUE_FILAS.start),
                            column=col0 + (ord(letras) - 65 - (BLOQUE_COLUMNAS.start - 1)))
        _escribir(hoja, destino.coordinate,
                  datos.get(clave) if datos.get(clave) is not None else "")


def _pegar_logo(hoja, logo: dict, fila0: int, col0: int, disposicion: dict) -> None:
    """Pone una copia del logotipo en el rótulo que empieza en esa fila y esa columna."""
    from copy import deepcopy

    from openpyxl.drawing.image import Image
    try:
        nuevo = Image(io.BytesIO(logo["datos"]))
    except Exception:                       # sin biblioteca de imagen, el pliego sale igual
        return
    factor = disposicion["ancho"] / CARPETA_ANCHO_CM
    nuevo.width = max(20, int(logo["ancho"] * factor))
    nuevo.height = max(10, int(logo["alto"] * factor))

    anclaje = deepcopy(logo["anclaje"])
    anclaje._from.row += fila0 - BLOQUE_FILAS.start
    anclaje._from.col += col0 - BLOQUE_COLUMNAS.start
    if getattr(anclaje, "to", None) is not None:
        anclaje.to.row += fila0 - BLOQUE_FILAS.start
        anclaje.to.col += col0 - BLOQUE_COLUMNAS.start
    nuevo.anchor = anclaje
    hoja.add_image(nuevo)


def _dimensionar_pliego(hoja, cuantos: int, disposicion: dict,
                        alto_bloque: int, ancho_bloque: int) -> None:
    """Da a cada rótulo del pliego el tamaño físico que le corresponde."""
    columnas_usadas = disposicion["columnas"]
    total_bloques = -(-cuantos // columnas_usadas)

    for c in range(columnas_usadas):
        base = BLOQUE_COLUMNAS.start + c * ancho_bloque
        _repartir_anchos(hoja, base, disposicion["ancho"])
        if c < columnas_usadas - 1:
            hoja.column_dimensions[_letra(base + len(BLOQUE_COLUMNAS))].width = 1.2
    for f in range(total_bloques):
        base = BLOQUE_FILAS.start + f * alto_bloque
        _repartir_altos(hoja, base, disposicion["alto"])
        hoja.row_dimensions[base + len(BLOQUE_FILAS)].height = 8

    hoja.print_area = (f"{_letra(BLOQUE_COLUMNAS.start)}{BLOQUE_FILAS.start}:"
                       f"{_letra(BLOQUE_COLUMNAS.start + columnas_usadas * ancho_bloque - 2)}"
                       f"{BLOQUE_FILAS.start + total_bloques * alto_bloque - 2}")
    hoja.page_setup.orientation = disposicion["orientacion"]
    hoja.page_setup.paperSize = OFICIO
    hoja.page_setup.scale = 100
    hoja.page_margins.left = hoja.page_margins.right = 0.3
    hoja.page_margins.top = hoja.page_margins.bottom = 0.3


def _letra(columna: int) -> str:
    from openpyxl.utils import get_column_letter
    return get_column_letter(columna)


def _proporcional(valores: list[float], objetivo_cm: float) -> list[float]:
    total = sum(valores) or 1
    objetivo_px = objetivo_cm / 2.54 * 96
    return [v * objetivo_px / total for v in valores]


# Las medidas del bloque original, para repartirlas conservando la proporción del formato.
_ANCHOS_BLOQUE = [26.43, 8.71, 8.43, 11.71, 12.71, 8.43, 19.71, 18.14]
_ALTOS_BLOQUE = [18.6, 16.5, 28.5, 34.5, 39.75, 39.75, 39.75, 39.75, 39.75, 42.0, 42.0, 42.0,
                 42.0, 42.0]
# Lo que mide el rótulo tal como viene en la plantilla, en centímetros.
BLOQUE_ANCHO_NATURAL_CM = sum(7 * a + 5 for a in _ANCHOS_BLOQUE) / 96 * 2.54
BLOQUE_ALTO_NATURAL_CM = sum(_ALTOS_BLOQUE) / 72 * 2.54


def _repartir_anchos(hoja, columna_base: int, ancho_cm: float) -> None:
    for i, px in enumerate(_proporcional([7 * a + 5 for a in _ANCHOS_BLOQUE], ancho_cm)):
        hoja.column_dimensions[_letra(columna_base + i)].width = max(1.0, (px - 5) / 7)


def _repartir_altos(hoja, fila_base: int, alto_cm: float) -> None:
    objetivo_pt = alto_cm / 2.54 * 72
    total = sum(_ALTOS_BLOQUE) or 1
    for i, alto in enumerate(_ALTOS_BLOQUE):
        hoja.row_dimensions[fila_base + i].height = max(4.0, alto * objetivo_pt / total)


def _cortes_de_pagina(hoja, cuantos: int, disposicion: dict, alto_bloque: int) -> None:
    """Un salto de página cada vez que se completa una hoja, para que no se parta un rótulo."""
    from openpyxl.worksheet.pagebreak import Break
    por_pagina = disposicion["columnas"] * disposicion["filas"]
    paginas = -(-cuantos // por_pagina)
    for p in range(1, paginas):
        fila = BLOQUE_FILAS.start + p * disposicion["filas"] * alto_bloque - 1
        hoja.row_breaks.append(Break(id=fila))

