"""
Vacía el flujo de trabajo para volver a empezar el cargue desde cero.

BORRA todo lo que se ha trabajado: expedientes, trámites, hojas de control, bitácora, cajas
definitivas, archivos registrados y el consumo de los modelos.

NO BORRA lo que costó cargar y no depende del trabajo diario:
    · el inventario de origen, las 7.699 carpetas del contrato
    · las tablas de valoración documental, con sus periodos, series y subseries
    · el contexto de cada periodo
    · los usuarios y sus contraseñas

Los archivos digitalizados en disco tampoco se borran aquí: eso se hace a mano vaciando la
carpeta almacen, y se dice al final por si lo quiere.

Uso dentro de Docker:
    docker compose exec servidor python scripts/vaciar_flujo.py --simular   ver qué borraría
    docker compose exec servidor python scripts/vaciar_flujo.py --si        borrarlo de verdad
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geology.nucleo.bd import SesionLocal
from geology.modelos import Archivo, Caja, ConsumoModelo, Expediente, Tramite, Trazabilidad


def main() -> None:
    simular = "--simular" in sys.argv
    confirmado = "--si" in sys.argv

    db = SesionLocal()
    try:
        conteos = {
            "expedientes": db.query(Expediente).count(),
            "trámites": db.query(Tramite).count(),
            "renglones de bitácora": db.query(Trazabilidad).count(),
            "archivos registrados": db.query(Archivo).count(),
            "cajas definitivas": db.query(Caja).count(),
            "consumo de modelos": db.query(ConsumoModelo).count(),
        }
        print("Se va a borrar:")
        for que, cuantos in conteos.items():
            print(f"  {cuantos:>7}  {que}")

        from geology.modelos import Periodo, UnidadInventario, UsuarioBD
        print("\nSe conserva:")
        print(f"  {db.query(UnidadInventario).count():>7}  carpetas del inventario de origen")
        print(f"  {db.query(Periodo).count():>7}  periodos con sus tablas de valoración")
        print(f"  {db.query(UsuarioBD).count():>7}  usuarios con sus contraseñas")

        if simular or not confirmado:
            print("\nNo se borró nada.")
            print("Para hacerlo de verdad: python scripts/vaciar_flujo.py --si")
            return

        # El orden importa: primero lo que apunta a otra cosa.
        db.query(Trazabilidad).delete(synchronize_session=False)
        db.query(Tramite).delete(synchronize_session=False)
        db.query(Archivo).delete(synchronize_session=False)
        db.query(Expediente).delete(synchronize_session=False)
        db.query(Caja).delete(synchronize_session=False)
        db.query(ConsumoModelo).delete(synchronize_session=False)
        db.commit()

        print("\nFlujo vacío. El inventario, las tablas de valoración y los usuarios siguen ahí.")
        print("\nSi también quiere borrar los documentos digitalizados del disco, borre el")
        print("contenido de la carpeta almacen del proyecto. Si no, los archivos viejos quedan")
        print("ahí sin estorbar y se sobrescriben al volver a cargar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
