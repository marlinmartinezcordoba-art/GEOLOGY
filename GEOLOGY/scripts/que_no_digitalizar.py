"""
Qué carpetas NO hay que digitalizar, según la disposición final de la tabla convalidada.

Cruza el inventario de origen contra las subseries que la tabla marcó como ELIMINACIÓN y
como SELECCIÓN, y entrega la lista de candidatas para que una persona las verifique antes
de escanear nada.

POR QUÉ NO SE CRUZA POR LA COLUMNA DE SUBSERIE DEL INVENTARIO. Porque en este fondo no es de
fiar: hay más de mil carpetas rotuladas «ACTA COMITE DE PUBLICACION» cuyo asunto dice
«INFORMES DE ANALISIS DE LABORATORIO QUIMICO DE MUESTRAS». Quien decidiera qué eliminar
leyendo esa columna se equivocaría más de mil veces. El cruce se hace sobre el ASUNTO, que
sí describe lo que hay dentro.

ESTE PROGRAMA PROPONE, NO DECIDE. Eliminar un documento de archivo es irreversible, la
eliminación va avalada por el Comité, y quien responde por una eliminación indebida es la
archivista que firma, no un programa. Cada candidata sale con su puntaje, con las palabras
por las que coincidió y con el asunto completo, para que la verificación sea de verdad una
verificación y no un visto bueno a ciegas.

Uso, desde la carpeta del proyecto:

    docker compose exec servidor python scripts/que_no_digitalizar.py
    docker compose exec servidor python scripts/que_no_digitalizar.py --periodo XIV
    docker compose exec servidor python scripts/que_no_digitalizar.py --excel

El archivo queda en la carpeta «expedidos» del proyecto.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geology.nucleo.bd import SesionLocal                      # noqa: E402
from geology.dominio import disposicion as dp# noqa: E402


def principal() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--periodo", default="", help="solo un periodo, en romano")
    p.add_argument("--excel", action="store_true", help="además escribe el libro de trabajo")
    p.add_argument("--solo-fuertes", action="store_true",
                   help="únicamente las coincidencias inequívocas")
    args = p.parse_args()

    db = SesionLocal()
    try:
        candidatas, r = dp.revisar_todo(db, args.periodo)
        if args.solo_fuertes:
            candidatas = [c for c in candidatas if c.confianza == "fuerte"]

        print("QUÉ NO HAY QUE DIGITALIZAR\n" + "=" * 74)
        print(f"  Carpetas del inventario revisadas          {r['revisadas']:>8,}")
        if r["sin_periodo"]:
            print(f"  Sin periodo, no se pudieron cruzar         {r['sin_periodo']:>8,}")
        print()
        print(f"  Candidatas a ELIMINACIÓN                   {r['eliminacion']:>8,}"
              f"   ({r['eliminacion_fuerte']:,} inequívocas)")
        print(f"     folios que representan                  {r['eliminacion_folios']:>8,}")
        print(f"  Candidatas a SELECCIÓN                     {r['seleccion']:>8,}"
              f"   ({r['seleccion_fuerte']:,} inequívocas)")
        print(f"     folios que representan                  {r['seleccion_folios']:>8,}")
        print("-" * 74)
        print(f"  FOLIOS QUE PODRÍAN NO DIGITALIZARSE        "
              f"{r['folios_que_no_se_digitalizarian']:>8,}")
        if r["revisadas"]:
            print(f"  Es el {100 * r['candidatas'] / r['revisadas']:.0f}% de las carpetas "
                  "del inventario.")

        print("\nPOR SUBSERIE DE LA TABLA:")
        por_sub = Counter((c.disposicion, c.subserie_tvd) for c in candidatas)
        for (d, ss), n in por_sub.most_common(15):
            print(f"  [{d}] {n:5d}  {ss[:52]}")

        print("\nEJEMPLOS, para que vea con qué está cruzando:")
        for c in candidatas[:5]:
            print(f"  {c.codigo_carpeta} · P{c.periodo} · [{c.disposicion}] {c.confianza}")
            print(f"      {c.asunto[:86]}")
            print(f"      se parece a «{c.subserie_tvd}» por {', '.join(c.coincidencias)}")

        print("\n" + "=" * 74)
        print("ESTO ES UNA PROPUESTA, NO UNA DECISIÓN.")
        print("Verifique con la carpeta en la mano antes de excluir nada. Eliminar es")
        print("irreversible y la eliminación va avalada por el Comité.")
        print("Cuidado especialmente con las coincidencias «probables»: un LIBRO MAYOR no es")
        print("un libro auxiliar, aunque las dos cosas digan «libro» y «contable».")
        print("=" * 74)

        if args.excel:
            destino = _libro(candidatas, r, args.periodo)
            print(f"\nLibro de verificación: {destino}")
        else:
            print("\nPara el libro de verificación, agregue  --excel")
        return 0
    finally:
        db.close()


def _libro(candidatas: list, resumen: dict, periodo: str) -> Path:
    """El libro con el que se hace la verificación, con su columna para firmar."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    libro = Workbook()
    h = libro.active
    h.title = "Candidatas a no digitalizar"

    h["A1"] = "CARPETAS QUE PODRÍAN NO DIGITALIZARSE · propuesta para verificación"
    h["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFFFF")
    h["A1"].fill = PatternFill("solid", fgColor="FF12293F")
    h.merge_cells("A1:J1")
    h["A2"] = (f"Expedido el {date.today().isoformat()} por GEOLOGY cruzando el inventario de "
               "origen contra la disposición final de la tabla de valoración convalidada. "
               "ES UNA PROPUESTA: verifique cada carpeta antes de excluirla. Eliminar es "
               "irreversible y va avalado por el Comité.")
    h["A2"].font = Font(name="Arial", size=9)
    h["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    h.merge_cells("A2:J2")
    h.row_dimensions[2].height = 46

    rotulos = ["Carpeta", "Periodo", "Disposición", "Qué significa", "Confianza",
               "Folios", "Asunto del inventario", "Se parece a", "Coincide en",
               "VERIFICADO POR (firme aquí)"]
    for i, r in enumerate(rotulos, start=1):
        c = h.cell(4, i, r)
        c.fill = PatternFill("solid", fgColor="FF1B4A6B")
        c.font = Font(name="Arial", size=9, bold=True, color="FFFFFFFF")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for ancho, letra in zip((14, 8, 11, 34, 10, 8, 58, 34, 26, 26), "ABCDEFGHIJ"):
        h.column_dimensions[letra].width = ancho

    for i, c in enumerate(candidatas):
        fila = 5 + i
        valores = [c.codigo_carpeta, c.periodo, c.disposicion,
                   dp.QUE_SIGNIFICA.get(c.disposicion, ""), c.confianza, c.folios,
                   c.asunto, f"{c.serie_tvd} › {c.subserie_tvd}",
                   ", ".join(c.coincidencias), ""]
        for j, v in enumerate(valores, start=1):
            celda = h.cell(fila, j, v)
            celda.font = Font(name="Arial", size=8,
                              bold=(j == 3 and c.disposicion == dp.ELIMINACION))
            celda.alignment = Alignment(vertical="top", wrap_text=(j in (4, 7, 8, 9)))
        if c.disposicion == dp.ELIMINACION:
            h.cell(fila, 3).font = Font(name="Arial", size=8, bold=True, color="FF96173C")

    h.freeze_panes = "A5"
    h.auto_filter.ref = f"A4:{get_column_letter(len(rotulos))}{4 + len(candidatas)}"

    resumen_hoja = libro.create_sheet("Resumen")
    resumen_hoja["A1"] = "RESUMEN"
    resumen_hoja["A1"].font = Font(name="Arial", size=12, bold=True)
    etiquetas = {
        "revisadas": "Carpetas del inventario revisadas",
        "sin_periodo": "Sin periodo, no se pudieron cruzar",
        "eliminacion": "Candidatas a ELIMINACIÓN",
        "eliminacion_fuerte": "   de ellas, inequívocas",
        "eliminacion_folios": "   folios que representan",
        "seleccion": "Candidatas a SELECCIÓN",
        "seleccion_fuerte": "   de ellas, inequívocas",
        "seleccion_folios": "   folios que representan",
        "folios_que_no_se_digitalizarian": "FOLIOS QUE PODRÍAN NO DIGITALIZARSE",
    }
    for i, (clave, etiqueta) in enumerate(etiquetas.items(), start=3):
        resumen_hoja.cell(i, 1, etiqueta).font = Font(name="Arial", size=10,
                                                      bold=clave.startswith("folios_que"))
        resumen_hoja.cell(i, 2, resumen.get(clave, 0)).font = Font(
            name="Arial", size=10, bold=clave.startswith("folios_que"))
    resumen_hoja.column_dimensions["A"].width = 44
    resumen_hoja.column_dimensions["B"].width = 14

    sufijo = f"_periodo_{periodo.upper()}" if periodo else ""
    destino = Path(f"expedidos/Que_NO_digitalizar{sufijo}_{date.today().isoformat()}.xlsx")
    destino.parent.mkdir(parents=True, exist_ok=True)
    libro.save(destino)
    return destino


if __name__ == "__main__":
    raise SystemExit(principal())
