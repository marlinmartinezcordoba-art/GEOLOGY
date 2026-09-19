"""
Qué tabla de valoración documental tiene cargada cada periodo.

Sirve para responder de una vez la pregunta «la lista desplegable no está completa»: dice
cuántas filas hay por periodo, de cuántas oficinas productoras, y avisa cuando dos filas
traen los mismos códigos de serie y de subserie, que es cuando hay que mirar de qué oficina
es cada una.

Uso:  docker compose exec servidor python scripts/revisar_tvd.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geology.nucleo.bd import SesionLocal
from geology.modelos import Periodo, Seccion, Serie, Subserie


def main() -> None:
    db = SesionLocal()
    try:
        periodos = db.query(Periodo).order_by(Periodo.orden).all()
        if not periodos:
            print("No hay ningún periodo cargado. Ejecute scripts/cargar_inventario.py.")
            return

        print(f"{'PERIODO':>8}  {'FILAS':>5}  {'OFICINAS':>8}  {'SERIES':>6}  ESTADO")
        print("-" * 78)
        total = 0
        vacios = []
        for p in periodos:
            filas = (db.query(Seccion.codigo_dependencia, Serie.codigo, Subserie.codigo)
                       .select_from(Subserie)
                       .join(Serie, Subserie.serie_id == Serie.id)
                       .join(Seccion, Serie.seccion_id == Seccion.id)
                       .filter(Seccion.periodo_id == p.id).all())
            oficinas = {f[0] for f in filas}
            series = {f[1] for f in filas}
            repetidos = [k for k, v in Counter((f[1], f[2]) for f in filas).items() if v > 1]
            total += len(filas)
            if not filas:
                estado = "SIN TABLA. No se puede clasificar en este periodo."
                vacios.append(p.numero_romano)
            elif repetidos:
                estado = (f"{len(repetidos)} pareja(s) de códigos repetida(s) entre oficinas; "
                          "se distinguen por la oficina productora")
            else:
                estado = "completa"
            print(f"{p.numero_romano:>8}  {len(filas):>5}  {len(oficinas):>8}  {len(series):>6}  {estado}")

        print("-" * 78)
        print(f"{'TOTAL':>8}  {total:>5} filas de tabla de valoración cargadas.")
        if vacios:
            print()
            print("Periodos sin tabla: " + ", ".join(vacios))
            print("Cárguelos con:  docker compose exec servidor python scripts/cargar_inventario.py")
        else:
            print("Todos los periodos tienen tabla cargada.")

        print()
        print("Si en la pantalla ve renglones que parecen iguales, no son iguales: son la "
              "misma serie y subserie de dos oficinas productoras distintas, y por el "
              "principio de procedencia no son la misma clasificación. La lista los muestra "
              "con la oficina delante.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
