"""Almacén de archivos (D-45): proveedor local o S3, cifrado AES-256-GCM en reposo, integridad y cambio de llave."""

import base64
import os
import uuid
from pathlib import Path

import pytest
from fabricas import pdf_escaneado

from arca.nucleo import almacen
from arca.nucleo.config import Ajustes, ajustes
from arca.nucleo.errores import DatosInvalidos, NoEncontrado

ORG = uuid.uuid4()


def _llave() -> str:
    return base64.b64encode(os.urandom(32)).decode()


def test_sin_llave_se_guarda_tal_cual():
    clave = almacen.guardar(ORG, b"%PDF-1.7 original ficticio")
    assert (Path(ajustes().almacen_dir) / clave).read_bytes() == b"%PDF-1.7 original ficticio"
    assert almacen.leer(clave, ORG) == b"%PDF-1.7 original ficticio"
    with pytest.raises(NoEncontrado):
        almacen.leer(clave, uuid.uuid4())  # otra organización no lo ve


def test_cifrado_integridad_y_cambio_de_llave(monkeypatch):
    original = b"%PDF-1.7 historia laboral ficticia"
    sin_cifrar = almacen.guardar(ORG, original)  # de antes de activar el cifrado
    vieja = _llave()
    monkeypatch.setattr(ajustes(), "clave_cifrado_almacen", vieja)
    clave = almacen.guardar(ORG, original)
    en_disco = (Path(ajustes().almacen_dir) / clave).read_bytes()
    assert en_disco.startswith(almacen.MAGICO) and original not in en_disco
    assert almacen.leer(clave, ORG) == original and almacen.verificar(clave, ORG, almacen.huella(original))
    assert almacen.leer(sin_cifrar, ORG) == original  # lo anterior se sigue leyendo
    # Alterar un byte o moverlo a otra clave se detecta.
    ruta = Path(ajustes().almacen_dir) / clave
    os.chmod(ruta, 0o640)
    ruta.write_bytes(en_disco[:-1] + bytes([en_disco[-1] ^ 1]))
    with pytest.raises(NoEncontrado, match="INTEGRIDAD"):
        almacen.leer(clave, ORG)
    otra = almacen.guardar(ORG, original)
    copia = Path(ajustes().almacen_dir) / f"{ORG}/2030/01/{uuid.uuid4().hex}"
    copia.parent.mkdir(parents=True, exist_ok=True)
    copia.write_bytes((Path(ajustes().almacen_dir) / otra).read_bytes())
    with pytest.raises(NoEncontrado, match="INTEGRIDAD"):
        almacen.leer(str(copia.relative_to(ajustes().almacen_dir)), ORG)
    # Cambio de llave: la nueva cifra; la anterior sigue leyendo lo suyo.
    monkeypatch.setattr(ajustes(), "clave_cifrado_almacen", _llave())
    with pytest.raises(NoEncontrado, match="llave"):
        almacen.leer(otra, ORG)
    monkeypatch.setattr(ajustes(), "claves_cifrado_anteriores", [vieja])
    assert almacen.leer(otra, ORG) == original
    assert almacen.estado()["cifrado"] is True


def test_produccion_exige_llave():
    secretos = {"clave_secreta": "a" * 48, "clave_sellado": "b" * 48}
    with pytest.raises(ValueError, match="CIFRADO_ALMACEN"):
        Ajustes(entorno="produccion", **secretos)
    assert Ajustes(entorno="produccion", clave_cifrado_almacen=_llave(), **secretos).entorno == "produccion"


def test_s3_compatible(monkeypatch):
    moto = pytest.importorskip("moto")
    with moto.mock_aws():
        import boto3

        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "prueba")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "prueba")
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="arca-pruebas")
        for k, v in {"almacen_proveedor": "s3", "s3_bucket": "arca-pruebas", "s3_region": "us-east-1", "s3_prefijo": "archivos",
                     "clave_cifrado_almacen": _llave()}.items():
            monkeypatch.setattr(ajustes(), k, v)
        almacen._proveedor_cache.cache_clear()
        try:
            clave = almacen.guardar(ORG, b"%PDF-1.7 en la nube")
            guardado = boto3.client("s3", region_name="us-east-1").get_object(Bucket="arca-pruebas", Key=f"archivos/{clave}")["Body"].read()
            assert guardado.startswith(almacen.MAGICO)  # en la nube va cifrado
            assert almacen.leer(clave, ORG) == b"%PDF-1.7 en la nube"
            with pytest.raises(DatosInvalidos):
                almacen.proveedor().escribir(clave, b"otro")  # no se sobrescribe
            assert almacen.estado() == {"proveedor": "s3", "disponible": True, "bucket": "arca-pruebas", "cifrado": True}
            with pytest.raises(NoEncontrado):
                almacen.leer(f"{ORG}/2030/01/no-existe", ORG)
        finally:
            almacen._proveedor_cache.cache_clear()


def test_la_plataforma_funciona_con_cifrado(cliente, org_a, monkeypatch):
    """De punta a punta: se carga un PDF cifrado en reposo y el visor lo muestra."""
    from test_m13_ocr import _listo  # noqa: PLC0415

    monkeypatch.setattr(ajustes(), "clave_cifrado_almacen", _llave())
    base, _, u = _listo(cliente, org_a)
    r = cliente.post(f"{base}/digitalizacion/archivos", files=[("archivos", ("CP-2.pdf", pdf_escaneado(1)))], data={"rutas_relativas": ["CP-2.pdf"]}, headers=org_a.admin)
    assert r.status_code == 200, r.text
    img = cliente.get(f"{base}/hojas-control/unidades/{u['CP-2']}/paginas/1/imagen", headers=org_a.admin)
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")
    archivos = list(Path(ajustes().almacen_dir).rglob("*"))
    assert any(p.is_file() and p.read_bytes().startswith(almacen.MAGICO) for p in archivos)
