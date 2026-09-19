"""
Punto de entrada de la interfaz de programación de aplicaciones de KUSTOS.

Ejecución local:
    uvicorn app.main:app --reload
Documentación interactiva:
    http://localhost:8000/docs
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.celery_app import celery_app
from app.core.config import configuracion
from app.core.database import crear_tablas, verificar_conexion

# La documentación interactiva es un mapa completo de la interfaz de programación: rutas,
# campos y formatos. Es utilísima mientras se construye y es un regalo para quien quiera
# atacar la plataforma. Por eso solo se publica en desarrollo. En producción responde 404.
_publica = not configuracion.es_produccion

app = FastAPI(
    title=configuracion.NOMBRE,
    description=configuracion.DESCRIPCION,
    version=configuracion.VERSION,
    docs_url="/docs" if _publica else None,
    redoc_url="/redoc" if _publica else None,
    openapi_url="/openapi.json" if _publica else None,
)


@app.middleware("http")
async def cabeceras_de_seguridad(peticion, siguiente):
    """Cabeceras mínimas para una plataforma accesible desde fuera de la oficina."""
    respuesta = await siguiente(peticion)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "same-origin"
    respuesta.headers["ngrok-skip-browser-warning"] = "true"
    if configuracion.es_produccion:
        respuesta.headers["Strict-Transport-Security"] = "max-age=31536000"
    return respuesta

app.add_middleware(
    CORSMiddleware,
    allow_origins=configuracion.ORIGENES_PERMITIDOS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import archivos, expedientes, instrumentos, reubicacion, usuarios   # noqa: E402

app.include_router(usuarios.router)
app.include_router(expedientes.router)
app.include_router(archivos.router)
app.include_router(reubicacion.router)
app.include_router(instrumentos.router)
# Los demás enrutadores se registran aquí a medida que se construyan.


# La interfaz se sirve desde el mismo servidor, de modo que no hay orígenes cruzados
# que configurar ni direcciones absolutas que mantener.
WEB = Path(__file__).parent / "web"
if WEB.exists():
    app.mount("/estatico", StaticFiles(directory=WEB), name="estatico")

    @app.get("/interfaz", include_in_schema=False)
    def interfaz():
        return FileResponse(WEB / "index.html")


@app.on_event("startup")
def _al_arrancar() -> None:
    """Crea las tablas que falten y avisa de lo que falta para publicar con seguridad."""
    try:
        crear_tablas()
    except Exception as e:      # si PostgreSQL aún no responde, el healthcheck lo dirá
        print(f"AVISO. No se pudieron crear las tablas todavía: {e}")

    # Ajustes de estructura sobre tablas que ya existen. crear_tablas no los hace, y sin esto
    # habría que borrar la base y volver a cargarlo todo cada vez que cambia una columna.
    try:
        from app.core.migraciones import aplicar
        for linea in aplicar():
            print("Estructura:", linea)
    except Exception as e:
        print(f"AVISO. No se pudieron aplicar los ajustes de estructura: {e}")

    from app.core.seguridad import llave_configurada
    if not llave_configurada():
        print("\n" + "!" * 78)
        print("ATENCIÓN. CLAVE_SECRETA no está configurada en el archivo .env.")
        print("Las sesiones se firman con una llave que cambia en cada reinicio, así que todo")
        print("el mundo tendrá que volver a ingresar cada vez que el servidor se reinicie.")
        print("Escríbala antes de publicar la plataforma fuera de la oficina.")
        print("!" * 78 + "\n")
    if not configuracion.es_produccion:
        print("AVISO. ENTORNO=desarrollo, así que /docs está abierto a quien alcance el servidor.")
        print("       Si la plataforma es accesible desde internet, ponga ENTORNO=produccion.")


@app.get("/", tags=["Estado"])
def raiz() -> dict:
    """Endpoint de prueba. Confirma que el servidor está en pie."""
    return {
        "sistema": configuracion.NOMBRE,
        "version": configuracion.VERSION,
        "entorno": configuracion.ENTORNO,
        "mensaje": "KUSTOS en línea",
        "documentacion": "/docs",
        "interfaz": "/interfaz",
    }


@app.get("/salud", tags=["Estado"])
def salud() -> dict:
    """Comprueba que PostgreSQL y el intermediario de mensajes responden."""
    base_de_datos = verificar_conexion()
    try:
        intermediario = bool(celery_app.connection().ensure_connection(max_retries=1))
    except Exception:
        intermediario = False
    return {
        "base_de_datos": "disponible" if base_de_datos else "sin conexión",
        "intermediario_de_mensajes": "disponible" if intermediario else "sin conexión",
        "estado": "operativo" if base_de_datos and intermediario else "degradado",
    }
