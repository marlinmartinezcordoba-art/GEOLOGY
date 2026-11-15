"""Aplicación ARCA: API versionada en /api/v1 y estado del servicio en /estado."""

import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from arca.modulos.descripcion.rutas import rutas as descripcion
from arca.modulos.disposicion.rutas import rutas as disposicion
from arca.modulos.entrega.rutas import rutas as entrega
from arca.modulos.entregables.rutas import expedicion, plantillas
from arca.modulos.flujo.rutas import rutas as flujo
from arca.modulos.historias.rutas import rutas as historias
from arca.modulos.hoja_control.rutas import rutas as hojas_control
from arca.modulos.inspeccion.rutas import rutas as inspeccion
from arca.modulos.m01_organizaciones.rutas import organizacion, plataforma
from arca.modulos.m02_usuarios.rutas import auth, roles, usuarios
from arca.modulos.m03_configuracion.rutas import rutas as configuracion
from arca.modulos.m04_instrumentos.rutas import clasificacion_rutas as clasificacion
from arca.modulos.m04_instrumentos.rutas import rutas as instrumentos
from arca.modulos.m06_proyectos.rutas import rutas as proyectos
from arca.modulos.m08_inventarios.rutas import rutas as inventario
from arca.modulos.m10_digitalizacion.rutas import rutas as digitalizacion
from arca.modulos.m13_ocr.rutas import rutas as ocr
from arca.modulos.m23_consulta.rutas import rutas as consulta
from arca.modulos.m24_productividad.rutas import powerbi
from arca.modulos.m24_productividad.rutas import rutas as productividad
from arca.modulos.m25_auditoria.rutas import rutas as auditoria
from arca.modulos.m28_operacion.rutas import rutas as operacion
from arca.modulos.procesos.rutas import rutas as procesos
from arca.modulos.transferencias.rutas import rutas as transferencias
from arca.nucleo.config import ajustes
from arca.nucleo.errores import registrar_manejadores

_CORRELACION_VALIDA = re.compile(r"^[A-Za-z0-9\-_.]{8,64}$")


@asynccontextmanager
async def _vida(app: FastAPI):
    """En local, un hilo atiende la cola del flujo automático (D-39). En producción va en un proceso aparte."""
    from arca.modulos.flujo.trabajador import Hilo, encendido  # noqa: PLC0415

    hilo = Hilo() if encendido() else None
    if hilo:
        hilo.iniciar()
    yield
    if hilo:
        hilo.detener()


def crear_app() -> FastAPI:
    a = ajustes()
    publica_docs = a.entorno in {"local", "test", "staging"}
    app = FastAPI(
        title="ARCA",
        version=a.version,
        description="Plataforma SaaS de gestión archivística, digitalización masiva y automatización documental. Etapa 1 (plataforma base) e Incremento 2 (inventario FUID, digitalización y calidad).",
        docs_url="/docs" if publica_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if publica_docs else None,
        lifespan=_vida,
    )
    app.add_middleware(CORSMiddleware, allow_origins=a.origenes_permitidos, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def correlacion(request: Request, call_next):
        """Cada petición lleva un identificador que viaja a la auditoría, a los errores y a la respuesta."""
        recibido = request.headers.get("x-correlation-id", "")
        request.state.correlacion_id = recibido if _CORRELACION_VALIDA.match(recibido) else uuid.uuid4().hex
        respuesta = await call_next(request)
        respuesta.headers["X-Correlation-ID"] = request.state.correlacion_id
        return respuesta

    registrar_manejadores(app)
    app.include_router(operacion)
    for router in (auth, plataforma, organizacion, usuarios, roles, configuracion, proyectos, instrumentos, clasificacion, transferencias, disposicion, hojas_control, historias, ocr, procesos, descripcion, consulta, flujo, inventario, digitalizacion, inspeccion, plantillas, expedicion, entrega, productividad, powerbi, auditoria):
        app.include_router(router, prefix="/api/v1")
    return app


app = crear_app()
