"""
Vuelve a encolar el levantamiento de la hoja de control de los expedientes ya cargados.

Sirve después de corregir algo del motor: se reprocesa lo que quedó a medias sin volver a
subir un solo archivo. No toca los expedientes que ya tienen descripción hecha ni los
retirados, y no borra nada: lo que el modelo proponga vuelve a quedar como propuesta para que
una persona la revise.

Uso dentro de Docker:
    docker compose exec servidor python scripts/reprocesar.py              todo lo pendiente
    docker compose exec servidor python scripts/reprocesar.py AC-CP-00808  una carpeta
    docker compose exec servidor python scripts/reprocesar.py --devueltos  solo los devueltos
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geology.nucleo.bd import SesionLocal
from geology.modelos import Archivo, Expediente
from geology.dominio.estados import Estado

# Estados desde los que tiene sentido volver a leer el documento. Los que ya están descritos
# o aprobados no se tocan: para rehacer uno de esos hay que retirarlo a conciencia.
REPROCESABLES = (Estado.EN_COLA.value, Estado.EN_PROCESAMIENTO.value,
                 Estado.HOJA_EN_ELABORACION.value, Estado.DEVUELTO.value)


def main() -> None:
    argumentos = [a for a in sys.argv[1:]]
    solo_devueltos = "--devueltos" in argumentos
    carpetas = [a.upper() for a in argumentos if not a.startswith("--")]

    db = SesionLocal()
    try:
        consulta = db.query(Expediente)
        if carpetas:
            consulta = consulta.filter(Expediente.codigo_carpeta.in_(carpetas))
        elif solo_devueltos:
            consulta = consulta.filter(Expediente.estado == Estado.DEVUELTO.value)
        else:
            consulta = consulta.filter(Expediente.estado.in_(REPROCESABLES))

        # En orden de cargue: el primero que entró es el primero que se procesa.
        expedientes = consulta.order_by(Expediente.creado_en, Expediente.id).all()
        if not expedientes:
            print("No hay expedientes para reprocesar con ese criterio.")
            return

        from geology.trabajos import levantar_hoja_de_control

        encolados, sin_archivo, no_procede = 0, [], []
        for e in expedientes:
            if e.estado not in REPROCESABLES:
                no_procede.append(f"{e.codigo_carpeta} ({e.estado})")
                continue
            archivos = (db.query(Archivo)
                          .filter(Archivo.codigo_carpeta == e.codigo_carpeta).all())
            if not archivos:
                sin_archivo.append(e.codigo_carpeta)
                continue
            faltantes = [a.nombre_original for a in archivos if not Path(a.ruta).exists()]
            if faltantes:
                sin_archivo.append(f"{e.codigo_carpeta} (no está en el almacén: "
                                   f"{', '.join(faltantes)})")
                continue
            # Cada expediente entra por una llave distinta, por turnos.
            levantar_hoja_de_control.delay(e.id, "reproceso", encolados)
            encolados += 1
            print(f"  encolado {e.codigo_carpeta}")

        print(f"\n{encolados} expediente(s) encolados para que el modelo los lea de nuevo.")
        if sin_archivo:
            print(f"\n{len(sin_archivo)} sin documento digitalizado utilizable:")
            for x in sin_archivo[:30]:
                print("   ", x)
            if len(sin_archivo) > 30:
                print(f"    y {len(sin_archivo) - 30} más")
            print("  Cárguelos en la pestaña Cargue antes de reprocesarlos.")
        if no_procede:
            print(f"\n{len(no_procede)} no se tocaron porque ya están descritos o retirados:")
            for x in no_procede[:15]:
                print("   ", x)
        if encolados:
            print("\nVea el avance en la pestaña «Hojas de control». Según el tamaño de los "
                  "expedientes puede tardar un rato.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
