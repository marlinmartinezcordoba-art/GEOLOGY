"""Lectura tolerante de la TRD, la TVD y el CCD desde una hoja de cálculo. Funciones puras, sin base de datos.

Reciclado de Kustos (instrumentos/servicios/importar_trd.py), que a su vez recicla la lectura de hojas de
GEOLOGY: ubica la fila de encabezados por su contenido y no por su posición, combina encabezados de dos niveles
(«RETENCIÓN» sobre «AG | AC»), normaliza códigos, nombres, tiempos y disposición, y deja constancia de cada
corrección. Acepta dos formas:

1. Tabular: una fila por serie o subserie, con columnas de código y nombre de dependencia, serie, subserie,
   tipos documentales (separados por «;» o salto de línea), AG, AC, disposición y soporte.
2. Formato del AGN: una hoja por dependencia («Oficina productora» y su código en el encabezado), una columna
   de código y una columna «Series, subseries y tipos documentales» en la que las filas sin código son los tipos
   documentales de la serie o subserie anterior.

Modos: «trd» exige AG, AC y disposición; «tvd» exige disposición (la retención en gestión no aplica a un fondo
acumulado); «ccd» solo clasifica. Nada se inventa: lo que falta es error o aviso.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import openpyxl

from arca.nucleo.errores import DatosInvalidos


def _plano(t: Any) -> str:
    s = "" if t is None else str(t)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _texto(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"[ \t]+", " ", str(v)).strip()


MAX_FILAS = 5000


def _plano(t: Any) -> str:
    s = "" if t is None else str(t)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _texto(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"[ \t]+", " ", str(v)).strip()


# Encabezados reconocidos (texto plano, sin tildes). El orden importa: lo específico antes que lo general.
COLUMNAS: list[tuple[str, re.Pattern[str]]] = [
    ("codigo_dependencia", re.compile(r"(codigo|cod\.?).*(dependencia|oficina|unidad)|^d$|^dep$")),
    ("dependencia", re.compile(r"^(dependencia|oficina productora|unidad administrativa|oficina)( productora)?$|nombre.*(dependencia|oficina)")),
    ("codigo_subserie", re.compile(r"(codigo|cod\.?).*subserie|^sb$|^ss$|^sub$")),
    ("codigo_serie", re.compile(r"(codigo|cod\.?).*serie|^s$")),
    ("nombre_mixto", re.compile(r"series?,? subseries? y tipos|series y subseries|series documentales")),
    ("subserie", re.compile(r"^(nombre (de la )?)?subseries?( documental(es)?)?$")),
    ("serie", re.compile(r"^(nombre (de la )?)?series?( documental(es)?)?$")),
    ("tipos", re.compile(r"tipos? documental")),
    ("ag", re.compile(r"(^|retencion )(ag|a\.g\.?|archivo de gestion|gestion)$")),
    ("ac", re.compile(r"(^|retencion )(ac|a\.c\.?|archivo central|central)$")),
    ("ct", re.compile(r"(^|disposicion( final)? )(ct|c\.t\.?|conservacion total)$")),
    ("e", re.compile(r"(^|disposicion( final)? )(e|el|eliminacion)$")),
    ("s", re.compile(r"(^|disposicion( final)? )(s|seleccion)$")),
    ("d", re.compile(r"(^|disposicion( final)? )(d|m|m/d|d/m|digitalizacion|microfilmacion|medio tecnico)$")),
    ("disposicion", re.compile(r"^disposicion( final)?$")),
    ("soporte_f", re.compile(r"(^|soporte )(f|p|fisico|papel)$")),
    ("soporte_e", re.compile(r"(^|soporte )(e|el|electronico)$")),
    ("soporte", re.compile(r"^soporte$")),
    ("procedimiento", re.compile(r"procedimiento|observaciones")),
    ("acceso", re.compile(r"acceso|clasificacion de la informacion|confidencialidad|reserva")),
    ("codigo", re.compile(r"^codigo$|^cod\.?$")),
]


@dataclass
class Fila:
    hoja: str
    fila: int
    codigo_dependencia: str
    dependencia: str
    codigo: str
    nombre: str
    nivel: str  # serie | subserie
    padre: str | None
    tipos: list[str] = field(default_factory=list)
    ag: int | None = None
    ac: int | None = None
    disposicion: str | None = None
    soporte: str | None = None
    procedimiento: str = ""
    acceso: str = "publica"


@dataclass
class Resultado:
    filas: list[Fila] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    correcciones: list[str] = field(default_factory=list)
    modo: str = "trd"  # trd | tvd | ccd


def _detectar(fila_a: list[Any], fila_b: list[Any] | None) -> dict[str, int]:
    """Columnas por su texto. Un encabezado de dos niveles se lee combinando la fila con la siguiente."""
    columnas: dict[str, int] = {}
    total = max(len(fila_a), len(fila_b or []))
    superior = ""
    for i in range(total):
        a = _plano(fila_a[i] if i < len(fila_a) else None)
        b = _plano(fila_b[i] if fila_b and i < len(fila_b) else None)
        superior = a or (superior if b else "")  # una celda combinada deja vacías las siguientes
        candidatos = [x for x in (f"{superior} {b}".strip() if b else "", b, a) if x]
        for texto in candidatos:
            for clave, patron in COLUMNAS:
                if clave not in columnas and patron.search(texto):
                    columnas[clave] = i
                    break
            else:
                continue
            break
    return columnas


def _es_encabezado(c: dict[str, int], modo: str = "trd") -> bool:
    nombre = any(k in c for k in ("serie", "subserie", "nombre_mixto"))
    if modo == "ccd":  # el CCD no lleva tiempos: basta con códigos y nombres
        return nombre and any(k in c for k in ("codigo_serie", "codigo", "codigo_dependencia"))
    if modo == "tvd":  # la TVD de un fondo acumulado puede no traer retención en gestión
        return nombre and any(k in c for k in ("ac", "ag", "ct", "e", "s", "d", "disposicion"))
    tiempos = "ag" in c or "ac" in c
    return nombre and tiempos


def _entero(v: Any) -> int | None:
    t = _texto(v)
    m = re.search(r"\d+", t)
    return int(m.group()) if m else None


def _marcada(v: Any) -> bool:
    return _plano(v) not in ("", "0", "no", "-", "n/a", "na")


def _normalizar_nombre(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip(" .-–")
    if t.isupper() and len(t) > 3:
        t = t.capitalize()
    return t


def _codigo(t: Any) -> str:
    return re.sub(r"\s+", "", _texto(t)).strip(".-")


def _tipos(t: Any) -> list[str]:
    partes = re.split(r"[;\n\r•]+|\s{2,}|(?<=[a-záéíóú])\s*,\s*(?=[A-ZÁÉÍÓÚ])", _texto(t))
    return [_normalizar_nombre(re.sub(r"^\s*[-–*\d.)]+\s*", "", p)) for p in partes if p and p.strip(" -–*")]


def _disposicion(fila: list[Any], c: dict[str, int], r: Resultado, donde: str) -> str | None:
    marcas = [d for d, k in (("CT", "ct"), ("E", "e"), ("S", "s"), ("D", "d")) if k in c and c[k] < len(fila) and _marcada(fila[c[k]])]
    if not marcas and "disposicion" in c and c["disposicion"] < len(fila):
        t = _plano(fila[c["disposicion"]])
        mapa = {"ct": "CT", "conservacion total": "CT", "e": "E", "eliminacion": "E", "s": "S", "seleccion": "S", "d": "D", "m": "D", "digitalizacion": "D", "microfilmacion": "D"}
        marcas = [v for k, v in mapa.items() if re.search(rf"(^|[\s/,-]){re.escape(k)}($|[\s/,-])", t)]
        marcas = list(dict.fromkeys(marcas))
    if len(marcas) > 1:
        # Combinaciones válidas en la práctica archivística: se conserva la de mayor protección y se informa.
        orden = ["CT", "S", "D", "E"]
        elegida = min(marcas, key=orden.index)
        r.avisos.append(f"{donde}: disposición múltiple ({'+'.join(marcas)}); se registra «{elegida}». Revise el procedimiento.")
        return elegida
    return marcas[0] if marcas else None


def _soporte(fila: list[Any], c: dict[str, int]) -> str | None:
    f = "soporte_f" in c and c["soporte_f"] < len(fila) and _marcada(fila[c["soporte_f"]])
    e = "soporte_e" in c and c["soporte_e"] < len(fila) and _marcada(fila[c["soporte_e"]])
    if not (f or e) and "soporte" in c and c["soporte"] < len(fila):
        t = _plano(fila[c["soporte"]])
        f = bool(re.search(r"\b(f|p|fisico|papel|analogo)\b", t))
        e = bool(re.search(r"\b(e|el|electronico|digital)\b", t))
    return "hibrido" if f and e else "fisico" if f else "electronico" if e else None


def _acceso(v: Any) -> str:
    t = _plano(v)
    return "reservada" if "reserv" in t else "clasificada" if "clasif" in t else "publica"


def _encabezado_hoja(filas: list[list[Any]], hasta: int) -> tuple[str, str]:
    """«Oficina productora: Secretaría de Planeación» y «Código: 120» encima de la tabla (formato AGN)."""
    codigo, nombre = "", ""
    for fila in filas[:hasta]:
        celdas = [_texto(x) for x in fila if _texto(x)]
        for i, t in enumerate(celdas):
            p = _plano(t)
            siguiente = celdas[i + 1] if i + 1 < len(celdas) else ""
            m = re.match(r"^(oficina productora|dependencia|unidad administrativa)\s*[:.]?\s*(.*)$", p)
            if m and not nombre:
                resto = t.split(":", 1)[1].strip() if ":" in t else ""
                nombre = resto or siguiente
            m2 = re.match(r"^(codigo( de la)?( dependencia| oficina)?)\s*[:.]?\s*(.*)$", p)
            if m2 and not codigo and "serie" not in p:
                resto = t.split(":", 1)[1].strip() if ":" in t else ""
                codigo = _codigo(resto or siguiente)
    return codigo, _normalizar_nombre(nombre)


def abrir_libro(contenido: bytes, nombre_archivo: str) -> Any:
    """Libro de Excel (.xlsx) o archivo CSV convertido en un libro de una hoja: los importadores leen los dos igual.

    CSV: separador «;» (Excel en español), «,», tabulador o «|», detectado solo; codificación UTF-8 o Windows-1252."""
    if contenido[:4] != b"PK\x03\x04" and nombre_archivo.lower().endswith((".csv", ".txt")):
        import csv  # noqa: PLC0415

        try:
            texto = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = contenido.decode("cp1252", errors="replace")
        try:
            dialecto = csv.Sniffer().sniff(texto[:4096], delimiters=";,\t|")
        except csv.Error:
            separador = ";" if texto[:4096].count(";") >= texto[:4096].count(",") else ","
            dialecto = type("DialectoArca", (csv.excel,), {"delimiter": separador})
        libro = openpyxl.Workbook()
        hoja = libro.active
        hoja.title = nombre_archivo.rsplit(".", 1)[0][:31] or "CSV"
        for n, fila in enumerate(csv.reader(io.StringIO(texto), dialecto), 1):
            if n > MAX_FILAS + 1:
                raise DatosInvalidos(f"«{nombre_archivo}» supera {MAX_FILAS} filas")
            hoja.append(fila)
        return libro
    try:
        return openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001 — archivo dañado o no es Excel
        raise DatosInvalidos(f"«{nombre_archivo}» no es un libro de Excel (.xlsx) ni un CSV legible") from exc


def leer(contenido: bytes, nombre_archivo: str = "trd.xlsx", modo: str = "trd") -> Resultado:
    libro = abrir_libro(contenido, nombre_archivo)
    r = Resultado(modo=modo)
    for hoja in libro.worksheets:
        filas = [list(f) for f in hoja.iter_rows(values_only=True)]
        if len(filas) > MAX_FILAS:
            raise DatosInvalidos(f"La hoja «{hoja.title}» supera {MAX_FILAS} filas")
        cabecera, c = None, {}
        for i in range(min(len(filas), 40)):
            det = _detectar(filas[i], filas[i + 1] if i + 1 < len(filas) else None)
            if _es_encabezado(det, modo):
                cabecera, c = i, det
                break
        if cabecera is None:
            continue
        # Si el encabezado es de dos niveles, los datos empiezan dos filas abajo.
        siguiente = filas[cabecera + 1] if cabecera + 1 < len(filas) else []
        sub = _detectar(siguiente, None) if siguiente else {}
        # Es la segunda fila del encabezado si trae varios subtítulos (AG, AC, CT…) y ningún número (los datos sí).
        numerica = any(isinstance(x, (int, float)) or re.fullmatch(r"\d+", _texto(x) or "-") for x in siguiente)
        doble = sum(k in sub for k in ("ag", "ac", "ct", "e", "s", "d", "soporte_f", "soporte_e")) >= 2 and not numerica
        inicio = cabecera + (2 if doble else 1)
        dep_codigo_hoja, dep_nombre_hoja = _encabezado_hoja(filas, cabecera)
        actual_serie: Fila | None = None
        actual: Fila | None = None
        for n, fila in enumerate(filas[inicio:], start=inicio + 1):
            celda = lambda k, fila=fila, c=c: fila[c[k]] if k in c and c[k] < len(fila) else None  # noqa: E731
            if all(_texto(x) == "" for x in fila):
                continue
            donde = f"Hoja «{hoja.title}», fila {n}"
            cod_dep = _codigo(celda("codigo_dependencia")) or dep_codigo_hoja
            dep = _normalizar_nombre(_texto(celda("dependencia"))) or dep_nombre_hoja
            cod_serie, cod_sub = _codigo(celda("codigo_serie")), _codigo(celda("codigo_subserie"))
            cod_mixto = _codigo(celda("codigo"))
            nom_serie, nom_sub = _texto(celda("serie")), _texto(celda("subserie"))
            mixto = _texto(celda("nombre_mixto"))
            # Formato AGN con D, S, Sb en columnas separadas: se arma el código completo.
            if cod_dep and cod_serie and not cod_serie.startswith(cod_dep):
                cod_serie = f"{cod_dep}-{cod_serie}"
            if cod_sub and cod_serie and not cod_sub.startswith(cod_serie):
                cod_sub = f"{cod_serie}.{cod_sub}"
            if cod_mixto and not (cod_serie or cod_sub):
                # Un solo código: «120-02» es serie; «120-02.01» (o tres partes) es subserie.
                partes = re.split(r"[.\-]", cod_mixto)
                if len(partes) >= 3:
                    cod_sub, cod_serie = cod_mixto, re.sub(r"[.\-][^.\-]+$", "", cod_mixto)
                else:
                    cod_serie = cod_mixto
            if mixto and not (nom_serie or nom_sub):
                if cod_sub:
                    nom_sub = mixto
                elif cod_serie:
                    nom_serie = mixto
            tipos = _tipos(celda("tipos"))
            if not (cod_serie or cod_sub or nom_serie or nom_sub):
                # Fila sin código ni nombre de serie: en el formato AGN es un tipo documental de la fila anterior.
                extra = _tipos(mixto) or tipos
                if extra and actual is not None:
                    actual.tipos.extend(extra)
                continue
            ag, ac = _entero(celda("ag")), _entero(celda("ac"))
            disp = _disposicion(fila, c, r, donde)
            soporte = _soporte(fila, c)
            proc = _texto(celda("procedimiento"))
            acceso = _acceso(celda("acceso"))
            if not cod_dep:
                r.errores.append(f"{donde}: falta el código de la dependencia (columna o encabezado «Código»)")
                continue
            if nom_serie and cod_serie and (not actual_serie or actual_serie.codigo != cod_serie):
                actual_serie = Fila(hoja.title, n, cod_dep, dep, cod_serie, _normalizar_nombre(nom_serie), "serie", None)
                r.filas.append(actual_serie)
                actual = actual_serie
            if nom_sub or cod_sub:
                if not cod_sub:
                    r.errores.append(f"{donde}: la subserie «{nom_sub}» no tiene código")
                    continue
                padre = actual_serie.codigo if actual_serie and cod_sub.startswith(actual_serie.codigo) else cod_serie or None
                if not padre:
                    r.errores.append(f"{donde}: la subserie {cod_sub} no tiene serie a la que pertenezca")
                    continue
                actual = Fila(hoja.title, n, cod_dep, dep, cod_sub, _normalizar_nombre(nom_sub) or cod_sub, "subserie", padre)
                r.filas.append(actual)
            elif not nom_serie:
                r.errores.append(f"{donde}: la serie {cod_serie} no tiene nombre")
                continue
            objetivo = actual
            if objetivo is None:
                continue
            if objetivo.fila != n and not (nom_sub or cod_sub):
                # La misma serie repetida en otra fila (sin subserie): se une si coincide; si contradice, es un error.
                choques = [x for x, (antes, ahora) in {"AG": (objetivo.ag, ag), "AC": (objetivo.ac, ac), "disposición": (objetivo.disposicion, disp)}.items() if antes is not None and ahora is not None and antes != ahora]
                if choques:
                    r.errores.append(f"{donde}: código {objetivo.codigo} repetido con datos distintos ({', '.join(choques)}) a la fila {objetivo.fila}")
                    continue
                r.avisos.append(f"{donde}: la serie {objetivo.codigo} se repite; se unió con la fila {objetivo.fila}")
            objetivo.tipos.extend(tipos)
            if ag is not None or ac is not None or disp:
                objetivo.ag, objetivo.ac, objetivo.disposicion = ag if ag is not None else objetivo.ag, ac if ac is not None else objetivo.ac, disp or objetivo.disposicion
            objetivo.soporte = soporte or objetivo.soporte
            objetivo.procedimiento = proc or objetivo.procedimiento
            objetivo.acceso = acceso if celda("acceso") is not None else objetivo.acceso
    libro.close()
    _verificar(r)
    return r


def _verificar(r: Resultado) -> None:
    """Hallazgos tipificados (como la verificación de hojas de GEOLOGY): errores impiden importar."""
    if not r.filas and not r.errores:
        r.errores.append({"ccd": "No se encontró un Cuadro de Clasificación: se esperan columnas de código y nombre de dependencia, serie y subserie",
                          "tvd": "No se encontró una tabla de TVD: se esperan columnas de serie o subserie y de disposición final"}.get(r.modo, "No se encontró una tabla de TRD: se esperan columnas de serie o subserie y de retención (AG/AC)"))
        return
    vistos: dict[str, Fila] = {}
    for f in r.filas:
        donde = f"Hoja «{f.hoja}», fila {f.fila} ({f.codigo})"
        if f.codigo in vistos:
            r.errores.append(f"{donde}: código repetido (ya está en la hoja «{vistos[f.codigo].hoja}», fila {vistos[f.codigo].fila})")
        vistos[f.codigo] = f
        if not f.dependencia:
            r.avisos.append(f"{donde}: la dependencia {f.codigo_dependencia} no tiene nombre; se usará el código")
        limpios = list(dict.fromkeys(t for t in f.tipos if t))
        if len(limpios) != len(f.tipos):
            r.correcciones.append(f"{donde}: se quitaron tipos documentales repetidos o vacíos")
        f.tipos = limpios
    padres = {f.codigo for f in r.filas if f.nivel == "serie"}
    con_hijas = {f.padre for f in r.filas if f.nivel == "subserie"}
    for f in r.filas:
        donde = f"Hoja «{f.hoja}», fila {f.fila} ({f.codigo})"
        if f.nivel == "subserie" and f.padre not in padres:
            r.errores.append(f"{donde}: la serie {f.padre} no aparece en la tabla")
        hoja = f.nivel == "subserie" or f.codigo not in con_hijas
        if not hoja:
            continue  # una serie con subseries no lleva tiempos propios: los llevan sus subseries
        if r.modo == "ccd":
            continue  # el CCD solo clasifica: los tiempos y la disposición se valoran después en la TRD
        if r.modo == "trd" and (f.ag is None or f.ac is None):
            r.errores.append(f"{donde}: faltan los tiempos de retención en archivo de gestión (AG) o central (AC)")
        if not f.disposicion:
            r.errores.append(f"{donde}: falta la disposición final (CT, E, S o M/D)")
        if not f.tipos:
            r.avisos.append(f"{donde}: no tiene tipos documentales; no se podrá clasificar documentos en ella hasta completarlos")
        if not f.soporte:
            f.soporte = "hibrido"
            r.correcciones.append(f"{donde}: sin soporte marcado; se registra híbrido (físico y electrónico)")
        if f.disposicion in ("S", "D", "E") and not f.procedimiento:
            r.avisos.append(f"{donde}: la disposición {f.disposicion} requiere describir el procedimiento (Acuerdo 001 de 2024)")
        if (f.ag or 0) + (f.ac or 0) == 0 and f.disposicion != "CT":
            r.avisos.append(f"{donde}: retención total de 0 años")




def plantilla(tipo: str = "TRD") -> bytes:
    """Libro de ejemplo en el formato tabular, con instrucciones. Los datos de ejemplo son ficticios."""
    libro = openpyxl.Workbook()
    h = libro.active
    h.title = tipo
    h.append(["Código dependencia", "Dependencia", "Código serie", "Serie", "Código subserie", "Subserie", "Tipos documentales", "AG", "AC", "CT", "E", "S", "M/D", "Soporte", "Acceso", "Procedimiento"])
    h.append(["100", "Dirección general", "100-02", "Actas", "100-02.01", "Actas de comité directivo", "Citación; Acta; Lista de asistencia", 2, 18, "X", "", "", "", "F/E", "Pública", "Conservación total por su valor histórico. Se digitaliza para consulta."])
    h.append(["100", "Dirección general", "100-05", "Decretos", "", "", "Decreto; Soportes", 2, 18, "X", "", "", "", "F/E", "Pública", "Conservación total."])
    h.append(["110", "Oficina jurídica", "110-05", "Acciones constitucionales", "110-05.01", "Acciones de tutela", "Tutela; Auto admisorio; Contestación; Fallo", 2, 8, "", "", "X", "", "E", "Clasificada", "Selección del 10 % de los expedientes por muestreo cualitativo."])
    for col, ancho in zip("ABCDEFGHIJKLMNOP", (12, 26, 13, 26, 14, 30, 44, 5, 5, 5, 5, 5, 6, 9, 12, 60), strict=True):
        h.column_dimensions[col].width = ancho
    ayuda = libro.create_sheet("Instrucciones")
    for linea in [
        "Una fila por serie o subserie. Si la serie tiene subseries, repita el código y nombre de la serie en cada fila de subserie.",
        "Tipos documentales: sepárelos con punto y coma (;) o con saltos de línea dentro de la celda.",
        "AG y AC: años de retención en archivo de gestión y central. Disposición: marque con X una de CT, E, S o M/D.",
        "Soporte: F (físico), E (electrónico) o F/E. Acceso: Pública, Clasificada o Reservada.",
        "También se acepta el formato oficial del AGN: una hoja por dependencia, con «Oficina productora» y «Código» en el encabezado.",
        "ARCA crea la versión en borrador: revísela y apruébela con el acto administrativo para que quede vigente.",
    ]:
        ayuda.append([linea])
    ayuda.column_dimensions["A"].width = 130
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()
