"""Configuración de ARCA leída de variables de entorno con prefijo ARCA_ (o del archivo .env).

Reciclado y adaptado del patrón de configuración de Kustos y de GEOLOGY (nucleo/ajustes.py).
Las claves de desarrollo solo sirven en local y pruebas: fuera de ahí la aplicación no arranca con ellas.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parents[3]

_SECRETO_DESARROLLO = "arca-dev-local-inseguro-cambiar-en-produccion-0123456789"


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARCA_", env_file=RAIZ / ".env", env_file_encoding="utf-8", extra="ignore")

    nombre: str = "ARCA"
    version: str = "0.1.0"
    entorno: str = "local"  # local | test | staging | produccion

    database_url: str = "sqlite:///./arca_local.db"

    clave_secreta: str = _SECRETO_DESARROLLO
    algoritmo_jwt: str = "HS256"
    minutos_sesion: int = 120
    clave_sellado: str = _SECRETO_DESARROLLO
    sellar_cada_eventos: int = 200

    # Bloqueo por intentos fallidos de ingreso.
    intentos_antes_de_bloquear: int = 5
    longitud_minima_clave: int = 12

    origenes_permitidos: list[str] = ["http://localhost:3000"]

    # Repositorio de archivos: original inmutable, una carpeta por organización.
    almacen_dir: Path = RAIZ / "almacen"
    almacen_proveedor: str = "local"  # local | s3 (D-45)
    s3_bucket: str = ""
    s3_endpoint: str = ""  # vacío = AWS; para MinIO u otro compatible, su URL
    s3_region: str = ""
    s3_prefijo: str = ""
    s3_cifrado_servidor: str = ""  # «AES256» o «aws:kms» para pedir además el cifrado del proveedor
    clave_cifrado_almacen: str = ""  # 32 bytes en base64: cifrado AES-256-GCM de cada archivo (obligatoria en producción)
    claves_cifrado_anteriores: list[str] = []  # para leer lo cifrado con una llave anterior mientras se cambia
    max_mb_por_archivo: int = 500
    max_filas_fuid: int = 20000

    # Correo saliente (D-46): invitaciones, contraseñas temporales y recuperación. Vacío = no se envía correo y la
    # contraseña temporal se le muestra a quien administra. «memoria» = se guarda en una bandeja (pruebas y demostraciones).
    smtp_host: str = ""
    smtp_puerto: int = 587
    smtp_usuario: str = ""
    smtp_clave: str = ""
    smtp_remitente: str = "ARCA <no-responder@localhost>"
    smtp_tls: bool = True  # STARTTLS
    url_publica: str = "http://localhost:3000"  # para los enlaces de los correos
    minutos_recuperacion: int = 30

    # Flujo automático (D-39): en local, un hilo de la aplicación atiende la cola de trabajos. En producción va en un
    # proceso aparte (`python -m arca.modulos.flujo.trabajador`) y esto se apaga. En pruebas, siempre apagado.
    trabajos_en_proceso: bool | None = None  # None = encendido solo en local
    segundos_entre_revisiones: float = 3.0
    paginas_ocr_por_tanda: int = 30
    hilos_ocr: int = 1  # hilos por proceso de Tesseract; el paralelismo lo dan los trabajadores
    minutos_alerta_cola: int = 15  # monitoreo: un pendiente más viejo que esto indica un trabajador detenido
    gb_minimos_libres: float = 20  # monitoreo: espacio libre mínimo del almacén local

    @model_validator(mode="after")
    def _exigir_secretos_reales(self) -> "Ajustes":
        if self.entorno not in {"local", "test"}:
            if self.clave_secreta == _SECRETO_DESARROLLO or self.clave_sellado == _SECRETO_DESARROLLO:
                raise ValueError("Fuera de local y pruebas, ARCA_CLAVE_SECRETA y ARCA_CLAVE_SELLADO son obligatorias")
            if self.clave_secreta == self.clave_sellado:
                raise ValueError("La clave de sellado de auditoría debe ser distinta de la clave de sesiones")
        if self.entorno == "produccion" and not self.clave_cifrado_almacen:
            raise ValueError("En producción, ARCA_CLAVE_CIFRADO_ALMACEN es obligatoria: los archivos se guardan cifrados (D-45)")
        return self


@lru_cache
def ajustes() -> Ajustes:
    return Ajustes()
