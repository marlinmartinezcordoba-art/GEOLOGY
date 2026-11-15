"""Repositorio de archivos: custodia del original con huella SHA-256 (reciclado de Kustos, comun/servicios/archivos.py).

Reglas:
- El original no se sobrescribe ni se borra por esta vía. Cada archivo se escribe UNA vez: si la clave ya existe,
  falla en vez de pisarlo.
- La clave de almacenamiento es `organización/aaaa/mm/uuid`, nunca el nombre que trae el archivo: así un
  nombre malicioso no puede escaparse de la carpeta ni chocar con otro.
- El formato se identifica por la firma interna (los primeros bytes), no por la extensión.
- La huella SHA-256 es siempre la del archivo original (sin cifrar): es la que se verifica y se entrega.

Proveedores (D-45): `local` (una carpeta) o `s3` (cualquier almacenamiento compatible con S3: AWS, MinIO, Wasabi,
Google Cloud Storage en modo interoperable…). Se elige con `ARCA_ALMACEN_PROVEEDOR`.

Cifrado en reposo (D-45): si hay llave (`ARCA_CLAVE_CIFRADO_ALMACEN`, 32 bytes en base64), cada archivo nuevo se
guarda cifrado con AES-256-GCM, ligado a su clave de almacenamiento (no se puede mover a otra clave sin que se
note). Los archivos guardados antes, sin cifrar, se siguen leyendo. Para cambiar de llave, la anterior va en
`ARCA_CLAVES_CIFRADO_ANTERIORES` hasta que se recifre todo.
"""

import base64
import functools
import hashlib
import os
import shutil
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


MAGICO = b"ARCA\x01"  # archivo cifrado, formato 1: MAGICO + id de llave (8) + nonce (12) + cifrado con su etiqueta


def _llaves() -> list[bytes]:
    a = ajustes()
    salida = []
    for texto in [a.clave_cifrado_almacen, *a.claves_cifrado_anteriores]:
        if texto:
            llave = base64.b64decode(texto)
            if len(llave) != 32:
                raise ValueError("Las llaves de cifrado del almacén son de 32 bytes (en base64)")
            salida.append(llave)
    return salida


def _id_llave(llave: bytes) -> bytes:
    return hashlib.sha256(b"arca-almacen" + llave).digest()[:8]


def cifrar(contenido: bytes, clave: str) -> bytes:
    llaves = _llaves()
    if not llaves:
        return contenido
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415

    nonce = os.urandom(12)
    return MAGICO + _id_llave(llaves[0]) + nonce + AESGCM(llaves[0]).encrypt(nonce, contenido, clave.encode())


def descifrar(datos: bytes, clave: str) -> bytes:
    if not datos.startswith(MAGICO):
        return datos  # guardado sin cifrar (antes de activar el cifrado)
    from cryptography.exceptions import InvalidTag  # noqa: PLC0415
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415

    id_llave, nonce, cuerpo = datos[5:13], datos[13:25], datos[25:]
    llave = next((x for x in _llaves() if _id_llave(x) == id_llave), None)
    if llave is None:
        raise NoEncontrado("El archivo está cifrado con una llave que este servidor no tiene")
    try:
        return AESGCM(llave).decrypt(nonce, cuerpo, clave.encode())
    except InvalidTag as e:
        raise NoEncontrado("ALERTA DE INTEGRIDAD: el archivo cifrado fue alterado o no corresponde a su clave") from e


class _Local:
    def escribir(self, clave: str, datos: bytes) -> None:
        ruta = Path(ajustes().almacen_dir) / clave
        ruta.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o440)
        with os.fdopen(descriptor, "wb") as f:
            f.write(datos)

    def leer(self, clave: str) -> bytes:
        ruta = Path(ajustes().almacen_dir) / clave
        if not ruta.is_file():
            raise NoEncontrado("El archivo no está en el repositorio")
        return ruta.read_bytes()

    def estado(self) -> dict[str, object]:
        raiz = Path(ajustes().almacen_dir)
        raiz.mkdir(parents=True, exist_ok=True)
        uso = shutil.disk_usage(raiz)
        return {"proveedor": "local", "disponible": True, "libre_gb": round(uso.free / 1e9, 1), "total_gb": round(uso.total / 1e9, 1)}


class _S3:
    def __init__(self) -> None:
        import boto3  # noqa: PLC0415 — solo si el proveedor es S3

        a = ajustes()
        if not a.s3_bucket:
            raise ValueError("Con el almacén S3 hay que indicar ARCA_S3_BUCKET")
        self.bucket, self.prefijo, self.sse = a.s3_bucket, a.s3_prefijo.strip("/"), a.s3_cifrado_servidor
        self.cliente = boto3.client("s3", endpoint_url=a.s3_endpoint or None, region_name=a.s3_region or None)

    def _k(self, clave: str) -> str:
        return f"{self.prefijo}/{clave}" if self.prefijo else clave

    def escribir(self, clave: str, datos: bytes) -> None:
        extra = {"ServerSideEncryption": self.sse} if self.sse else {}
        try:
            self.cliente.put_object(Bucket=self.bucket, Key=self._k(clave), Body=datos, IfNoneMatch="*", **extra)
        except self.cliente.exceptions.ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("PreconditionFailed", "412"):
                raise DatosInvalidos("Ya existe un archivo con esa clave: no se sobrescribe") from e
            raise

    def leer(self, clave: str) -> bytes:
        try:
            return self.cliente.get_object(Bucket=self.bucket, Key=self._k(clave))["Body"].read()
        except self.cliente.exceptions.NoSuchKey as e:
            raise NoEncontrado("El archivo no está en el repositorio") from e

    def estado(self) -> dict[str, object]:
        try:
            self.cliente.head_bucket(Bucket=self.bucket)
            return {"proveedor": "s3", "disponible": True, "bucket": self.bucket}
        except Exception as e:  # noqa: BLE001 — el estado informa, no falla
            return {"proveedor": "s3", "disponible": False, "bucket": self.bucket, "error": str(e)[:200]}


@functools.lru_cache(maxsize=4)
def _proveedor_cache(nombre: str, bucket: str, endpoint: str):
    return _S3() if nombre == "s3" else _Local()


def proveedor():
    a = ajustes()
    if a.almacen_proveedor not in ("local", "s3"):
        raise ValueError("ARCA_ALMACEN_PROVEEDOR es «local» o «s3»")
    return _Local() if a.almacen_proveedor == "local" else _proveedor_cache("s3", a.s3_bucket, a.s3_endpoint)


def guardar(tenant_id: uuid.UUID, contenido: bytes) -> str:
    """Escribe el contenido una sola vez (cifrado si hay llave) y devuelve su clave de almacenamiento."""
    limite = ajustes().max_mb_por_archivo * 1024 * 1024
    if len(contenido) > limite:
        raise DatosInvalidos(f"El archivo supera el máximo de {ajustes().max_mb_por_archivo} MB")
    ahora = datetime.now(UTC)
    clave = f"{tenant_id}/{ahora:%Y}/{ahora:%m}/{uuid.uuid4().hex}"
    proveedor().escribir(clave, cifrar(contenido, clave))
    return clave


def leer(clave: str, tenant_id: uuid.UUID) -> bytes:
    """Lee un original (descifrado). La clave debe pertenecer a la organización que la pide."""
    if not clave.startswith(f"{tenant_id}/") or ".." in clave:
        raise NoEncontrado("El archivo no existe")
    return descifrar(proveedor().leer(clave), clave)


def verificar(clave: str, tenant_id: uuid.UUID, sha256: str) -> bool:
    """Fijeza: el original sigue siendo, byte por byte, el que entró."""
    return huella(leer(clave, tenant_id)) == sha256


def estado() -> dict[str, object]:
    """Para el monitoreo: proveedor, si responde, espacio libre (local) y si el cifrado está activo."""
    try:
        e = proveedor().estado()
    except Exception as ex:  # noqa: BLE001
        e = {"proveedor": ajustes().almacen_proveedor, "disponible": False, "error": str(ex)[:200]}
    return {**e, "cifrado": bool(_llaves())}
