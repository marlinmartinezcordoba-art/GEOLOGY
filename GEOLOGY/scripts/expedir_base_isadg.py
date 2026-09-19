"""
Expide la base de datos de descripción ISAD(G) en la plantilla del proyecto.

Escribe DENTRO de datos/Plantilla_BASE_ISADG_733.xlsx: ni una columna cambia de sitio. Si
algún día la plantilla cambia, se reemplaza ese archivo y este programa no se toca.

La descripción sale multinivel, que es como la pide la norma: fondo, sección —el periodo
institucional—, subserie de la tabla convalidada y, al final, la unidad documental. Cada
renglón queda amarrado al de arriba por la columna «Unidad superior».

Uso, desde la carpeta del proyecto:

    docker compose exec servidor python scripts/expedir_base_isadg.py
    docker compose exec servidor python scripts/expedir_base_isadg.py --incluir-por-validar
    docker compose exec servidor python scripts/expedir_base_isadg.py --solo-conservacion-total

El archivo queda en la carpeta «expedidos» del proyecto, que se ve desde Windows en
C:\\GEOLOGY\\expedidos.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geology.nucleo.bd import SesionLocal                      # noqa: E402
from geology.dominio import base_isadg as bi# noqa: E402
from geology.dominio.estados import Estado                        # noqa: E402


def principal() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--incluir-por-validar", action="store_true",
                   help="agrega las descripciones sin validar. Para revisar, NO para entregar.")
    p.add_argument("--solo-conservacion-total", action="store_true",
                   help="únicamente lo que va a la transferencia secundaria.")
    p.add_argument("--salida", default="", help="dónde escribirlo; por omisión, expedidos/")
    p.add_argument("--sin-revisor", action="store_true",
                   help="no pone el segundo modelo a revisar. Más rápido y sin gasto de cuota, "
                        "pero solo quedan las reglas y no el juicio sobre título y alcance.")
    p.add_argument("--limite-revisor", type=int, default=0,
                   help="cuántas unidades revisa el segundo modelo; 0 es todas.")
    args = p.parse_args()

    db = SesionLocal()
    try:
        estados = ()
        if args.incluir_por_validar:
            estados = (Estado.DESCRIPCION_POR_VALIDAR.value,
                       Estado.DESCRIPCION_VALIDADA.value,
                       Estado.ARCHIVADO.value, Estado.EN_INVENTARIO.value)
        salida = None
        try:
            salida = bi.expedir(db, destino=Path(args.salida) if args.salida else None,
                                solo_conservacion_total=args.solo_conservacion_total,
                                desde_estado=estados,
                                con_revisor=not args.sin_revisor,
                                limite_revisor=args.limite_revisor)
        except ValueError as e:
            print(e)
            print("\nPara ver cómo va quedando, agregue  --incluir-por-validar")
            return 1

        cuenta = Counter(r.nivel for r in bi.construir(db, args.solo_conservacion_total, estados))
        print(f"Base expedida: {salida['archivo']}\n")
        for nivel in (bi.NIVEL_FONDO, bi.NIVEL_SECCION, bi.NIVEL_SUBSERIE, bi.NIVEL_EXPEDIENTE):
            if cuenta.get(nivel):
                print(f"  {cuenta[nivel]:5d}  {nivel}")
        print(f"  {'-' * 5}")
        print(f"  {salida['unidades']:5d}  unidades de descripción en total")

        r = salida["resumen"]
        print("\n" + "=" * 72)
        if r["se_puede_entregar"]:
            print("SE PUEDE ENTREGAR. No quedó ningún incumplimiento de norma.")
        else:
            print(f"NO SE PUEDE ENTREGAR TODAVÍA. {r['devuelve']} incumplimiento(s) de norma.")
            print("Con uno solo devuelven el lote completo.")
        print("=" * 72)

        rv = r.get("revisor") or {}
        if rv.get("revisados"):
            print(f"\nUn segundo modelo, distinto al que redactó, revisó "
                  f"{rv['revisados']} de {rv['de']} unidad(es).")
            if rv.get("se_acabo_la_cuota"):
                print("  Se detuvo por falta de cuota. Vuelva a correrlo mañana si quiere el resto.")
        elif rv.get("error"):
            print(f"\nEl revisor no pudo correr ({rv['error']}). La revisión de reglas sí "
                  "quedó completa.")
        if r["revise"]:
            print(f"\nAdemás hay {r['revise']} punto(s) para mirar con el expediente delante.")
        if r["por_regla"]:
            print("\nPor regla:")
            for regla, cuantos in r["por_regla"].items():
                print(f"  {cuantos:4d}  {regla}")

        graves = [h for h in salida["hallazgos"] if h.gravedad == "DEVUELVE"]
        for h in graves[:12]:
            print(f"\n  {h.unidad} · {h.regla}")
            print(f"      {h.que_pasa}")
            print(f"      → {h.como_se_arregla}")
        if len(graves) > 12:
            print(f"\n  … y {len(graves) - 12} más. Están todos en la hoja «Revisión previa» "
                  "del archivo.")

        print("\nEl detalle completo va dentro del archivo, en la hoja «Revisión previa».")
        if args.incluir_por_validar:
            print("\nADVERTENCIA: este archivo trae descripciones SIN VALIDAR. Sirve para "
                  "revisar cómo va quedando, no para entregar.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(principal())
