"""
Sesiones firmadas.

El servidor no guarda sesiones: entrega un pase firmado con la llave secreta del proyecto.
Si alguien lo modifica, la firma deja de coincidir y el pase se rechaza. Los pases vencen,
de modo que un computador olvidado abierto no queda con la sesión viva para siempre.
"""
from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta
from hashlib import sha256

GEOLOGY_HORAS_SESION = int(os.getenv("GEOLOGY_HORAS_SESION", "12"))


def _llave() -> bytes:
    secreto = os.getenv("GEOLOGY_CLAVE", "").strip()
    if not secreto or secreto in ("cambie_esta_llave", "cambieme"):
        # Sin llave configurada se usa una aleatoria de esta ejecución: los pases dejan de
        # valer al reiniciar. Es incómodo a propósito, para que nadie salga a la red sin llave.
        secreto = _llave.__dict__.setdefault("temporal", secrets.token_hex(32))
    return secreto.encode("utf-8")


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode("ascii").rstrip("=")


def _desb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def crear_pase(correo: str, horas: int | None = None) -> str:
    cuerpo = {"correo": correo,
              "vence": (datetime.now() + timedelta(hours=horas or GEOLOGY_HORAS_SESION)).timestamp()}
    crudo = _b64(json.dumps(cuerpo).encode("utf-8"))
    firma = _b64(hmac.new(_llave(), crudo.encode("ascii"), sha256).digest())
    return f"{crudo}.{firma}"


def leer_pase(pase: str) -> str | None:
    """Devuelve el correo si el pase es válido y no ha vencido; None en cualquier otro caso."""
    try:
        crudo, firma = pase.split(".")
        esperada = _b64(hmac.new(_llave(), crudo.encode("ascii"), sha256).digest())
        if not hmac.compare_digest(firma, esperada):
            return None
        cuerpo = json.loads(_desb64(crudo))
        if datetime.now().timestamp() > float(cuerpo["vence"]):
            return None
        return cuerpo["correo"]
    except Exception:
        return None


def llave_configurada() -> bool:
    secreto = os.getenv("GEOLOGY_CLAVE", "").strip()
    return bool(secreto) and secreto not in ("cambie_esta_llave", "cambieme")
