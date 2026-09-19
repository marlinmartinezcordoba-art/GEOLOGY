"""
Vuelve a expedir en los formatos oficiales del Servicio Geológico todo lo que ya está hecho.

No hay nada que rehacer a mano. Los datos de los expedientes están en la base, no dentro de
los archivos de Excel: lo que se diligenció con el formato anterior vuelve a salir aquí, con
la misma información, en las plantillas F-GDM-003, F-GDM-006, F-GDM-007 y F-GDM-008.

Antes de expedir completa, en las hojas ya revisadas, quién las revisó. El campo 15 del
formato pasó a ser el responsable de la REVISIÓN y esa columna nació vacía; el dato se toma
de la bitácora, del movimiento «revisar_hoja». Si un expediente no tiene ese movimiento, el
campo se deja en blanco: no se inventa una firma.

Uso, desde la carpeta del proyecto:

    docker compose exec servidor python scripts/reexpedir_formatos.py
    docker compose exec servidor python scripts/reexpedir_formatos.py --caja AH-CJ-00001
    docker compose exec servidor python scripts/reexpedir_formatos.py --periodo VI --por-pagina 2

Los archivos quedan en la carpeta «expedidos» del proyecto, que se ve desde Windows en
C:\\GEOLOGY\\expedidos.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geology.nucleo.bd import SesionLocal
from geology.dominio import expedir

RAIZ = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caja", help="solo esta caja definitiva, por ejemplo AH-CJ-00001")
    parser.add_argument("--periodo", help="solo este periodo, en número romano")
    parser.add_argument("--limite", type=int, default=0, help="cuántos expedientes como máximo")
    parser.add_argument("--por-pagina", type=int, default=4, dest="por_pagina",
                        help="rótulos de carpeta por hoja oficio: 1, 2 o 4")
    parser.add_argument("--salida", default=str(RAIZ / "expedidos"),
                        help="carpeta donde dejar los archivos")
    argumentos = parser.parse_args()

    db = SesionLocal()
    try:
        completados = expedir.completar_revisores(db)
        if completados:
            print(f"Se completó el responsable de la revisión en {completados} hoja(s), "
                  "tomándolo de la bitácora.")

        print("Expidiendo en los formatos oficiales del Servicio Geológico…")
        archivos = expedir.armar(db, argumentos.caja, argumentos.periodo,
                                    argumentos.limite or None, argumentos.por_pagina)
        if not archivos:
            print("No hay nada que expedir todavía: se necesitan expedientes con hoja de "
                  "control levantada.")
            return

        destino = Path(argumentos.salida) / f"formatos_oficiales_{date.today().isoformat()}"
        destino.mkdir(parents=True, exist_ok=True)
        for nombre, contenido in archivos.items():
            ruta = destino / nombre
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(contenido)

        hojas = sum(1 for n in archivos if n.startswith("hojas_de_control/"))
        rotulos = sum(1 for n in archivos if n.startswith("rotulos/"))
        inventarios = sum(1 for n in archivos if n.startswith("F-GDM-003"))
        print()
        print(f"  {hojas:>4} hoja(s) de control      F-GDM-007 versión 4")
        print(f"  {rotulos:>4} archivo(s) de rótulos  F-GDM-006 y F-GDM-008 versión 5")
        print(f"  {inventarios:>4} inventario(s)          F-GDM-003 versión 9")
        print()
        print(f"Quedaron en:  {destino}")
        print("Desde Windows: C:\\GEOLOGY\\expedidos")
        print()
        print("Imprima los rótulos al 100 por ciento, sin «ajustar a la página»: si la "
              "impresora los escala, dejan de coincidir con la caja y con la carpeta.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
