"""Crea (o reconoce) la cuenta del operador de la plataforma e imprime su contraseña temporal.

Uso:  python scripts/crear_operador.py operador@empresa.com "Nombre Apellido"

El operador administra organizaciones; no entra a los datos de ninguna. Debe cambiar la contraseña
temporal en el primer ingreso y se recomienda activar la verificación en dos pasos de inmediato.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from arca.modelos import Usuario  # noqa: E402
from arca.modulos.m25_auditoria.servicios import registrar  # noqa: E402
from arca.nucleo.bd import FabricaSesiones  # noqa: E402
from arca.nucleo.seguridad import clave_temporal, hashear_clave  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    correo, nombre = sys.argv[1].strip().lower(), sys.argv[2].strip()
    with FabricaSesiones() as db:
        if db.scalar(select(Usuario).where(Usuario.correo == correo)):
            print(f"Ya existe una cuenta con el correo {correo}. No se modificó.")
            return 1
        temporal = clave_temporal()
        usuario = Usuario(correo=correo, nombre_completo=nombre, clave_hash=hashear_clave(temporal), es_operador=True, debe_cambiar_clave=True)
        db.add(usuario)
        db.flush()
        registrar(
            db, tenant_id=None, usuario=None, accion="CREAR_OPERADOR", objeto="Usuario", objeto_id=usuario.id, detalle=correo, usuario_nombre="Instalación"
        )
        db.commit()
    print(f"Operador creado: {correo}\nContraseña temporal (se muestra una sola vez): {temporal}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
