"""Repositorio de archivos: custodia del original con huella SHA-256 (reciclado de Kustos, comun/servicios/archivos.py).

Reglas:
- El original no se sobrescribe ni se borra por esta vía. Cada archivo se escribe UNA vez, con apertura
  exclusiva: si la clave ya existe, falla en vez de pisarlo.
- La clave de almacenamiento es `organización/aaaa/mm/uuid`, nunca el nombre que trae el archivo: así un
  nombre malicioso no puede escaparse de la carpeta ni chocar con otro.
- El formato se identifica por la firma interna (los primeros bytes), no por la extensión.

Hoy el respaldo es una carpeta local. La interfaz es la misma que tendrá el almacenamiento de objetos
(S3 compatible) cuando se decida el proveedor de nube (D-12).
"""

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from arca.nucleo.config import ajustes
from arca.nucleo.errores import DatosInvalidos, NoEncontrado


@dataclass(frozen=True)
class Identificacion:
    formato: str
    mime: str


_FIRMAS: list[tuple[bytes, Identificacion]] = [
    (b"%PDF-", Identificacion("PDF", "application/pdf")),
    (b"II*\x00", Identificacion("TIFF", "image/tiff")),
    (b"MM\x00*", Identificacion("TIFF", "image/tiff")),
    (b"\xff\xd8\xff", Identificacion("JPEG", "image/jpeg")),
    (b"\x89PNG\r\n\x1a\n", Identificacion("PNG", "image/png")),
    (b"PK\x03\x04", Identificacion("XLSX", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
]


def identificar(contenido: bytes, nombre: str) -> Identificacion | None:
    for firma, ident in _FIRMAS:
        if contenido.startswith(firma):
            if ident.formato == "XLSX" and nombre.lower().endswith(".zip"):
                return Identificacion("ZIP", "application/zip")
            if ident.formato == "XLSX" and not nombre.lower().endswith(".xlsx"):
                return None
            return ident
    if nombre.lower().endswith((".csv", ".txt")):
        try:
            contenido[:4096].decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                contenido[:4096].decode("latin-1")
            except UnicodeDecodeError:
                return None
        return Identificacion("CSV", "text/csv")
    return None


def huella(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _raiz() -> Path:
    return Path(ajustes().almacen_dir)


def guardar(tenant_id: uuid.UUID, contenido: bytes) -> str:
    """Escribe el contenido una sola vez y devuelve su clave de almacenamiento."""
    limite = ajustes().max_mb_por_archivo * 1024 * 1024
    if len(contenido) > limite:
        raise DatosInvalidos(f"El archivo supera el máximo de {ajustes().max_mb_por_archivo} MB")
    ahora = datetime.now(UTC)
    clave = f"{tenant_id}/{ahora:%Y}/{ahora:%m}/{uuid.uuid4().hex}"
    ruta = _raiz() / clave
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o440)
    with os.fdopen(descriptor, "wb") as f:
        f.write(contenido)
    return clave


def leer(clave: str, tenant_id: uuid.UUID) -> bytes:
    """Lee un original. La clave debe pertenecer a la organización que la pide."""
    if not clave.startswith(f"{tenant_id}/") or ".." in clave:
        raise NoEncontrado("El archivo no existe")
    ruta = _raiz() / clave
    if not ruta.is_file():
        raise NoEncontrado("El archivo no está en el repositorio")
    return ruta.read_bytes()


def verificar(clave: str, tenant_id: uuid.UUID, sha256: str) -> bool:
    """Fijeza: el original sigue siendo, byte por byte, el que entró."""
    return huella(leer(clave, tenant_id)) == sha256
