"""Escenario de pruebas: base SQLite en memoria, un operador y dos organizaciones con sus administradores.

Todo con datos ficticios (Instrucciones, «Cómo utilizar este documento»).
"""

import os

os.environ.setdefault("ARCA_ENTORNO", "test")
os.environ.setdefault("ARCA_DATABASE_URL", "sqlite://")

from dataclasses import dataclass  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from arca.main import crear_app  # noqa: E402
from arca.modelos import Base, Usuario  # noqa: E402
from arca.nucleo import bd  # noqa: E402
from arca.nucleo.seguridad import hashear_clave  # noqa: E402

CLAVE = "Clave-de-prueba-2026"
# NIT ficticios con dígito de verificación correcto.
NIT_A = "900123456-8"
NIT_B = "800197268-4"


@pytest.fixture(autouse=True)
def almacen_temporal(tmp_path, monkeypatch):
    """Cada prueba guarda sus archivos en una carpeta propia que se borra al final."""
    from arca.nucleo.config import ajustes

    monkeypatch.setattr(ajustes(), "almacen_dir", tmp_path / "almacen")


@pytest.fixture
def motor():
    motor = bd.crear_motor("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


@pytest.fixture
def fabrica(motor, monkeypatch):
    fabrica = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(bd, "FabricaSesiones", fabrica)
    return fabrica


@pytest.fixture
def cliente(fabrica):
    app = crear_app()

    def sesion():
        with fabrica() as s:
            yield s

    app.dependency_overrides[bd.obtener_sesion] = sesion
    with TestClient(app) as c:
        yield c


def ingresar(cliente: TestClient, correo: str, clave: str = CLAVE, codigo: str | None = None) -> dict:
    r = cliente.post("/api/v1/auth/ingresar", json={"correo": correo, "clave": clave, "codigo_mfa": codigo})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def activar_cuenta(cliente: TestClient, correo: str, temporal: str) -> dict:
    """Primer ingreso: cambia la contraseña temporal por CLAVE y devuelve cabeceras con sesión válida."""
    cab = ingresar(cliente, correo, temporal)
    r = cliente.post("/api/v1/auth/cambiar-clave", json={"clave_actual": temporal, "clave_nueva": CLAVE}, headers=cab)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@dataclass
class Org:
    id: str
    admin: dict  # cabeceras del administrador (con X-Organizacion)
    admin_correo: str

    def con(self, cabeceras: dict) -> dict:
        return cabeceras | {"X-Organizacion": self.id}


@pytest.fixture
def operador(cliente, fabrica) -> dict:
    with fabrica() as db:
        db.add(
            Usuario(
                correo="operador@arca.example.com",
                nombre_completo="Operadora Plataforma",
                clave_hash=hashear_clave(CLAVE),
                es_operador=True,
                debe_cambiar_clave=False,
            )
        )
        db.commit()
    return ingresar(cliente, "operador@arca.example.com")


def crear_org(cliente, operador, nombre: str, nit: str, correo_admin: str, limites: dict | None = None) -> Org:
    r = cliente.post(
        "/api/v1/plataforma/organizaciones",
        json={
            "nombre": nombre,
            "razon_social": f"{nombre} S.A.S.",
            "identificacion": nit,
            "limites": limites or {},
            "administrador": {"correo": correo_admin, "nombre_completo": f"Admin {nombre}"},
        },
        headers=operador,
    )
    assert r.status_code == 201, r.text
    datos = r.json()
    cab = activar_cuenta(cliente, correo_admin, datos["clave_temporal"])
    return Org(id=datos["organizacion"]["id"], admin=cab | {"X-Organizacion": datos["organizacion"]["id"]}, admin_correo=correo_admin)


@pytest.fixture
def org_a(cliente, operador) -> Org:
    return crear_org(cliente, operador, "Consultora Alfa", NIT_A, "admin@alfa.example.com")


@pytest.fixture
def org_b(cliente, operador) -> Org:
    return crear_org(cliente, operador, "Consultora Beta", NIT_B, "admin@beta.example.com")


def rol_id(cliente, org: Org, nombre: str) -> str:
    r = cliente.get("/api/v1/roles", headers=org.admin)
    assert r.status_code == 200, r.text
    return next(x["id"] for x in r.json() if x["nombre"] == nombre)


def agregar_usuario(cliente, org: Org, correo: str, rol: str, proyectos: list[str] | None = None) -> tuple[str, dict]:
    """Agrega un usuario con el rol indicado, activa su cuenta y devuelve (usuario_id, cabeceras)."""
    r = cliente.post(
        "/api/v1/usuarios",
        json={"correo": correo, "nombre_completo": f"Persona {correo}", "rol_id": rol_id(cliente, org, rol), "proyectos": proyectos},
        headers=org.admin,
    )
    assert r.status_code == 201, r.text
    datos = r.json()
    cab = activar_cuenta(cliente, correo, datos["clave_temporal"]) if datos["clave_temporal"] else ingresar(cliente, correo)
    return datos["miembro"]["usuario_id"], org.con(cab)


def proyecto_basico(cliente, org: Org, codigo: str = "P-001", **extra) -> dict:
    cuerpo = {
        "codigo": codigo,
        "nombre": f"Digitalización masiva e historias laborales {codigo}",
        "entidad_cliente": "Entidad Ficticia",
        "numero_contrato": "CT-001-2026",
    } | extra
    r = cliente.post("/api/v1/proyectos", json=cuerpo, headers=org.admin)
    assert r.status_code == 201, r.text
    return r.json()
