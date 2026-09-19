"""
Crea o actualiza las cuentas de la plataforma a partir de un archivo de equipo.

Uso:
    docker compose exec servidor python scripts/crear_usuarios.py                # lee datos/equipo.csv
    docker compose exec servidor python scripts/crear_usuarios.py datos/otro.csv
    docker compose exec servidor python scripts/crear_usuarios.py --administradora "Nombre" correo@dominio

El archivo es un CSV con encabezado:
    nombre,cargo,correo,rol,funcion,clave
    rol      administradora | lider | equipo | consulta | entidad
    funcion  Ambas | Hoja de control | Descripción     (para entidad y consulta se ignora)
    clave    opcional; si va vacía la plataforma genera una provisional y la imprime.

Todas las claves son PROVISIONALES: la plataforma obliga a cambiarlas en el primer ingreso.
A las cuentas que ya existen no se les toca la contraseña, solo nombre, cargo, rol y función.
Hay un ejemplo en datos/equipo.ejemplo.csv.
"""
from __future__ import annotations

import csv
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geology.nucleo.bd import SesionLocal, crear_tablas
from geology.modelos import UsuarioBD, cifrar_clave

ROLES = {"administradora", "lider", "equipo", "consulta", "entidad"}
FUNCIONES = {"Ambas", "Hoja de control", "Descripción"}


def leer(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        filas = [dict((k.strip().lower(), (v or "").strip()) for k, v in fila.items())
                 for fila in csv.DictReader(f)]
    return [f for f in filas if f.get("correo")]


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--administradora":
        if len(args) < 3:
            sys.exit("Uso: --administradora \"Nombre\" correo")
        filas = [{"nombre": args[1], "cargo": "Dirección del proyecto", "correo": args[2],
                  "rol": "administradora", "funcion": "Ambas", "clave": ""}]
    else:
        ruta = Path(args[0]) if args else Path("datos/equipo.csv")
        if not ruta.exists():
            sys.exit(f"No existe {ruta}. Copie datos/equipo.ejemplo.csv como datos/equipo.csv y "
                     "escriba allí al equipo, o use --administradora \"Nombre\" correo.")
        filas = leer(ruta)

    crear_tablas()
    db = SesionLocal()
    try:
        nuevos, actualizados, provisionales = 0, 0, []
        for f in filas:
            correo = f["correo"].lower()
            rol = (f.get("rol") or "equipo").lower()
            funcion = f.get("funcion") or "Ambas"
            if rol not in ROLES:
                print(f"  AVISO: rol «{rol}» no existe para {correo}; se deja «equipo».")
                rol = "equipo"
            if funcion not in FUNCIONES:
                funcion = "Ambas"
            u = db.query(UsuarioBD).filter(UsuarioBD.correo == correo).first()
            if u:
                u.nombre, u.cargo, u.rol, u.funcion, u.activo = f["nombre"], f.get("cargo") or None, rol, funcion, True
                actualizados += 1
            else:
                clave = f.get("clave") or ("Geology-" + secrets.token_urlsafe(6))
                db.add(UsuarioBD(nombre=f["nombre"], cargo=f.get("cargo") or None, correo=correo,
                                 rol=rol, funcion=funcion, clave_hash=cifrar_clave(clave),
                                 debe_cambiar_clave=True, activo=True,
                                 ve_hojas_control=True, ve_isadg=True, ve_fuid=True,
                                 ve_imagenes=False))
                provisionales.append((f["nombre"], correo, clave))
                nuevos += 1
        db.commit()
        print(f"Cuentas listas. {nuevos} nuevas, {actualizados} actualizadas.")
        if provisionales:
            print("\nClaves provisionales. Entréguelas en persona; la plataforma exige cambiarlas "
                  "en el primer ingreso.\n")
            for nombre, correo, clave in provisionales:
                print(f"  {nombre:<34} {correo:<42} {clave}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
