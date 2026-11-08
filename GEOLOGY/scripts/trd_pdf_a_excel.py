"""
Convierte una Tabla de Retención Documental (TRD) publicada en PDF al Excel con que
se carga al sistema.

Lee los PDF de la TRD (uno por oficina productora, formato F-A-DOC-09 del Ministerio de
Ambiente y Desarrollo Sostenible), reconstruye la jerarquía dependencia > serie > subserie
> tipo documental y escribe un libro con estas hojas:

  FICHA              Datos del instrumento, convenciones y resumen de la conversión.
  TRD                Una fila por tipo documental, con todos los datos de su serie o
                     subserie repetidos. Es la hoja para cargar.
  SERIES_SUBSERIES   Una fila por serie o subserie, con el mismo orden de columnas que la
                     TVD consolidada que ya usa el sistema (datos/TVD_CONSOLIDADA_SGC733.xlsx).
  CUADRO_CLASIFICACION  Series y subseries únicas del fondo, con las oficinas que las producen.
  DEPENDENCIAS       Oficinas productoras procesadas y sus conteos.
  OBSERVACIONES      Celdas que el PDF trae vacías o ambiguas y conviene revisar antes de cargar.

No inventa contenido: lo que el PDF no trae queda vacío y señalado en OBSERVACIONES.

Uso:
    pip install pdfplumber openpyxl
    python scripts/trd_pdf_a_excel.py <carpeta_con_pdf> <salida.xlsx> [--version "TRD V1 2017-2021"]
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import OrderedDict
from datetime import date
from pathlib import Path

import pdfplumber
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Columnas de la tabla del F-A-DOC-09, de izquierda a derecha.
C_DEP, C_SERIE, C_SUB, C_NOM_SERIE, C_NOM_SUB, C_TIPO, C_SOPORTE, C_AG, C_AC, C_CT, C_E, C_MT, C_S, C_PROC = range(14)

DISPOSICIONES = ((C_CT, "CT"), (C_E, "E"), (C_MT, "MT"), (C_S, "S"))

# Palabras sueltas que en algunos PDF aparecen como subtítulo de etapa dentro de la lista
# de tipos documentales (sin soporte). No son tipos documentales: se guardan como ETAPA.
ETAPAS = {"diseño", "implementación", "implementacion", "seguimiento", "evaluación", "evaluacion",
          "planeación", "planeacion", "ejecución", "ejecucion", "formulación", "formulacion"}


def limpiar(texto) -> str:
    if texto is None:
        return ""
    t = str(texto).replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip()
    # Guion partido por un salto de línea del PDF («P-A- DOC-05» → «P-A-DOC-05»).
    t = re.sub(r"(?<=\w)- (?=[A-ZÁÉÍÓÚ])", "-", t)
    t = re.sub(r"\.\s+\.$", ".", t)
    return t


def entero(texto: str):
    """Los tiempos de retención se cargan como número cuando el PDF trae solo dígitos."""
    t = limpiar(texto)
    return int(t) if t.isdigit() else t


def soporte_normalizado(texto: str) -> str:
    t = limpiar(texto)
    if not t:
        return ""
    bajo = t.lower()
    fisico = "físico" in bajo or "fisico" in bajo
    electronico = "electr" in bajo
    if fisico and electronico:
        return "Físico - Electrónico"
    if fisico:
        return "Físico"
    if electronico:
        return "Electrónico"
    return t[0].upper() + t[1:]


def leer_encabezado(filas: list[list]) -> dict:
    """Fondo, unidad administrativa, oficina productora, versión, vigencia y código del formato."""
    datos = {}
    for fila in filas:
        celdas = [limpiar(c) for c in fila]
        texto = " ".join(c for c in celdas if c)
        etiqueta = celdas[0].upper()
        valor = next((c for c in celdas[1:] if c), "")
        if etiqueta == "FONDO":
            datos["fondo"] = valor
        elif etiqueta.startswith("SECCIÓN") or etiqueta.startswith("SECCION"):
            datos["unidad_administrativa"] = valor
        elif etiqueta.startswith("SUBSECCIÓN") or etiqueta.startswith("SUBSECCION"):
            datos["oficina_productora"] = valor
        m = re.search(r"Versi[oó]n:\s*(\S+)", texto)
        if m:
            datos["version_formato"] = m.group(1)
        m = re.search(r"Vigencia:\s*(\S+)", texto)
        if m:
            datos["vigencia_formato"] = m.group(1)
        m = re.search(r"C[oó]digo:\s*(\S+)", texto)
        if m:
            datos["codigo_formato"] = m.group(1)
    return datos


def es_fila_de_datos(fila: list) -> bool:
    """Una fila de la tabla trae un código de dependencia numérico o solo un tipo documental."""
    if len(fila) != 14:
        return False
    dep = limpiar(fila[C_DEP])
    tipo = limpiar(fila[C_TIPO])
    if dep.isdigit():
        return True
    # Fila de continuación: sin códigos ni nombres de serie, con tipo documental.
    return (not dep and not limpiar(fila[C_NOM_SERIE]) and tipo
            and tipo.upper() != "TIPOS DOCUMENTALES")


def procesar_pdf(ruta: Path, observaciones: list[dict]) -> tuple[dict, list[dict]]:
    """Devuelve el encabezado de la oficina y la lista de agrupaciones (series o subseries),
    cada una con sus tipos documentales."""
    agrupaciones: list[dict] = []
    encabezado: dict = {}
    actual: dict | None = None
    etapa = ""

    with pdfplumber.open(ruta) as pdf:
        encabezado["paginas"] = len(pdf.pages)
        for num_pagina, pagina in enumerate(pdf.pages, start=1):
            for tabla in pagina.extract_tables():
                filas_datos = [f for f in tabla if es_fila_de_datos(f)]
                if not encabezado or "oficina_productora" not in encabezado:
                    encabezado.update(leer_encabezado([f for f in tabla if not es_fila_de_datos(f)]))
                for fila in filas_datos:
                    dep = limpiar(fila[C_DEP])
                    if dep.isdigit():
                        marcas = [d for idx, d in DISPOSICIONES if limpiar(fila[idx]).upper() == "X"]
                        actual = {
                            "cod_dependencia": dep,
                            "cod_serie": limpiar(fila[C_SERIE]),
                            "cod_subserie": limpiar(fila[C_SUB]),
                            "serie": limpiar(fila[C_NOM_SERIE]),
                            "subserie": limpiar(fila[C_NOM_SUB]),
                            "ag": entero(fila[C_AG]),
                            "ac": entero(fila[C_AC]),
                            "marcas": marcas,
                            "disposicion": "+".join(marcas),
                            "procedimiento": limpiar(fila[C_PROC]),
                            "pagina": num_pagina,
                            "archivo": ruta.name,
                            "tipos": [],
                        }
                        etapa = ""
                        agrupaciones.append(actual)
                        if not marcas:
                            observaciones.append(_obs(ruta, num_pagina, actual, "", "La agrupación no tiene marcada ninguna disposición final en el PDF."))
                        if actual["ag"] == "" or actual["ac"] == "":
                            observaciones.append(_obs(ruta, num_pagina, actual, "", "Falta un tiempo de retención (AG o AC) en el PDF."))
                        if not actual["procedimiento"]:
                            observaciones.append(_obs(ruta, num_pagina, actual, "", "La agrupación no trae procedimiento en el PDF."))
                    if actual is None:
                        observaciones.append({"archivo": ruta.name, "pagina": num_pagina, "cod_dependencia": "",
                                              "codigo": "", "agrupacion": "", "tipo_documental": limpiar(fila[C_TIPO]),
                                              "observacion": "Tipo documental antes de la primera serie: no se pudo asignar."})
                        continue
                    tipo = limpiar(fila[C_TIPO])
                    soporte = limpiar(fila[C_SOPORTE])
                    if not tipo:
                        continue
                    if not soporte and tipo.lower() in ETAPAS:
                        etapa = tipo
                        continue
                    registro = {"tipo": tipo, "soporte_original": soporte,
                                "soporte": soporte_normalizado(soporte), "etapa": etapa, "pagina": num_pagina}
                    actual["tipos"].append(registro)
                    if not soporte:
                        observaciones.append(_obs(ruta, num_pagina, actual, tipo, "El tipo documental no trae soporte en el PDF."))
    return encabezado, agrupaciones


def _obs(ruta: Path, pagina: int, agr: dict, tipo: str, texto: str) -> dict:
    codigo = ".".join(c for c in (agr["cod_dependencia"], agr["cod_serie"], agr["cod_subserie"]) if c)
    return {"archivo": ruta.name, "pagina": pagina, "cod_dependencia": agr["cod_dependencia"],
            "codigo": codigo, "agrupacion": agr["subserie"] or agr["serie"], "tipo_documental": tipo,
            "observacion": texto}


# ---------------------------------------------------------------- escritura del Excel

AZUL = "1F3864"
GRIS = "F2F2F2"
borde = Border(*(Side(style="thin", color="BFBFBF"),) * 4)


def escribir_hoja(ws, titulo: str, columnas: list[tuple[str, int]], filas: list[list], envolver: set[str] = frozenset()):
    ws.append([titulo])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(columnas))
    ws["A1"].font = Font(bold=True, size=12, color=AZUL)
    ws.append([c for c, _ in columnas])
    for j, (nombre, ancho) in enumerate(columnas, start=1):
        celda = ws.cell(row=2, column=j)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor=AZUL)
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        celda.border = borde
        ws.column_dimensions[get_column_letter(j)].width = ancho
    ws.row_dimensions[2].height = 32
    for fila in filas:
        ws.append(fila)
    for r in ws.iter_rows(min_row=3, max_row=ws.max_row, max_col=len(columnas)):
        for celda in r:
            nombre = columnas[celda.column - 1][0]
            celda.border = borde
            celda.alignment = Alignment(vertical="top", wrap_text=nombre in envolver,
                                        horizontal="center" if nombre.startswith("COD") or nombre in ("CT", "E", "MT", "S", "RETENCIÓN AG", "RETENCIÓN AC", "PÁGINA", "N TIPOS") else "left")
    ws.freeze_panes = "A3"
    if filas:
        ws.auto_filter.ref = f"A2:{get_column_letter(len(columnas))}{ws.max_row}"


def construir_excel(resultados: list[tuple[dict, list[dict]]], observaciones: list[dict], salida: Path, version: str, fuente: str):
    wb = Workbook()
    fondo = next((e.get("fondo") for e, _ in resultados if e.get("fondo")), "")
    entidad = fondo.title() if fondo else ""

    # ---- TRD: una fila por tipo documental
    filas_trd, filas_ss, filas_dep = [], [], []
    ccd: OrderedDict[tuple, dict] = OrderedDict()
    n = 0
    for encabezado, agrupaciones in resultados:
        ua = encabezado.get("unidad_administrativa", "")
        op = encabezado.get("oficina_productora", "")
        n_sub = sum(1 for a in agrupaciones if a["cod_subserie"])
        n_tipos_dep = 0
        for a in agrupaciones:
            soportes = sorted({t["soporte"] for t in a["tipos"] if t["soporte"]})
            nivel = "Subserie" if a["cod_subserie"] else "Serie"
            codigo = ".".join(c for c in (a["cod_dependencia"], a["cod_serie"], a["cod_subserie"]) if c)
            filas_ss.append([version, entidad, ua, op, a["cod_dependencia"], a["cod_serie"], a["serie"],
                             a["cod_subserie"], a["subserie"], nivel, codigo, " / ".join(soportes),
                             a["ag"], a["ac"], a["disposicion"], a["procedimiento"], len(a["tipos"]),
                             a["archivo"], a["pagina"]])
            llave = (a["cod_serie"], a["cod_subserie"])
            entrada = ccd.setdefault(llave, {"serie": a["serie"], "subserie": a["subserie"], "oficinas": [], "disp": set(), "ret": set()})
            entrada["oficinas"].append(a["cod_dependencia"])
            entrada["disp"].add(a["disposicion"])
            entrada["ret"].add(f"{a['ag']}+{a['ac']}")
            for t in a["tipos"]:
                n += 1
                n_tipos_dep += 1
                filas_trd.append([n, version, ua, op, a["cod_dependencia"], a["cod_serie"], a["serie"],
                                  a["cod_subserie"], a["subserie"], codigo, t["etapa"], t["tipo"], t["soporte"],
                                  a["ag"], a["ac"],
                                  *["X" if m in a["marcas"] else "" for _, m in DISPOSICIONES],
                                  a["disposicion"], a["procedimiento"], a["archivo"], t["pagina"]])
        filas_dep.append([agrupaciones[0]["cod_dependencia"] if agrupaciones else "", ua, op,
                          sum(1 for a in agrupaciones if not a["cod_subserie"]), n_sub, n_tipos_dep,
                          agrupaciones[0]["archivo"] if agrupaciones else "", encabezado.get("paginas", 0)])

    ws = wb.active
    ws.title = "FICHA"
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 110
    filas_ficha = [
        ("TABLA DE RETENCIÓN DOCUMENTAL", ""),
        ("Fondo", fondo),
        ("Versión de la TRD", version),
        ("Formato de origen", " · ".join(f"{k}: {v}" for k, v in (("Código", resultados[0][0].get("codigo_formato", "")), ("Versión", resultados[0][0].get("version_formato", "")), ("Vigencia", resultados[0][0].get("vigencia_formato", ""))) if v)),
        ("Fuente", fuente),
        ("Fecha de conversión", date.today().isoformat()),
        ("", ""),
        ("Oficinas productoras procesadas", str(len(resultados))),
        ("Series y subseries", str(len(filas_ss))),
        ("Tipos documentales", str(len(filas_trd))),
        ("Observaciones para revisar", str(len(observaciones))),
        ("", ""),
        ("Convenciones de disposición final", "CT = Conservación Total · E = Eliminación · MT = Medio Técnico · S = Selección. La columna DISPOSICIÓN FINAL une con «+» las marcas X del PDF (por ejemplo CT+MT)."),
        ("Tiempos de retención", "En años. AG = Archivo de Gestión · AC = Archivo Central."),
        ("Soporte", "Se transcribe el del PDF, unificando la escritura: Físico · Electrónico · Físico - Electrónico."),
        ("Etapa", "Algunas subseries listan sus tipos documentales agrupados por etapa (Diseño, Implementación, Seguimiento, Evaluación). La etapa se conserva en su columna y no se cuenta como tipo documental."),
        ("Códigos", "Se conservan como texto, con sus ceros a la izquierda, tal como figuran en el PDF. CÓDIGO COMPLETO = dependencia.serie.subserie."),
        ("Hoja para cargar", "TRD (una fila por tipo documental). SERIES_SUBSERIES sigue el orden de columnas de la TVD consolidada del sistema."),
    ]
    for etiqueta, valor in filas_ficha:
        ws.append([etiqueta, valor])
    ws["A1"].font = Font(bold=True, size=13, color=AZUL)
    for fila in ws.iter_rows(min_row=2, max_row=ws.max_row):
        fila[0].font = Font(bold=True)
        fila[1].alignment = Alignment(wrap_text=True, vertical="top")
        fila[0].alignment = Alignment(vertical="top")

    columnas_trd = [("N°", 6), ("VERSIÓN TRD", 16), ("UNIDAD ADMINISTRATIVA", 30), ("OFICINA PRODUCTORA", 34),
                    ("COD DEPENDENCIA", 12), ("COD SERIE", 9), ("SERIE", 28), ("COD SUBSERIE", 11), ("SUBSERIE", 40),
                    ("CÓDIGO COMPLETO", 14), ("ETAPA", 14), ("TIPO DOCUMENTAL", 52), ("SOPORTE", 18),
                    ("RETENCIÓN AG", 10), ("RETENCIÓN AC", 10), ("CT", 5), ("E", 5), ("MT", 5), ("S", 5),
                    ("DISPOSICIÓN FINAL", 12), ("PROCEDIMIENTO", 90), ("ARCHIVO FUENTE", 36), ("PÁGINA", 8)]
    escribir_hoja(wb.create_sheet("TRD"), f"TABLA DE RETENCIÓN DOCUMENTAL · {fondo} · {version} · una fila por tipo documental",
                  columnas_trd, filas_trd, envolver={"PROCEDIMIENTO", "TIPO DOCUMENTAL", "SUBSERIE", "SERIE"})

    columnas_ss = [("VERSIÓN TRD", 16), ("ENTIDAD PRODUCTORA", 36), ("UNIDAD ADMINISTRATIVA", 30), ("OFICINA PRODUCTORA", 34),
                   ("COD DEPENDENCIA", 12), ("COD SERIE", 9), ("SERIE", 30), ("COD SUBSERIE", 11), ("SUBSERIE", 44),
                   ("NIVEL", 10), ("CÓDIGO COMPLETO", 14), ("SOPORTE", 26), ("RETENCIÓN AG", 10), ("RETENCIÓN AC", 10),
                   ("DISPOSICIÓN FINAL", 12), ("PROCEDIMIENTO", 90), ("N TIPOS", 8), ("ARCHIVO FUENTE", 36), ("PÁGINA", 8)]
    escribir_hoja(wb.create_sheet("SERIES_SUBSERIES"), f"SERIES Y SUBSERIES · {fondo} · {version}",
                  columnas_ss, filas_ss, envolver={"PROCEDIMIENTO", "SUBSERIE", "SERIE"})

    filas_ccd = []
    for (cs, css), e in sorted(ccd.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        filas_ccd.append([cs, e["serie"], css, e["subserie"], "Subserie" if css else "Serie",
                          ", ".join(sorted(set(e["oficinas"]))), len(set(e["oficinas"])),
                          " | ".join(sorted(e["disp"])), " | ".join(sorted(e["ret"])),
                          "Sí" if len(e["disp"]) > 1 or len(e["ret"]) > 1 else ""])
    columnas_ccd = [("COD SERIE", 9), ("SERIE", 34), ("COD SUBSERIE", 11), ("SUBSERIE", 50), ("NIVEL", 10),
                    ("OFICINAS PRODUCTORAS (COD)", 30), ("N OFICINAS", 9), ("DISPOSICIÓN FINAL", 16),
                    ("RETENCIÓN AG+AC", 16), ("DIFIERE ENTRE OFICINAS", 12)]
    escribir_hoja(wb.create_sheet("CUADRO_CLASIFICACION"), f"SERIES Y SUBSERIES ÚNICAS DEL FONDO (en las oficinas procesadas) · {version}",
                  columnas_ccd, filas_ccd, envolver={"SUBSERIE", "SERIE"})

    columnas_dep = [("COD DEPENDENCIA", 12), ("UNIDAD ADMINISTRATIVA", 36), ("OFICINA PRODUCTORA", 44),
                    ("SERIES SIN SUBSERIE", 12), ("SUBSERIES", 10), ("TIPOS DOCUMENTALES", 12), ("ARCHIVO FUENTE", 44), ("PÁGINAS", 8)]
    escribir_hoja(wb.create_sheet("DEPENDENCIAS"), f"OFICINAS PRODUCTORAS PROCESADAS · {version}", columnas_dep, filas_dep)

    columnas_obs = [("ARCHIVO FUENTE", 44), ("PÁGINA", 8), ("COD DEPENDENCIA", 12), ("CÓDIGO", 14),
                    ("SERIE / SUBSERIE", 44), ("TIPO DOCUMENTAL", 44), ("OBSERVACIÓN", 70)]
    escribir_hoja(wb.create_sheet("OBSERVACIONES"), "CELDAS QUE EL PDF TRAE VACÍAS O AMBIGUAS · revisar antes de cargar",
                  columnas_obs, [[o["archivo"], o["pagina"], o["cod_dependencia"], o["codigo"], o["agrupacion"],
                                  o["tipo_documental"], o["observacion"]] for o in observaciones],
                  envolver={"OBSERVACIÓN", "SERIE / SUBSERIE", "TIPO DOCUMENTAL"})

    salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(salida)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpeta", type=Path, help="Carpeta con los PDF de la TRD (uno por oficina productora)")
    ap.add_argument("salida", type=Path, help="Ruta del Excel a generar")
    ap.add_argument("--version", default="", help="Etiqueta de la versión de la TRD, p. ej. «TRD V1 2017-2021»")
    ap.add_argument("--fuente", default="", help="De dónde salieron los PDF (carpeta, enlace), para la ficha")
    args = ap.parse_args()

    pdfs = sorted(args.carpeta.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No hay PDF en {args.carpeta}")
    observaciones: list[dict] = []
    resultados = []
    for ruta in pdfs:
        encabezado, agrupaciones = procesar_pdf(ruta, observaciones)
        n_tipos = sum(len(a["tipos"]) for a in agrupaciones)
        print(f"{ruta.name}: {encabezado.get('oficina_productora', '?')} · {len(agrupaciones)} series/subseries · {n_tipos} tipos")
        if not agrupaciones:
            observaciones.append({"archivo": ruta.name, "pagina": 0, "cod_dependencia": "", "codigo": "",
                                  "agrupacion": "", "tipo_documental": "", "observacion": "No se reconoció ninguna fila de la tabla."})
        resultados.append((encabezado, agrupaciones))
    construir_excel(resultados, observaciones, args.salida, args.version, args.fuente or str(args.carpeta))
    print(f"\nExcel generado: {args.salida}  ·  {len(observaciones)} observaciones para revisar")


if __name__ == "__main__":
    main()
