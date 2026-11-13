"""Contraseñas (Argon2), tokens de sesión (JWT), verificación en dos pasos (TOTP) y validación de NIT.

Reciclado de Kustos (security/hashing.py y security/tokens.py). El TOTP sigue la RFC 6238 con la
biblioteca estándar, compatible con Google Authenticator, Microsoft Authenticator y similares.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import jwt
from pwdlib import PasswordHash

from arca.nucleo.config import ajustes

# --- Contraseñas -------------------------------------------------------------------------------

_hasher = PasswordHash.recommended()
# Se verifica contra este hash cuando el correo no existe, para que la respuesta tarde lo mismo.
_HASH_FICTICIO = _hasher.hash("clave-ficticia-para-tiempo-constante")


def hashear_clave(clave: str) -> str:
    return _hasher.hash(clave)


def verificar_clave(clave: str, hash_guardado: str | None) -> bool:
    if hash_guardado is None:
        _hasher.verify(clave, _HASH_FICTICIO)
        return False
    return _hasher.verify(clave, hash_guardado)


def clave_temporal() -> str:
    """Contraseña provisional de un solo uso; el usuario debe cambiarla en su primer ingreso."""
    return secrets.token_urlsafe(12)


# --- Tokens de sesión ----------------------------------------------------------------------------

TIPO_ACCESO = "acceso"


@dataclass(frozen=True)
class DatosToken:
    usuario_id: uuid.UUID
    version_sesion: int
    tipo: str


def crear_token(usuario_id: uuid.UUID, version_sesion: int) -> str:
    a = ajustes()
    ahora = datetime.now(UTC)
    carga = {"sub": str(usuario_id), "typ": TIPO_ACCESO, "sv": version_sesion, "iat": ahora, "exp": ahora + timedelta(minutes=a.minutos_sesion)}
    return jwt.encode(carga, a.clave_secreta, algorithm=a.algoritmo_jwt)


def leer_token(token: str) -> DatosToken | None:
    a = ajustes()
    try:
        carga = jwt.decode(token, a.clave_secreta, algorithms=[a.algoritmo_jwt])
        return DatosToken(uuid.UUID(carga["sub"]), int(carga.get("sv", 0)), carga.get("typ", ""))
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


# --- Verificación en dos pasos (TOTP, RFC 6238) ------------------------------------------------

PASO_TOTP = 30


def nuevo_secreto_totp() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def codigo_totp(secreto: str, instante: float | None = None, digitos: int = 6) -> str:
    clave = base64.b32decode(secreto + "=" * (-len(secreto) % 8))
    contador = int((time.time() if instante is None else instante) // PASO_TOTP)
    resumen = hmac.new(clave, struct.pack(">Q", contador), hashlib.sha1).digest()
    desplazamiento = resumen[-1] & 0x0F
    numero = (struct.unpack(">I", resumen[desplazamiento : desplazamiento + 4])[0] & 0x7FFFFFFF) % 10**digitos
    return f"{numero:0{digitos}d}"


def verificar_totp(secreto: str, codigo: str, instante: float | None = None) -> bool:
    """Acepta el código del intervalo actual y el de un intervalo antes o después (desfase de reloj)."""
    if not codigo or not codigo.isdigit():
        return False
    base = time.time() if instante is None else instante
    return any(hmac.compare_digest(codigo_totp(secreto, base + d * PASO_TOTP), codigo) for d in (-1, 0, 1))


def uri_totp(secreto: str, correo: str) -> str:
    return f"otpauth://totp/ARCA:{quote(correo)}?secret={secreto}&issuer=ARCA&period={PASO_TOTP}&digits=6"


# --- NIT (Colombia) ----------------------------------------------------------------------------

_PESOS_NIT = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


def digito_verificacion_nit(numero: str) -> int:
    """Dígito de verificación de la DIAN (módulo 11 con los pesos oficiales)."""
    suma = sum(int(d) * _PESOS_NIT[i] for i, d in enumerate(reversed(numero)))
    residuo = suma % 11
    return residuo if residuo < 2 else 11 - residuo


def normalizar_nit(valor: str) -> str:
    """Devuelve el NIT como «número-dv». Exige el dígito de verificación y que sea el correcto."""
    limpio = valor.replace(".", "").replace(" ", "")
    if "-" not in limpio:
        raise ValueError("Escriba el NIT con su dígito de verificación, por ejemplo 900123456-8")
    numero, dv = limpio.rsplit("-", 1)
    if not numero.isdigit() or not dv.isdigit() or len(dv) != 1 or not 5 <= len(numero) <= 15:
        raise ValueError("El NIT debe tener entre 5 y 15 dígitos y un dígito de verificación")
    if digito_verificacion_nit(numero) != int(dv):
        raise ValueError("El dígito de verificación del NIT no corresponde")
    return f"{numero}-{dv}"
