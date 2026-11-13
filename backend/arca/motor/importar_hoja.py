"""
Importación de hojas de control diligenciadas fuera de ARCA.

El equipo lleva meses levantando hojas de control en libros de cálculo. Esas hojas son
trabajo hecho y no hay ninguna razón para volver a escribirlas: se importan, se verifican con
las mismas reglas que las de aquí, y lo que esté mal sale señalado con el número del trámite.

El lector es deliberadamente tolerante con la forma del archivo, porque esas hojas se
diligenciaron a lo largo de meses y no todas quedaron iguales. Busca la fila de encabezados
por el nombre de las columnas, admite las variantes con que el equipo las escribió, y deduce
el código de carpeta del nombre del archivo, del nombre de la pestaña o de una celda.

Lo que NO hace es adivinar contenido. Si una columna no aparece, lo dice; si un trámite no
tiene tipo documental, lo señala; y nunca inventa una fecha ni un folio que no estén escritos.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Cada campo con las formas en que el equipo lo escribió en las hojas.
COLUMNAS = {
    "no_item": ("N", "NO", "N°", "NUM", "NUMERO", "ITEM", "NO ITEM", "#", "CONSECUTIVO"),
    "no_radicado": ("RADICADO", "NO RADICADO", "N RADICADO", "NUMERO DE RADICADO",
                    "RADICACION", "NO DE RADICADO"),
    "fecha": ("FECHA", "FECHA DEL DOCUMENTO", "FECHA DEL TRAMITE", "FECHA DOCUMENTO"),
    "tipo_documental": ("TIPO DOCUMENTAL", "TIPO DE DOCUMENTO", "TIPOLOGIA DOCUMENTAL",
                        "DESCRIPCION", "ASUNTO", "TIPO"),
    "folio_desde": ("DESDE", "FOLIO DESDE", "FOL DESDE", "F DESDE", "FOLIO INICIAL"),
    "folio_hasta": ("HASTA", "FOLIO HASTA", "FOL HASTA", "F HASTA", "FOLIO FINAL"),
    "observaciones": ("OBSERVACIONES", "OBSERVACION", "NOTAS", "OBS"),
    "sistema_informacion": ("SISTEMA DE INFORMACION", "SISTEMA"),
    "expediente_sgdea": ("EXPEDIENTE SGDEA", "EXPEDIENTE EN EL SGDEA", "SGDEA"),
    "enlace_acceso": ("ENLACE", "ENLACE DE ACCESO", "URL", "RUTA"),
}

# Campos del encabezado que puedan venir como pares de etiqueta y valor.
ENCABEZADO = {
    "codigo_serie": ("CODIGO SERIE", "COD SERIE", "CODIGO DE SERIE"),
    "serie": ("SERIE",),
    "codigo_subserie": ("CODIGO SUBSERIE", "COD SUBSERIE", "CODIGO DE SUBSERIE"),
    "subserie": ("SUBSERIE",),
    "nombre_expediente": ("NOMBRE DEL EXPEDIENTE", "NOMBRE EXPEDIENTE", "EXPEDIENTE"),
    # Los campos 15 y 16 del formato oficial se llaman así, con todas sus letras. Se listan
    # tal cual porque es como vienen en las hojas que el equipo ya diligenció.
    "responsable": ("RESPONSABLE", "RESPONSABLE DEL DILIGENCIAMIENTO", "DILIGENCIO",
                    "NOMBRE Y FIRMA RESPONSABLE DE DILIGENCIAMIENTO",
                    "NOMBRE Y FIRMA RESPONSABLE", "NOMBRE Y FIRMA", "FIRMA RESPONSABLE"),
    # No se pone «FECHA» a secas a propósito: se tragaría «10. Fecha del documento», que es
    # la columna de la tabla y no la fecha en que se diligenció la hoja.
    "fecha_diligenciamiento": ("FECHA DE DILIGENCIAMIENTO", "FECHA DILIGENCIAMIENTO",
                               "FECHA DD M AAAA", "FECHA DD MM AAAA"),
    "dependencia": ("DEPENDENCIA", "OFICINA PRODUCTORA"),
    "codigo_dependencia": ("CODIGO DEPENDENCIA", "COD DEPENDENCIA"),
    "periodo": ("PERIODO", "PERIODO INSTITUCIONAL", "PERIODO TVD"),
}

# Pestañas que NO son hojas de control aunque nombren sus casillas. El formato oficial trae
# una de instrucciones que explica cada columna, y ahí aparece «11. Tipo documental» igual
# que en la tabla de verdad; leerla importaría las instrucciones como si fueran trámites.
# Se comprueba el nombre escrito de cualquier manera, porque en los archivos del equipo
# aparece como «Intrucciones», sin la ese.
_PESTANAS_QUE_NO_SON = ("INSTRUC", "INTRUC", "CONTROL DE CAMBIOS", "CAMBIOS", "DEFINICION",
                        "AYUDA", "EJEMPLO", "PORTADA", "INDICE")

# Un identificador de carpeta genérico: letras y un número («CP-00374», «EXP 12», «CARPETA_0007»).
# El código que se lee aquí es solo una pista: ARCA lo confirma contra el inventario del proyecto.
_CARPETA = re.compile(r"\b[A-Z]{1,12}[\s_-]?\d{1,8}\b", re.IGNORECASE)
_CARPETA_CORTA = _CARPETA


@dataclass
class HojaImportada:
    """Una hoja de control leída de un libro de cálculo."""
    codigo_carpeta: str = ""
    hoja: str = ""
    encabezado: dict = field(default_factory=dict)
    tramites: list[dict] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def sirve(self) -> bool:
        return bool(self.codigo_carpeta and self.tramites and not self.error)


def _plano(valor) -> str:
    """Mayúsculas, sin tildes y sin signos, para comparar encabezados escritos de cualquier forma."""
    t = unicodedata.normalize("NFD", str(valor or "").strip().upper())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", t)).strip()


# Muchos formatos oficiales de hoja de control numeran todas sus casillas: «11. Tipo documental», «12.1
# Desde», «13.2 No expediente SGDEA». Ese número es parte del formato, no del nombre de la
# columna, y comparando el texto completo nunca coincidía con nada. Por eso se le quita.
_NUMERACION = re.compile(r"^(?:\d{1,2}(?:[ .]\d{1,2})*)\s+")


def _sin_numeracion(plano: str) -> str:
    return _NUMERACION.sub("", plano).strip()


def _campo_de(plano: str, catalogo: dict) -> str:
    """
    A qué campo corresponde un encabezado.

    Primero se busca la coincidencia exacta, y solo si no la hay se admite que el encabezado
    EMPIECE por una de las formas conocidas. Eso es lo que permite leer «10. Fecha del
    documento (dd/mm/aaaa)» sin tener que listar cada variante de la aclaración entre
    paréntesis que cada quien escribió distinto. Se prueban las formas de la más larga a la
    más corta, para que «TIPO DOCUMENTAL» gane antes que «TIPO».
    """
    limpio = _sin_numeracion(plano)
    if not limpio:
        return ""
    for campo, formas in catalogo.items():
        if limpio in formas:
            return campo
    for campo, formas in catalogo.items():
        for forma in sorted(formas, key=len, reverse=True):
            if limpio.startswith(forma + " "):
                return campo
    return ""


def _carpeta_de(texto: str) -> str:
    e = _CARPETA.search(str(texto or "")) or _CARPETA_CORTA.search(str(texto or ""))
    return e.group(0).strip() if e else ""


def _texto(celda) -> str:
    if celda is None:
        return ""
    if hasattr(celda, "isoformat"):
        return celda.isoformat()[:10]
    if isinstance(celda, float) and celda.is_integer():
        return str(int(celda))
    # Los saltos de línea dentro de una casilla se vuelven un espacio: vienen de cómo se
    # escribió en Excel y en la hoja de control rompen el renglón sin aportar nada.
    return re.sub(r"\s*\n\s*", " ", str(celda)).strip()


def leer_libro(ruta: Path, nombre_archivo: str = "") -> list[HojaImportada]:
    """
    Lee todas las pestañas del libro y devuelve una hoja de control por cada una que lo sea.

    Un libro puede traer una sola hoja o una pestaña por expediente, que es como quedaron
    las exportaciones del equipo. Las pestañas que no tengan pinta de hoja de control se
    ignoran en silencio: suelen ser índices o instrucciones.
    """
    # El Excel viejo es un formato distinto por dentro, no una variante del actual, y no se
    # puede leer con la misma herramienta. Decirlo así, con la salida concreta, evita que la
    # persona crea que el archivo se dañó.
    if str(nombre_archivo or ruta.name).lower().endswith((".xls", ".ods")):
        return [HojaImportada(error=(
            "Ese archivo está en el formato viejo de Excel (.xls) o en formato abierto "
            "(.ods), y ARCA lee el formato actual. Ábralo en Excel, use «Guardar como» y "
            "escoja «Libro de Excel (*.xlsx)». El contenido no se pierde."))]
    try:
        import openpyxl
        libro = openpyxl.load_workbook(ruta, data_only=True, read_only=True)
    except Exception as e:
        return [HojaImportada(error=(
            f"No se pudo abrir el libro ({type(e).__name__}). Suele pasar cuando el archivo "
            "quedó a medio descargar o está protegido con contraseña. Ábralo en Excel para "
            "comprobar que sirve y vuelva a subirlo."))]

    del_archivo = _carpeta_de(nombre_archivo or ruta.name)
    salida: list[HojaImportada] = []
    for nombre in libro.sheetnames:
        leida = _leer_pestana(libro[nombre], nombre, del_archivo)
        if leida:
            salida.append(leida)
    if not salida:
        return [HojaImportada(error="El libro no tiene ninguna pestaña con forma de hoja de "
                                    "control: no se encontró la fila de encabezados con la "
                                    "columna «tipo documental».")]
    return salida


def _leer_pestana(pestana, nombre: str, carpeta_del_archivo: str) -> HojaImportada | None:
    if any(marca in _plano(nombre) for marca in _PESTANAS_QUE_NO_SON):
        return None
    filas = [list(f) for f in pestana.iter_rows(values_only=True)]
    if not filas:
        return None

    fila_encabezado, mapa = _encontrar_encabezados(filas)
    if fila_encabezado is None:
        return None

    h = HojaImportada(hoja=nombre)
    h.codigo_carpeta = (_carpeta_de(nombre) or carpeta_del_archivo
                        or _buscar_carpeta(filas[:fila_encabezado]))
    if not h.codigo_carpeta:
        h.avisos.append("No fue posible deducir el código de carpeta de esta pestaña. "
                        "Nombre el archivo con el identificador del expediente (por ejemplo CP-00374.xlsx) o escríbalo en la hoja.")

    h.encabezado = _leer_encabezado(filas[:fila_encabezado])

    faltan = [c for c in ("fecha", "tipo_documental", "folio_desde") if c not in mapa]
    if faltan:
        h.avisos.append("A la hoja le faltan columnas: " + ", ".join(
            c.replace("_", " ") for c in faltan) + ".")

    for numero, fila in enumerate(filas[fila_encabezado + 1:], start=1):
        if all(c is None or str(c).strip() == "" for c in fila):
            continue

        # Debajo de la tabla vienen los campos 15 y 16 del formato, que son el responsable y
        # la fecha de diligenciamiento. Sin reconocerlos, ese pie entraba como si fuera un
        # trámite más: uno con fecha, sin tipo documental y sin folios. Aquí se leen, se
        # guardan donde corresponde y la lectura de trámites se detiene.
        pie = _leer_pie(filas[fila_encabezado + numero:])
        if pie:
            h.encabezado.update({k: v for k, v in pie.items() if k not in h.encabezado})
            break

        t = {campo: _texto(fila[i]) if i < len(fila) else "" for campo, i in mapa.items()}
        if not any(t.get(c) for c in ("fecha", "tipo_documental", "folio_desde", "folio_hasta")):
            continue
        t["fila"] = fila_encabezado + 1 + numero          # fila real del Excel, para señalarla
        t.setdefault("no_item", "")
        h.tramites.append(t)

    # Una tabla de trámites de verdad tiene fechas o folios. Si lo único que hay es texto en
    # la columna del tipo documental, lo que se está leyendo es una lista de instrucciones o
    # un índice, no una hoja de control, y no tiene por qué entrar al flujo.
    con_datos = [t for t in h.tramites
                 if t.get("fecha") or t.get("folio_desde") or t.get("folio_hasta")]
    if h.tramites and not con_datos:
        return None

    if not h.tramites:
        h.avisos.append("La hoja no tiene ningún trámite con datos.")
    return h


def _encontrar_encabezados(filas) -> tuple[int | None, dict]:
    """
    La fila de encabezados es la primera que nombra el tipo documental. No se asume que sea
    la primera fila del archivo: estas hojas suelen traer arriba el membrete y los datos del
    expediente.
    """
    for indice, fila in enumerate(filas[:60]):
        if not any(_campo_de(_plano(c), COLUMNAS) == "tipo_documental" for c in fila):
            continue
        mapa: dict[str, int] = {}
        ultima = indice

        # El encabezado del formato oficial ocupa DOS renglones: arriba «12. Cantidad de
        # folios» y abajo «12.1 Desde» y «12.2 Hasta». Leyendo solo el primero se perdían la
        # foliación y el vínculo archivístico, que están todos en el segundo.
        for desplazamiento in (0, 1):
            if indice + desplazamiento >= len(filas):
                break
            renglon = filas[indice + desplazamiento]
            encontro = False
            for columna, celda in enumerate(renglon):
                if str(celda or "").strip() == "#":
                    mapa.setdefault("no_item", columna)
                    encontro = True
                    continue
                campo = _campo_de(_plano(celda), COLUMNAS)
                if campo and campo not in mapa:
                    mapa[campo] = columna
                    encontro = True
            if desplazamiento and encontro:
                ultima = indice + desplazamiento

        if "tipo_documental" in mapa:
            return ultima, mapa
    return None, {}


_PIE = ("responsable", "fecha_diligenciamiento")


def _leer_pie(filas) -> dict:
    """
    Si este renglón es el pie del formato, devuelve lo que trae; si no, nada.

    El pie se reconoce porque nombra el campo 15 o el 16. Se leen los dos de una vez, aunque
    estén en renglones distintos, porque en el formato oficial la firma va varias filas
    encima de la fecha.
    """
    if not filas:
        return {}
    if not any(_campo_de(_plano(c).rstrip(" :"), ENCABEZADO) in _PIE for c in filas[0]):
        return {}
    return _leer_encabezado(filas)


def _buscar_carpeta(filas) -> str:
    for fila in filas:
        for celda in fila:
            encontrado = _carpeta_de(_texto(celda))
            if encontrado:
                return encontrado
    return ""


def _leer_encabezado(filas) -> dict:
    """
    Los datos del expediente que están arriba de la tabla, como pares de etiqueta y valor.
    Se admite que el valor esté en la celda de al lado o en la de abajo.
    """
    datos: dict[str, str] = {}
    for i, fila in enumerate(filas):
        for j, celda in enumerate(fila):
            campo = _campo_de(_plano(celda).rstrip(" :"), ENCABEZADO)
            if not campo or campo in datos:
                continue
            # El valor es la PRIMERA casilla con algo escrito a la derecha de la etiqueta que
            # no sea otra etiqueta. Se recorre el renglón entero y no un número fijo de
            # casillas, porque en el formato oficial van combinadas y el dato puede quedar a
            # dos, a cuatro o a seis columnas según el campo.
            valor = ""
            for adelante in range(j + 1, len(fila)):
                candidato = _texto(fila[adelante])
                if not candidato:
                    continue
                if _campo_de(_plano(candidato).rstrip(" :"), ENCABEZADO):
                    break
                valor = candidato
                break
            if not valor and i + 1 < len(filas) and j < len(filas[i + 1]):
                valor = _texto(filas[i + 1][j])
            if valor:
                datos[campo] = valor
    return datos
