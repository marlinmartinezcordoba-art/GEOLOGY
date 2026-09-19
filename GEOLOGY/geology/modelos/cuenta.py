"""
Usuarios con contraseña.

La contraseña nunca se guarda: se guarda su huella, calculada con PBKDF2 y una sal propia
de cada usuario, de modo que ni siquiera quien tenga acceso a la base de datos puede leerla.
Cada persona debe cambiar la clave inicial la primera vez que entra.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from geology.nucleo.bd import Base

ITERACIONES = 240_000


def cifrar_clave(clave: str) -> str:
    """Devuelve «iteraciones$sal$huella». Nunca guarda la clave."""
    sal = os.urandom(16)
    huella = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, ITERACIONES)
    return f"{ITERACIONES}${sal.hex()}${huella.hex()}"


def clave_correcta(clave: str, guardada: str) -> bool:
    """Comparación en tiempo constante, para no filtrar información por la demora."""
    try:
        iteraciones, sal, huella = guardada.split("$")
        calculada = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"),
                                        bytes.fromhex(sal), int(iteraciones))
        return hmac.compare_digest(calculada.hex(), huella)
    except Exception:
        return False


class UsuarioBD(Base):
    __tablename__ = "cuenta"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    cargo: Mapped[Optional[str]] = mapped_column(String(120))
    correo: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    clave_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20), default="equipo")
    funcion: Mapped[str] = mapped_column(String(30), default="Ambas")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    debe_cambiar_clave: Mapped[bool] = mapped_column(Boolean, default=True)
    # Habilitaciones del perfil de la entidad (rol «entidad»). La dirección las prende y
    # apaga desde la pestaña Cuentas; para los demás roles no se consultan.
    ve_hojas_control: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    ve_isadg: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    ve_fuid: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    ve_imagenes: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    ultimo_ingreso: Mapped[Optional[datetime]] = mapped_column(DateTime)
    intentos_fallidos: Mapped[int] = mapped_column(default=0)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
