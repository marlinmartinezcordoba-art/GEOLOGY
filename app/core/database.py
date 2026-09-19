"""
Conexión a PostgreSQL.

El motor mantiene un grupo de conexiones reutilizables, de modo que cada petición
web toma una conexión ya abierta en lugar de negociar una nueva. Esa sola
diferencia es la que separa una respuesta de milisegundos de las esperas que
imponía la plataforma anterior.

Aquí no se declara ninguna tabla. La clase Base queda lista para que los modelos
se registren en ella cuando llegue el momento de definirlos.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import configuracion

motor = create_engine(
    configuracion.DATABASE_URL,
    pool_size=configuracion.DB_POOL_SIZE,
    max_overflow=configuracion.DB_MAX_OVERFLOW,
    pool_pre_ping=True,      # descarta conexiones muertas antes de usarlas
    pool_recycle=1800,
    echo=configuracion.DB_ECHO,
    future=True,
)

SesionLocal = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False, class_=Session)


class Base(DeclarativeBase):
    """Clase declarativa de la que heredarán todos los modelos del sistema."""


def obtener_sesion() -> Generator[Session, None, None]:
    """Dependencia de FastAPI que entrega una sesión por petición y la cierra al terminar."""
    sesion = SesionLocal()
    try:
        yield sesion
    finally:
        sesion.close()


def crear_tablas() -> int:
    """
    Crea las tablas que falten. Es suficiente mientras el esquema se está construyendo;
    cuando el sistema entre en producción, los cambios de esquema se harán con Alembic
    para poder versionarlos y devolverse.
    """
    from app import models  # noqa: F401  registra todas las tablas en los metadatos
    Base.metadata.create_all(bind=motor)
    return len(Base.metadata.tables)


def verificar_conexion() -> bool:
    """Comprobación de disponibilidad usada por el endpoint de salud."""
    try:
        with motor.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
