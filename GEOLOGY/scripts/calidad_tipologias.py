"""
Calidad de la columna «tipo documental» de las hojas de control.

Trabaja en dos tiempos, y esa es toda la idea: primero PROPONE, y solo después, cuando usted
ya marcó en el archivo lo que acepta, APLICA. Ninguna hoja se toca sin que alguien lo haya
visto y lo haya marcado.

    docker compose exec servidor python scripts/calidad_tipologias.py
        Mira lo que hay y escribe el libro de propuestas en la carpeta «expedidos».

    (usted abre el libro y escribe SI en la columna APLICAR de los grupos que acepta)

    docker compose exec servidor python scripts/calidad_tipologias.py --aplicar expedidos/<archivo>.xlsx
        Cambia únicamente los grupos marcados con SI, y deja constancia en la bitácora.

QUÉ SE TOCA Y QUÉ NO. Solo la parte del tipo que está ANTES del separador. El detalle del
trámite —las muestras, el yacimiento, el municipio— no se toca ni una letra: ahí está lo que
distingue un trámite de otro y lo que de verdad sirve para buscar.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geology.nucleo.bd import SesionLocal                      # noqa: E402
from geology.dominio import tipologias as tp# noqa: E402

ENCABEZADOS = ["APLICAR", "Forma propuesta", "Trámites", "Por cambiar",
               "Variantes que hay hoy", "De dónde sale", "Subserie"]


def _datos(db):
    """Los trámites con su carpeta y la subserie de la tabla a la que pertenece cada una."""
    from geology.modelos import Expediente, Serie, Subserie, Tramite

    subseries = {s.id: s for s in db.query(Subserie).all()}
    series = {s.id: s for s in db.query(Serie).all()}
    expedientes = {e.id: e for e in db.query(Expediente).all()}

    por_carpeta = {}
    for e in expedientes.values():
        sub = subseries.get(e.subserie_id)
        if sub:
            serie = series.get(sub.serie_id)
            por_carpeta[e.codigo_carpeta] = (f"{serie.nombre} › {sub.nombre}" if serie
                                             else sub.nombre)

    tramites = []
    for t in db.query(Tramite).all():
        e = expedientes.get(t.expediente_id)
        if e and (t.tipo_documental or "").strip():
            tramites.append((e.codigo_carpeta, t.no_item, t.tipo_documental))
    return tramites, por_carpeta


def principal() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--aplicar", default="", metavar="ARCHIVO",
                   help="aplica los grupos marcados con SI en ese libro")
    p.add_argument("--salida", default="", help="dónde escribir el libro de propuestas")
    args = p.parse_args()

    db = SesionLocal()
    try:
        if args.aplicar:
            return _aplicar(db, Path(args.aplicar))

        tramites, por_carpeta = _datos(db)
        if not tramites:
            print("Todavía no hay trámites con tipo documental.")
            return 0

        grupos = tp.agrupar(tramites, por_carpeta)
        reparos = tp.reparos(tramites)
        por_cambiar = sum(g.hay_que_cambiar for g in grupos)

        print("CALIDAD DE LOS TIPOS DOCUMENTALES\n" + "=" * 74)
        print(f"  Trámites revisados                      {len(tramites):>8,}")
        print(f"  Tipos documentales distintos            {len(grupos):>8,}")
        print(f"  Trámites que quedarían mejor escritos   {por_cambiar:>8,}")
        print(f"  Reparos de fondo (no de escritura)      {len(reparos):>8,}")

        con_variantes = [g for g in grupos if len(g.variantes) > 1]
        if con_variantes:
            print(f"\nEL MISMO TIPO ESCRITO DE VARIAS MANERAS ({len(con_variantes)} caso(s)):")
            for g in con_variantes[:10]:
                print(f"\n  → «{g.propuesta}»   ({g.veces} trámite(s))")
                for v in g.variantes:
                    marca = "  =" if v.texto == g.propuesta else "  ≠"
                    print(f"     {marca} {v.veces:5d} × «{v.texto}»")
                print(f"        {g.porque}")

        solos = [g for g in grupos if len(g.variantes) == 1 and g.hay_que_cambiar]
        if solos:
            print(f"\nSOLO CORRECCIÓN DE ESCRITURA ({len(solos)} tipo(s)):")
            for g in solos[:8]:
                print(f"   «{g.variantes[0].texto}»")
                print(f"      → «{g.propuesta}»")

        if reparos:
            print(f"\nREPAROS DE FONDO — estos no los arregla el programa ({len(reparos)}):")
            for r in reparos[:6]:
                print(f"   {r.carpeta} trámite {r.no_item}: {r.problema}")
                print(f"      dice: {r.que_dice[:82]}")
                print(f"      → {r.que_hacer}")

        destino = Path(args.salida or
                       f"expedidos/Calidad_tipologias_{date.today().isoformat()}.xlsx")
        _libro(grupos, reparos, destino)
        print("\n" + "=" * 74)
        print(f"Libro de propuestas: {destino}")
        print("Ábralo, escriba SI en la columna APLICAR de los grupos que acepte, guárdelo, y")
        print(f"después corra:  python scripts/calidad_tipologias.py --aplicar {destino}")
        print("Los que deje en blanco NO se tocan.")
        return 0
    finally:
        db.close()


def _libro(grupos, reparos, destino: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    libro = Workbook()
    h = libro.active
    h.title = "Propuestas"
    h["A1"] = "UNIFICACIÓN DE TIPOS DOCUMENTALES · escriba SI en APLICAR para aceptar"
    h["A1"].font = Font(name="Arial", size=12, bold=True, color="FFFFFFFF")
    h["A1"].fill = PatternFill("solid", fgColor="FF12293F")
    h.merge_cells("A1:G1")
    h["A2"] = ("Solo se cambia la parte del tipo que va ANTES del separador. El detalle del "
               "trámite —muestras, yacimiento, municipio— no se toca. Lo que deje en blanco "
               "en APLICAR no se modifica.")
    h["A2"].font = Font(name="Arial", size=9)
    h["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    h.merge_cells("A2:G2")
    h.row_dimensions[2].height = 32

    for i, r in enumerate(ENCABEZADOS, start=1):
        c = h.cell(4, i, r)
        c.fill = PatternFill("solid", fgColor="FF1B4A6B")
        c.font = Font(name="Arial", size=9, bold=True, color="FFFFFFFF")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for ancho, letra in zip((10, 42, 10, 12, 62, 46, 34), "ABCDEFG"):
        h.column_dimensions[letra].width = ancho

    for i, g in enumerate(g for g in grupos if g.hay_que_cambiar):
        fila = 5 + i
        variantes = " | ".join(f"{v.veces}× {v.texto}" for v in g.variantes)
        for j, v in enumerate(["", g.propuesta, g.veces, g.hay_que_cambiar,
                               variantes, g.porque, g.subserie], start=1):
            c = h.cell(fila, j, v)
            c.font = Font(name="Arial", size=9, bold=(j == 2))
            c.alignment = Alignment(vertical="top", wrap_text=(j in (5, 6, 7)))
        h.cell(fila, 1).fill = PatternFill("solid", fgColor="FFFDF3DE")
    h.freeze_panes = "A5"

    if reparos:
        r2 = libro.create_sheet("Reparos de fondo")
        r2["A1"] = "ESTOS NO LOS ARREGLA EL PROGRAMA · hay que corregirlos en la hoja"
        r2["A1"].font = Font(name="Arial", size=11, bold=True, color="FFFFFFFF")
        r2["A1"].fill = PatternFill("solid", fgColor="FF96173C")
        r2.merge_cells("A1:E1")
        for i, rot in enumerate(["Carpeta", "Trámite", "Qué dice", "Problema", "Qué hacer"], 1):
            c = r2.cell(3, i, rot)
            c.font = Font(name="Arial", size=9, bold=True, color="FFFFFFFF")
            c.fill = PatternFill("solid", fgColor="FF1B4A6B")
        for ancho, letra in zip((14, 9, 60, 46, 62), "ABCDE"):
            r2.column_dimensions[letra].width = ancho
        for i, x in enumerate(reparos):
            for j, v in enumerate([x.carpeta, x.no_item, x.que_dice, x.problema, x.que_hacer], 1):
                c = r2.cell(4 + i, j, v)
                c.font = Font(name="Arial", size=9)
                c.alignment = Alignment(vertical="top", wrap_text=(j in (3, 4, 5)))
        r2.freeze_panes = "A4"

    destino.parent.mkdir(parents=True, exist_ok=True)
    libro.save(destino)


def _aplicar(db, archivo: Path) -> int:
    """Cambia únicamente los grupos que la persona marcó con SI."""
    import openpyxl

    from geology.modelos import Expediente, Tramite, Trazabilidad

    if not archivo.exists():
        print(f"No existe {archivo}.")
        return 1
    hoja = openpyxl.load_workbook(archivo, data_only=True)["Propuestas"]

    aceptados = {}
    for fila in hoja.iter_rows(min_row=5, values_only=True):
        if not fila or not fila[1]:
            continue
        marca = str(fila[0] or "").strip().upper()
        if marca in ("SI", "SÍ", "S", "X", "1", "OK"):
            aceptados[str(fila[1]).strip()] = str(fila[4] or "")
    if not aceptados:
        print("No hay ningún grupo marcado con SI en la columna APLICAR. No se cambió nada.")
        return 0

    tramites, por_carpeta = _datos(db)
    grupos = {g.propuesta: g for g in tp.agrupar(tramites, por_carpeta)}

    filas = {t.id: t for t in db.query(Tramite).all()}
    expedientes = {e.id: e for e in db.query(Expediente).all()}
    por_carpeta_item = {}
    for t in filas.values():
        e = expedientes.get(t.expediente_id)
        if e:
            por_carpeta_item[(e.codigo_carpeta, t.no_item)] = t

    cambiados, tocadas = 0, set()
    for propuesta in aceptados:
        g = grupos.get(propuesta)
        if not g:
            print(f"  (ya no existe el grupo «{propuesta}»; se omite)")
            continue
        for v in g.variantes:
            if v.texto == g.propuesta:
                continue
            for carpeta, no_item in v.tramites:
                t = por_carpeta_item.get((carpeta, no_item))
                if not t:
                    continue
                cabeza, detalle = tp.partir(t.tipo_documental or "")
                t.tipo_documental = f"{g.propuesta} - {detalle}" if detalle else g.propuesta
                cambiados += 1
                tocadas.add(t.expediente_id)

    for expediente_id in tocadas:
        db.add(Trazabilidad(
            expediente_id=expediente_id, estado_anterior=expedientes[expediente_id].estado,
            estado_nuevo=expedientes[expediente_id].estado, accion="calidad_tipologias",
            usuario="calidad_tipologias",
            motivo=("Se unificó la escritura del tipo documental en los trámites de este "
                    "expediente, con la forma aprobada en el libro de propuestas. El detalle "
                    "de cada trámite no se modificó.")))
    db.commit()
    print(f"{cambiados} trámite(s) unificados en {len(tocadas)} expediente(s).")
    print("Queda anotado en la bitácora de cada uno.")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
