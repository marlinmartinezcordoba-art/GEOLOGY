"""
Retira los expedientes cuyo documento digitalizado ya no está en el almacén.

Un «fantasma» es un expediente con registro de archivo en la base pero sin el archivo en
disco. Suele quedar cuando una carga se interrumpió o cuando se reinstaló la plataforma sin
conservar el almacén. Mientras exista, el expediente se queda en Devuelto y no hay forma de
sacarlo de ahí desde la interfaz.

Este programa los retira para que la carpeta se pueda volver a cargar limpia.

NO toca:
    · expedientes con descripción hecha, validada, aprobada o en inventario de salida
    · expedientes cuyo archivo sí está en el almacén
    · nada del inventario de origen, ni las tablas de valoración, ni los usuarios

Uso dentro de Docker:
    docker compose exec servidor python scripts/limpiar_fantasmas.py --simular   ver qué haría
    docker compose exec servidor python scripts/limpiar_fantasmas.py             hacerlo
    docker compose exec servidor python scripts/limpiar_fantasmas.py AC-CP-00891 solo esa
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geology.nucleo.bd import SesionLocal
from geology.modelos import Archivo, Expediente
from geology.dominio.estados import Estado

# Solo se retiran expedientes que todavía no tienen trabajo de descripción encima.
RETIRABLES = (Estado.EN_COLA.value, Estado.EN_PROCESAMIENTO.value,
              Estado.HOJA_EN_ELABORACION.value, Estado.HOJA_POR_REVISAR.value,
              Estado.HOJA_REVISADA.value, Estado.DEVUELTO.value)


def main() -> None:
    argumentos = sys.argv[1:]
    simular = "--simular" in argumentos
    carpetas = [a.upper() for a in argumentos if not a.startswith("--")]

    db = SesionLocal()
    try:
        consulta = db.query(Expediente).filter(Expediente.estado.in_(RETIRABLES))
        if carpetas:
            consulta = consulta.filter(Expediente.codigo_carpeta.in_(carpetas))

        fantasmas, protegidos = [], []
        for e in consulta.order_by(Expediente.codigo_carpeta).all():
            archivos = db.query(Archivo).filter(Archivo.codigo_carpeta == e.codigo_carpeta).all()
            si_estan = [a for a in archivos if Path(a.ruta).exists()]
            if si_estan:
                continue                      # tiene con qué trabajar: no se toca
            if e.codigo_referencia or e.describio:
                protegidos.append(e.codigo_carpeta)
                continue
            fantasmas.append((e, archivos))

        if not fantasmas:
            print("No hay expedientes fantasma. Todo lo que está cargado tiene su archivo.")
            if protegidos:
                print(f"({len(protegidos)} tienen descripción y no se tocan aunque falte el archivo.)")
            return

        print(f"{len(fantasmas)} expediente(s) sin documento en el almacén:\n")
        for e, archivos in fantasmas:
            nombres = ", ".join(a.nombre_original for a in archivos) or "sin registro de archivo"
            print(f"  {e.codigo_carpeta}  ·  {e.estado}  ·  {nombres}")

        if simular:
            print("\nSimulación: no se retiró nada. Ejecute sin --simular para hacerlo.")
            return

        for e, archivos in fantasmas:
            for a in archivos:
                db.delete(a)
            db.delete(e)          # la bitácora y los trámites se van con él
        db.commit()

        print(f"\nRetirados {len(fantasmas)} expedientes. Ya puede volver a cargar esas carpetas "
              "en la pestaña Cargue.")
        if protegidos:
            print(f"\n{len(protegidos)} no se tocaron porque ya tienen descripción: "
                  + ", ".join(protegidos[:15]))
    finally:
        db.close()


if __name__ == "__main__":
    main()
