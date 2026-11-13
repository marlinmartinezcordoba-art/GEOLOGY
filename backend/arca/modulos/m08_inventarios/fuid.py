"""Lectura tolerante del FUID (Formato Único de Inventario Documental del AGN). Funciones puras, sin base de datos.

Reciclado de Kustos (expedientes/servicios/importar_fuid.py) y de la lectura tolerante de hojas de GEOLOGY:
- ubica la fila del encabezado aunque arriba haya membrete, logo o títulos;
- entiende el encabezado de dos niveles del AGN («Fechas extremas» › Inicial / Final;
  «Unidad de conservación» › Caja / Carpeta / Tomo / Otro);
- reconoce las columnas por su nombre, y quien importa puede corregir el mapeo a mano;
- nunca inventa un dato que falta: lo marca como error o como aviso.

Agregado en ARCA: el campo «identificador» (código de la carpeta o del expediente), que es el que llevan
los archivos digitalizados. Si el FUID no lo trae, el identificador es el número de orden.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import openpyxl

from arca.nucleo.errores import DatosInvalidos

# Orden de búsqueda: el primer campo cuyo patrón coincide se queda con la columna.
CAMPOS: list[tuple[str, str, re.Pattern[str]]] = [
    ("orden", "Número de orden", re.compile(r"(numero|no\.?|n°|nro|num)\s*(de\s*)?orden|^orden$|^no\.?$|^item$")),
    ("identificador", "Identificador de la unidad", re.compile(r"identificador|signatura|codigo (de |del )?(la )?(carpeta|unidad|expediente)|^id (carpeta|unidad)")),
    ("fecha_inicial", "Fecha inicial", re.compile(r"inicial|^desde$|fecha inicio")),
    ("fecha_final", "Fecha final", re.compile(r"final|^hasta$")),
    ("caja", "Caja", re.compile(r"^caja")),
    ("carpeta", "Carpeta", re.compile(r"^carpeta")),
    ("tomo", "Tomo", re.compile(r"^tomo")),
    ("otro", "Otro", re.compile(r"^otro")),
    ("folios", "Número de folios", re.compile(r"folio")),
    ("soporte", "Soporte", re.compile(r"soporte")),
    ("frecuencia", "Frecuencia de consulta", re.compile(r"frecuencia")),
    ("notas", "Notas", re.compile(r"nota|observac")),
    ("codigo_serie", "Código de la serie o subserie", re.compile(r"^codigo|^cod\.?$")),
    ("nombre", "Nombre de las series, subseries o asuntos", re.compile(r"nombre|asunto|titulo|descripcion")),
]
NOMBRES_CAMPO = {c: n for c, n, _ in CAMPOS}
UNIDADES = ("caja", "carpeta", "tomo", "otro")


def plano(t: Any) -> str:
    s = unicodedata.normalize("NFKD", "" if t is None else str(t)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.replace("_", " ")).strip().lower()


def texto(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return re.sub(r"\s+", " ", str(v)).strip()


def clave_de(identificador: str) -> str:
    """Forma comparable de un identificador: sin tildes, sin signos y sin ceros a la izquierda en cada número.

    «CP-00374», «cp 374» y «CP374» dan la misma clave; así un archivo «CARPETA_00374.pdf» se reconoce.
    """
    s = unicodedata.normalize("NFKD", identificador or "").encode("ascii", "ignore").decode().upper()
    partes = re.findall(r"[A-Z]+|\d+", s)
    return "".join(str(int(p)) if p.isdigit() else p for p in partes)


def detectar_columnas(encabezados: list[str]) -> dict[str, int]:
    c: dict[str, int] = {}
    for i, h in enumerate(encabezados):
        p = plano(h)
        if not p:
            continue
        for campo, _, patron in CAMPOS:
            if campo not in c and patron.search(p):
                c[campo] = i
                break
    return c


@dataclass
class Hoja:
    nombre_hoja: str | None
    fila_encabezado: int  # número de fila (1 = primera) donde empiezan los datos menos uno
    encabezados: list[str]
    mapeo: dict[str, int]
    filas: list[tuple[int, list[str]]] = field(default_factory=list)  # (número de fila en el archivo, celdas)


def _filas_excel(contenido: bytes) -> tuple[str, list[list[Any]]]:
    try:
        libro = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001 — archivo dañado o no es Excel
        raise DatosInvalidos("El archivo no es un libro de Excel (.xlsx) legible") from exc
    hoja = libro.worksheets[0]
    return hoja.title, [list(f) for f in hoja.iter_rows(values_only=True)]


def _filas_csv(contenido: bytes) -> list[list[Any]]:
    try:
        contenido_texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        contenido_texto = contenido.decode("latin-1")
    muestra = contenido_texto[:4000]
    separador = ";" if muestra.count(";") >= muestra.count(",") else ","
    return [list(f) for f in csv.reader(io.StringIO(contenido_texto), delimiter=separador)]


def _encabezado(filas: list[list[Any]]) -> tuple[int, list[str], dict[str, int]]:
    """Fila del encabezado (de uno o dos niveles), los títulos combinados y la posición de cada campo."""
    for i in range(min(len(filas), 40)):
        arriba = [texto(x) for x in filas[i]]
        c = detectar_columnas(arriba)
        if "nombre" in c and ("orden" in c or "identificador" in c or "codigo_serie" in c):
            if i + 1 < len(filas):
                abajo = [texto(x) for x in filas[i + 1]]
                sub = detectar_columnas(abajo)
                if any(k in sub for k in ("fecha_inicial", "caja", "carpeta")) and not any(re.fullmatch(r"\d+", x or "-") for x in abajo):
                    ancho = max(len(arriba), len(abajo))
                    combinados = [(abajo[j] if j < len(abajo) and abajo[j] else (arriba[j] if j < len(arriba) else "")) for j in range(ancho)]
                    return i + 2, combinados, detectar_columnas(combinados)
            return i + 1, arriba, c
    raise DatosInvalidos(
        "No se encontró el encabezado del FUID. Debe tener al menos la columna «Nombre de las series, subseries o asuntos» "
        "y el «Número de orden» o el identificador de la unidad."
    )


def leer(contenido: bytes, nombre_archivo: str, max_filas: int) -> Hoja:
    ext = nombre_archivo.lower().rsplit(".", 1)[-1]
    nombre_hoja = None
    if ext in ("csv", "txt"):
        filas = _filas_csv(contenido)
    else:
        nombre_hoja, filas = _filas_excel(contenido)
    inicio, encabezados, mapeo = _encabezado(filas)
    datos: list[tuple[int, list[str]]] = []
    for n, fila in enumerate(filas[inicio:], start=inicio + 1):
        celdas = [texto(x) for x in fila]
        if not any(celdas):
            continue
        datos.append((n, celdas))
    if not datos:
        raise DatosInvalidos("El FUID no tiene registros debajo del encabezado")
    if len(datos) > max_filas:
        raise DatosInvalidos(f"El FUID tiene {len(datos)} registros y el máximo por archivo es {max_filas}: divídalo")
    return Hoja(nombre_hoja, inicio, encabezados, mapeo, datos)


def validar_mapeo(mapeo: dict[str, int], ancho: int) -> dict[str, int]:
    desconocidos = set(mapeo) - set(NOMBRES_CAMPO)
    if desconocidos:
        raise DatosInvalidos(f"Campos desconocidos en el mapeo: {', '.join(sorted(desconocidos))}")
    for campo, i in mapeo.items():
        if not isinstance(i, int) or not 0 <= i < ancho:
            raise DatosInvalidos(f"La columna asignada a «{NOMBRES_CAMPO[campo]}» no existe")
    usadas = [i for i in mapeo.values()]
    if len(usadas) != len(set(usadas)):
        raise DatosInvalidos("Una misma columna no puede asignarse a dos campos")
    if "nombre" not in mapeo:
        raise DatosInvalidos("Falta asignar la columna del nombre de la serie, subserie o asunto")
    if "orden" not in mapeo and "identificador" not in mapeo:
        raise DatosInvalidos("Falta asignar la columna del número de orden o la del identificador de la unidad")
    return mapeo


def _fecha(v: str, final: bool = False) -> tuple[date | None, str | None]:
    if not v:
        return None, None
    if plano(v) in ("s.f.", "sf", "s.f", "sin fecha", "n/a", "-"):
        return None, None
    if re.fullmatch(r"\d{4}", v):
        return (date(int(v), 12, 31) if final else date(int(v), 1, 1)), None
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(v, formato).date(), None
        except ValueError:
            continue
    return None, f"la fecha «{v}» no se reconoce (use AAAA-MM-DD o DD/MM/AAAA)"


def _soporte(v: str) -> str:
    p = plano(v)
    if p in ("e", "electronico", "digital", "electronica"):
        return "electronico"
    if "hibrid" in p or p in ("h", "mixto"):
        return "hibrido"
    return "fisico"


def normalizar(celdas: list[str], mapeo: dict[str, int]) -> tuple[dict[str, Any], list[str], list[str]]:
    """Una fila: (valores normalizados, errores que impiden integrarla, avisos que solo quedan anotados)."""
    v = {campo: (celdas[i] if i < len(celdas) else "") for campo, i in mapeo.items()}
    errores: list[str] = []
    avisos: list[str] = []
    identificador = v.get("identificador") or v.get("orden") or ""
    if not identificador:
        errores.append("falta el identificador de la unidad (o el número de orden)")
    elif not clave_de(identificador):
        errores.append(f"el identificador «{identificador}» no tiene letras ni números")
    nombre = v.get("nombre", "")
    if len(nombre) < 3:
        errores.append("falta el nombre de la serie, subserie o asunto")
    fi, e1 = _fecha(v.get("fecha_inicial", ""))
    ff, e2 = _fecha(v.get("fecha_final", ""), final=True)
    errores += [e for e in (e1, e2) if e]
    if fi and ff and fi > ff:
        errores.append("la fecha inicial es posterior a la final")
    if not fi and not ff and not e1 and not e2:
        avisos.append("sin fechas extremas (s.f.)")
    folios = None
    if folios_txt := v.get("folios", ""):
        if re.fullmatch(r"\d+", folios_txt):
            folios = int(folios_txt)
        else:
            errores.append(f"los folios «{folios_txt}» no son un número entero")
    else:
        avisos.append("sin número de folios")
    soporte = _soporte(v.get("soporte", ""))
    if soporte != "electronico" and not any(v.get(u) for u in UNIDADES):
        avisos.append("sin unidad de conservación (caja, carpeta, tomo u otro)")
    normalizado = {
        "identificador": identificador,
        "clave": clave_de(identificador),
        "numero_orden": v.get("orden") or None,
        "codigo_serie": v.get("codigo_serie") or None,
        "nombre": nombre,
        "fecha_inicial": fi.isoformat() if fi else None,
        "fecha_final": ff.isoformat() if ff else None,
        "folios": folios,
        "soporte": soporte,
        "frecuencia_consulta": v.get("frecuencia") or None,
        "notas": v.get("notas") or None,
        **{u: (v.get(u) or None) for u in UNIDADES},
    }
    return normalizado, errores, avisos
