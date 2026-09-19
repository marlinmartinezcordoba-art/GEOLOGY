"""
Punto de entrada de GEOLOGY.

Ejecución local:
    uvicorn geology.main:aplicacion --reload
Documentación interactiva (solo en desarrollo):
    http://localhost:8080/docs
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from geology.nucleo.ajustes import configuracion
from geology.nucleo.bd import crear_tablas, verificar_conexion
from geology.nucleo.cola import celery_app

# La documentación interactiva es un mapa completo de la interfaz de programación. Se
# publica solo en desarrollo; en producción responde 404.
_publica = not configuracion.es_produccion

aplicacion = FastAPI(
    title=configuracion.NOMBRE,
    description=configuracion.DESCRIPCION,
    version=configuracion.VERSION,
    docs_url="/docs" if _publica else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _publica else None,
)


@aplicacion.middleware("http")
async def cabeceras_de_proteccion(peticion, siguiente):
    respuesta = await siguiente(peticion)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "same-origin"
    respuesta.headers["ngrok-skip-browser-warning"] = "true"
    if configuracion.es_produccion:
        respuesta.headers["Strict-Transport-Security"] = "max-age=31536000"
    return respuesta


aplicacion.add_middleware(
    CORSMiddleware,
    allow_origins=configuracion.ORIGENES_PERMITIDOS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from geology.rutas import cargue, consulta, cuentas, instrumentos, ubicacion, unidades  # noqa: E402

aplicacion.include_router(cuentas.router)
aplicacion.include_router(unidades.router)
aplicacion.include_router(cargue.router)
aplicacion.include_router(ubicacion.router)
aplicacion.include_router(instrumentos.router)
aplicacion.include_router(consulta.router)

# La interfaz se sirve desde el mismo servidor.
INTERFAZ = Path(__file__).parent / "interfaz"
if INTERFAZ.exists():
    aplicacion.mount("/recursos", StaticFiles(directory=INTERFAZ), name="recursos")

    @aplicacion.get("/app", include_in_schema=False)
    def interfaz():
        return FileResponse(INTERFAZ / "index.html")

    @aplicacion.get("/", include_in_schema=False)
    def raiz():
        return RedirectResponse("/app")


@aplicacion.on_event("startup")
def _al_arrancar() -> None:
    """Crea las tablas que falten, completa la estructura y avisa de lo que falta para publicar."""
    try:
        crear_tablas()
    except Exception as e:
        print(f"AVISO. No se pudieron crear las tablas todavía: {e}")
    try:
        from geology.nucleo.estructura import aplicar
        for linea in aplicar():
            print("Estructura:", linea)
    except Exception as e:
        print(f"AVISO. No se pudieron aplicar los ajustes de estructura: {e}")

    from geology.nucleo.pases import llave_configurada
    if not llave_configurada():
        print("\n" + "!" * 78)
        print("ATENCIÓN. GEOLOGY_CLAVE no está configurada en el archivo .env.")
        print("Las sesiones se firman con una llave que cambia en cada reinicio.")
        print("!" * 78 + "\n")
    if not configuracion.es_produccion:
        print("AVISO. GEOLOGY_ENTORNO=desarrollo: /docs está abierto. En internet use produccion.")


@aplicacion.get("/estado", tags=["Estado"])
def estado() -> dict:
    """Comprueba que PostgreSQL y el intermediario de mensajes responden."""
    base_de_datos = verificar_conexion()
    try:
        intermediario = bool(celery_app.connection().ensure_connection(max_retries=1))
    except Exception:
        intermediario = False
    return {
        "plataforma": configuracion.NOMBRE,
        "version": configuracion.VERSION,
        "entorno": configuracion.ENTORNO,
        "base_de_datos": "disponible" if base_de_datos else "sin conexión",
        "intermediario_de_mensajes": "disponible" if intermediario else "sin conexión",
        "estado": "operativo" if base_de_datos and intermediario else "degradado",
    }
