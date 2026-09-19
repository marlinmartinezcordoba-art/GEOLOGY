"""
Carga el contexto por periodo, que es lo que da calidad a todas las descripciones.

Los tres textos (historia institucional 3.2.2, historia archivística 3.2.3 y características
físicas 3.4.4) se escriben una sola vez por periodo y cada expediente los hereda, tal como
pide la norma al no repetir información entre niveles. Sin esto, esos elementos salen
vacíos o genéricos en cada descripción.

Uso:  docker compose exec servidor python scripts/cargar_contexto.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl

from geology.nucleo.bd import SesionLocal, crear_tablas
from geology.modelos import Periodo

ARCHIVO = Path(__file__).resolve().parent.parent / "datos" / "CONTEXTO_PERIODOS.xlsx"


def main() -> None:
    crear_tablas()
    if not ARCHIVO.exists():
        print(f"ERROR. No se encontró {ARCHIVO.name} en la carpeta datos.")
        return
    hoja = openpyxl.load_workbook(ARCHIVO, read_only=True, data_only=True).worksheets[0]
    filas = hoja.iter_rows(values_only=True)
    next(filas)                      # encabezado

    db = SesionLocal()
    try:
        puestos, faltantes = 0, []
        for fila in filas:
            if not fila or not fila[0]:
                continue
            romano = str(fila[0]).strip().upper()
            periodo = db.query(Periodo).filter(Periodo.numero_romano == romano).first()
            if not periodo:
                faltantes.append(romano)
                continue
            periodo.historia_institucional = (fila[1] or "").strip() or None
            periodo.historia_archivistica = (fila[2] or "").strip() or None
            periodo.caracteristicas_fisicas = (fila[3] or "").strip() or None
            puestos += 1
        db.commit()

        sin_contexto = [p.numero_romano for p in db.query(Periodo).order_by(Periodo.orden).all()
                        if not p.historia_institucional]
        print(f"Contexto cargado en {puestos} periodos.")
        if faltantes:
            print(f"AVISO. Estos periodos del archivo no existen en la base: {', '.join(faltantes)}.")
        if sin_contexto:
            print(f"PENDIENTE. Estos periodos quedaron sin contexto y sus descripciones saldrán "
                  f"con esos elementos vacíos: {', '.join(sin_contexto)}.")
        else:
            print("Todos los periodos tienen su contexto.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
