"""
Configuración central de GEOLOGY.

Todas las variables se leen del archivo .env mediante python-dotenv, de modo que
el mismo código funciona en el equipo de desarrollo, en el servidor de pruebas y
en producción sin tocar una sola línea.

Regla no negociable del proyecto: la persistencia es PostgreSQL. El sistema se
niega a arrancar si la cadena de conexión apunta a SQLite u otro motor, porque un
Sistema de Gestión de Documentos Electrónicos de Archivo requiere concurrencia
real, integridad transaccional y respaldos en caliente.
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

MOTORES_ACEPTADOS = ("postgresql://", "postgresql+psycopg2://", "postgresql+psycopg://")


def _texto(clave: str, defecto: str = "") -> str:
    return os.getenv(clave, defecto)


def _entero(clave: str, defecto: int) -> int:
    try:
        return int(os.getenv(clave, str(defecto)))
    except ValueError:
        return defecto


def _booleano(clave: str, defecto: bool = False) -> bool:
    return os.getenv(clave, str(defecto)).strip().lower() in ("1", "true", "si", "sí")


class Configuracion:
    """Valores de configuración de la aplicación, resueltos al instanciarse."""

    def __init__(self) -> None:
        # Identidad del sistema
        self.NOMBRE = "GEOLOGY"
        self.DESCRIPCION = (
            "Plataforma de organización y descripción documental del fondo acumulado del "
            "Servicio Geológico Colombiano, contrato 733 de 2026."
        )
        self.VERSION = "2.0.0"
        self.ENTORNO = _texto("GEOLOGY_ENTORNO", "desarrollo")

        # Persistencia
        self.DATABASE_URL = _texto(
            "DATABASE_URL", "postgresql+psycopg2://geology:geology@almacen_datos:5432/geology"
        )
        self.DB_POOL_SIZE = _entero("DB_POOL_SIZE", 10)
        self.DB_MAX_OVERFLOW = _entero("DB_MAX_OVERFLOW", 20)
        self.DB_ECHO = _booleano("DB_ECHO", False)

        # Encolamiento de tareas
        self.CELERY_BROKER_URL = _texto("CELERY_BROKER_URL", "redis://mensajeria:6379/0")
        self.CELERY_RESULT_BACKEND = _texto("CELERY_RESULT_BACKEND", "redis://mensajeria:6379/1")
        self.COLA_PREDETERMINADA = _texto("GEOLOGY_COLA", "geology")
        self.ZONA_HORARIA = _texto("ZONA_HORARIA", "America/Bogota")

        # Interfaz web independiente
        self.ORIGENES_PERMITIDOS = [
            origen.strip()
            for origen in _texto("ORIGENES_PERMITIDOS", "http://localhost:3000").split(",")
            if origen.strip()
        ]

        # Almacenamiento de objetos en Amazon Web Services
        self.AWS_REGION = _texto("AWS_REGION", "us-east-1")
        self.AWS_S3_BUCKET = _texto("AWS_S3_BUCKET")
        self.AWS_ACCESS_KEY_ID = _texto("AWS_ACCESS_KEY_ID")
        self.AWS_SECRET_ACCESS_KEY = _texto("AWS_SECRET_ACCESS_KEY")
        self.URL_PREFIRMADA_SEGUNDOS = _entero("URL_PREFIRMADA_SEGUNDOS", 900)

        self._validar_motor()

    def _validar_motor(self) -> None:
        url = self.DATABASE_URL.strip().lower()
        if url.startswith("sqlite"):
            raise RuntimeError(
                "GEOLOGY no admite SQLite. Configure DATABASE_URL apuntando a PostgreSQL, "
                "por ejemplo postgresql+psycopg2://geology:clave@db:5432/geology"
            )
        if not url.startswith(MOTORES_ACEPTADOS):
            raise RuntimeError(
                f"DATABASE_URL debe usar PostgreSQL. Valor recibido: {self.DATABASE_URL!r}"
            )

    @property
    def es_produccion(self) -> bool:
        return self.ENTORNO.strip().lower() in ("produccion", "producción", "production")


@lru_cache
def obtener_configuracion() -> Configuracion:
    return Configuracion()


configuracion = obtener_configuracion()
