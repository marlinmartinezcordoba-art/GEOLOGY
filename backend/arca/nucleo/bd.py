"""Motor y sesiones de base de datos. PostgreSQL en servidor; SQLite solo para desarrollo y pruebas."""

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from arca.nucleo.config import ajustes


def crear_motor(url: str, **kwargs) -> Engine:
    motor = create_engine(url, future=True, **kwargs)
    if motor.dialect.name == "sqlite":

        @event.listens_for(motor, "connect")
        def _llaves_foraneas(conexion, _registro) -> None:  # pragma: no cover - configuración del motor
            cursor = conexion.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return motor


motor = crear_motor(ajustes().database_url)
FabricaSesiones = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


def obtener_sesion() -> Iterator[Session]:
    with FabricaSesiones() as sesion:
        yield sesion
