"""
Vuelve a poner a leer las carpetas que quedaron devueltas.

Una carpeta queda devuelta por razones muy distintas y no todas se arreglan igual. La que
volvió porque el tomo era demasiado extenso para una sola petición ya no tiene por qué
volver: ahora el sistema lo parte solo y lo lee por bloques encadenados. La que volvió
porque el archivo no estaba en el almacén sí necesita que se cargue de nuevo, y eso no lo
arregla este guion.

Por eso aquí primero se MIRA y solo después se encola. Sin argumentos no toca nada: lista
las devueltas con el motivo que quedó en la bitácora, para decidir con el dato delante.

Uso, desde la carpeta del proyecto:

    docker compose exec servidor python scripts/releer_devueltas.py
    docker compose exec servidor python scripts/releer_devueltas.py --encolar
    docker compose exec servidor python scripts/releer_devueltas.py --encolar --solo-extensos
    docker compose exec servidor python scripts/releer_devueltas.py --encolar --carpeta AC-CP-00808
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geology.nucleo.bd import SesionLocal                      # noqa: E402
from geology.modelos import Archivo, Expediente, Trazabilidad# noqa: E402
from geology.dominio.estados import Estado                        # noqa: E402

# Las devueltas por tamaño son las que este cambio arregla: eran tomos que no cabían en una
# petición y ahora se leen por bloques.
SENAS_DE_EXTENSO = ("tope por petición", "tope por archivo", "páginas y el tope",
                    "Pártalo con sufijo", "no reconoció ningún trámite")


def motivo_de(db, exp: Expediente) -> str:
    ultima = (db.query(Trazabilidad)
                .filter(Trazabilidad.expediente_id == exp.id)
                .order_by(Trazabilidad.id.desc()).first())
    return (ultima.motivo or "") if ultima else ""


def paginas_de(db, exp: Expediente) -> int:
    total = 0
    for a in db.query(Archivo).filter(Archivo.codigo_carpeta == exp.codigo_carpeta).all():
        total += a.paginas or 0
    return total


def hay_documento(db, exp: Expediente) -> bool:
    for a in db.query(Archivo).filter(Archivo.codigo_carpeta == exp.codigo_carpeta).all():
        if Path(a.ruta).exists():
            return True
    return False


def principal() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--encolar", action="store_true",
                   help="además de listar, vuelve a poner a leer. Sin esto solo mira.")
    p.add_argument("--solo-extensos", action="store_true",
                   help="únicamente las que volvieron por ser demasiado extensas.")
    p.add_argument("--carpeta", default="", help="una sola carpeta, por su código.")
    args = p.parse_args()

    db = SesionLocal()
    try:
        consulta = db.query(Expediente).filter(Expediente.estado == Estado.DEVUELTO.value)
        if args.carpeta:
            consulta = consulta.filter(Expediente.codigo_carpeta == args.carpeta.strip().upper())
        devueltas = consulta.order_by(Expediente.codigo_carpeta).all()

        if not devueltas:
            print("No hay carpetas devueltas.")
            return 0

        encolables, sin_documento, otras = [], [], []
        print(f"{len(devueltas)} carpeta(s) devuelta(s):\n")
        for exp in devueltas:
            motivo = motivo_de(db, exp)
            paginas = paginas_de(db, exp)
            tiene = hay_documento(db, exp)
            extensa = any(s.lower() in motivo.lower() for s in SENAS_DE_EXTENSO)

            print(f"  {exp.codigo_carpeta}  ({paginas or '?'} páginas)")
            print(f"      {motivo[:160] or 'sin motivo anotado'}")

            if not tiene:
                sin_documento.append(exp)
                print("      → hay que volver a cargar el documento; esto no lo arregla el guion.")
            elif extensa or not args.solo_extensos:
                encolables.append(exp)
                print("      → se puede volver a leer.")
            else:
                otras.append(exp)
            print()

        if sin_documento:
            print(f"{len(sin_documento)} sin documento en el almacén. Cárguelas otra vez "
                  "desde la pestaña Cargue.\n")

        if not args.encolar:
            print(f"{len(encolables)} se pueden volver a leer. Para hacerlo, agregue --encolar.")
            return 0

        from geology.trabajos import levantar_hoja_de_control
        turno = db.query(Trazabilidad).filter(Trazabilidad.accion == "levantar_hoja").count()
        puestas = 0
        for exp in encolables:
            db.add(Trazabilidad(expediente_id=exp.id, estado_anterior=exp.estado,
                                estado_nuevo=Estado.EN_COLA.value, accion="levantar_hoja",
                                usuario="releer_devueltas",
                                motivo="Se vuelve a leer: los documentos extensos ahora se "
                                       "parten en bloques y se leen encadenados."))
            exp.estado = Estado.EN_COLA.value
            db.commit()
            levantar_hoja_de_control.delay(exp.id, "releer_devueltas", turno + puestas)
            puestas += 1
            print(f"  encolada {exp.codigo_carpeta}")

        print(f"\n{puestas} carpeta(s) puestas a leer. Siga el avance en la pestaña Proceso.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(principal())
