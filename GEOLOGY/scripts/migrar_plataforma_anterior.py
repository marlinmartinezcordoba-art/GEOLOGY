"""
Migra a GEOLOGY lo que ya se trabajó en la plataforma anterior (base de datos y depósito).

Son tres pasos y hay que seguirlos en este orden. Todo se hace con la plataforma parada
(solo la base de datos encendida):

  1. En el servidor anterior, sacar el respaldo:
         docker compose exec db pg_dump -U <usuario> --no-owner --no-privileges <base> > respaldo_anterior.sql
     y copiar también la carpeta «almacen» (los documentos digitalizados).

  2. En GEOLOGY, con la base de datos vacía:
         docker compose up -d almacen_datos
         docker compose run --rm servidor python scripts/migrar_plataforma_anterior.py --preparar
         docker compose exec -T almacen_datos psql -U geology -d geology < respaldo_anterior.sql
         docker compose run --rm servidor python scripts/migrar_plataforma_anterior.py --renombrar --almacen /ruta/al/almacen
         docker compose up -d

     --preparar   borra las tablas vacías que GEOLOGY haya creado, para que el respaldo entre limpio.
     --renombrar  pasa las tablas a los nombres de GEOLOGY, agrega las columnas nuevas, corrige las
                  rutas del depósito y copia los documentos del almacén anterior.

Nada se borra del respaldo ni del almacén de origen. Si algo falla a mitad, se puede vaciar la
base (docker compose down -v) y volver a empezar desde el paso 2.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text

from geology.nucleo.bd import motor

# tabla anterior -> tabla de GEOLOGY
TABLAS = {
    "expediente": "unidad_documental", "tramite": "asiento_hoja",
    "unidad_inventario": "inventario_origen", "trazabilidad": "bitacora",
    "consumo_modelo": "consumo_lector", "archivo": "archivo_digital",
    "caja": "caja_definitiva", "usuario": "cuenta", "fondo": "fondo_documental",
    "periodo": "periodo_institucional", "seccion": "seccion_productora",
    "serie": "serie_documental", "subserie": "subserie_documental",
}


def preparar() -> None:
    insp = inspect(motor)
    existentes = set(insp.get_table_names())
    nuevas = [t for t in TABLAS.values() if t in existentes]
    if not nuevas:
        print("La base está vacía. Ya puede restaurar el respaldo.")
        return
    with motor.begin() as cx:
        for t in nuevas:
            filas = cx.execute(text(f"SELECT count(*) FROM {t}")).scalar()
            if filas:
                sys.exit(f"La tabla {t} tiene {filas} filas: la base NO está vacía. La migración "
                         "solo se hace sobre una base vacía (docker compose down -v).")
        cx.execute(text("DROP TABLE IF EXISTS " + ", ".join(nuevas) + " CASCADE"))
    print(f"Se retiraron {len(nuevas)} tablas vacías. Ya puede restaurar el respaldo.")


def renombrar(almacen: Path | None) -> None:
    insp = inspect(motor)
    existentes = set(insp.get_table_names())
    faltan = [v for v in TABLAS if v not in existentes and TABLAS[v] not in existentes]
    if faltan:
        sys.exit(f"No están las tablas del respaldo: {', '.join(faltan)}. ¿Se restauró el archivo?")
    with motor.begin() as cx:
        for vieja, nueva in TABLAS.items():
            if vieja in existentes and nueva not in existentes:
                cx.execute(text(f"ALTER TABLE {vieja} RENAME TO {nueva}"))
                print(f"  {vieja:<20} -> {nueva}")
        # Las secuencias siguen amarradas a su columna por identidad interna; solo se les
        # cambia el nombre para que no quede rastro del anterior.
        secuencias = [r[0] for r in cx.execute(text(
            "SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema='public'"))]
        for vieja, nueva in TABLAS.items():
            s = f"{vieja}_id_seq"
            if s in secuencias and f"{nueva}_id_seq" not in secuencias:
                cx.execute(text(f"ALTER SEQUENCE {s} RENAME TO {nueva}_id_seq"))
        # Índices con el nombre anterior
        indices = [r[0] for r in cx.execute(text(
            "SELECT indexname FROM pg_indexes WHERE schemaname='public'"))]
        for vieja, nueva in TABLAS.items():
            for ix in indices:
                if ix.startswith(f"ix_{vieja}_"):
                    cx.execute(text(f"ALTER INDEX {ix} RENAME TO ix_{nueva}_{ix[len(vieja) + 4:]}"))

    # Columnas que GEOLOGY tiene y la plataforma anterior no.
    from geology.nucleo.estructura import aplicar
    for linea in aplicar():
        if not linea.startswith("(sin efecto)"):
            print("  estructura:", linea)

    # Rutas del depósito: la plataforma anterior guardaba en «almacen/» y expedía en «salida/».
    with motor.begin() as cx:
        for columna in ("ruta", "ruta_matriz", "ruta_consulta", "ruta_texto"):
            n = cx.execute(text(
                f"UPDATE archivo_digital SET {columna} = regexp_replace({columna}, '^(\\./)?almacen/', 'deposito/') "
                f"WHERE {columna} LIKE 'almacen/%' OR {columna} LIKE './almacen/%'")).rowcount
            if n:
                print(f"  {n} ruta(s) de {columna} pasadas a deposito/")
        # Los usuarios anteriores no tienen perfil de entidad; sus habilitaciones quedan por defecto.
        n = cx.execute(text("UPDATE cuenta SET ve_hojas_control = TRUE, ve_isadg = TRUE, ve_fuid = TRUE, "
                            "ve_imagenes = FALSE WHERE ve_hojas_control IS NULL")).rowcount

    if almacen:
        if not almacen.exists():
            sys.exit(f"No existe la carpeta {almacen}.")
        destino = Path("deposito")
        destino.mkdir(exist_ok=True)
        copiados = 0
        for origen in almacen.rglob("*"):
            if origen.is_file():
                rel = origen.relative_to(almacen)
                d = destino / rel
                if not d.exists():
                    d.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(origen, d)
                    copiados += 1
        print(f"  {copiados} documento(s) copiados de {almacen} a deposito/")

    with motor.connect() as cx:
        for nueva in ("unidad_documental", "asiento_hoja", "inventario_origen", "archivo_digital", "cuenta"):
            print(f"  {nueva:<20} {cx.execute(text(f'SELECT count(*) FROM {nueva}')).scalar()} filas")
    print("\nMigración terminada. Arranque la plataforma: docker compose up -d")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--preparar", action="store_true")
    p.add_argument("--renombrar", action="store_true")
    p.add_argument("--almacen", default="", help="carpeta «almacen» de la plataforma anterior, para copiar los documentos")
    a = p.parse_args()
    if a.preparar:
        preparar()
    elif a.renombrar:
        renombrar(Path(a.almacen) if a.almacen else None)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
