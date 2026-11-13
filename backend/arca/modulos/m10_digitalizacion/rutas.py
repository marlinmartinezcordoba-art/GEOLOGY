"""M10 y M11 · API de digitalización: perfil del proyecto, carga de carpetas, bandeja de calidad y visor."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from arca.api.deps import Contexto, requiere
from arca.modulos.m03_configuracion.servicios import publicar
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.modulos.m10_digitalizacion import perfil, servicios
from arca.nucleo.errores import DatosInvalidos
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/digitalizacion", tags=["M10 · Digitalización y calidad"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Cargador = Annotated[Contexto, Depends(requiere(Permiso.CAPTURAR))]
Revisor = Annotated[Contexto, Depends(requiere(Permiso.CALIDAD))]
Director = Annotated[Contexto, Depends(requiere(Permiso.PROYECTOS))]

MAX_ARCHIVOS_POR_ENVIO = 200


class PerfilSalida(BaseModel):
    perfil: dict[str, Any]
    version: int | None
    por_defecto: dict[str, Any]
    hallazgos: dict[str, str]


class PerfilNuevo(BaseModel):
    perfil: dict[str, Any]
    motivo: str = Field(min_length=5)
    vigente_desde: datetime | None = None


class RecursoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    unidad_id: uuid.UUID | None
    ruta_original: str
    modalidad: str
    parte: int
    pagina: int | None
    paginas: int
    ficha: dict[str, Any]
    hallazgos: list[dict[str, Any]]
    estado: str
    perfil_version: int | None
    reemplaza_id: uuid.UUID | None
    decidido_por: uuid.UUID | None
    motivo_decision: str | None
    creado_en: datetime
    unidad_identificador: str | None = None


class PaginaRecursos(BaseModel):
    total: int
    recursos: list[RecursoSalida]


class Decision(BaseModel):
    decision: str = Field(description="aprobar | recaptura")
    motivo: str = Field(min_length=5)


class Asignacion(BaseModel):
    unidad_id: uuid.UUID
    parte: int = Field(default=0, ge=0)
    pagina: int | None = Field(default=None, ge=0)
    motivo: str = Field(min_length=5)


def _salida(r) -> RecursoSalida:
    s = RecursoSalida.model_validate(r)
    s.unidad_identificador = r.unidad.identificador if r.unidad else None
    return s


@rutas.get("/perfil", response_model=PerfilSalida)
def ver_perfil(proyecto_id: uuid.UUID, ctx: Lector):
    reglas, version = servicios.perfil_de(ctx, obtener_proyecto(ctx, proyecto_id))
    return PerfilSalida(perfil=reglas, version=version, por_defecto=perfil.POR_DEFECTO, hallazgos=perfil.HALLAZGOS)


@rutas.put("/perfil", response_model=PerfilSalida)
def configurar_perfil(proyecto_id: uuid.UUID, datos: PerfilNuevo, ctx: Director):
    """Publica una versión nueva del perfil (parámetro versionado del proyecto, con vigencia y motivo)."""
    proyecto = obtener_proyecto(ctx, proyecto_id)
    publicar(ctx.db, ctx, perfil.CLAVE, datos.perfil, datos.motivo, datos.vigente_desde, proyecto.id)
    reglas, version = servicios.perfil_de(ctx, proyecto)
    return PerfilSalida(perfil=reglas, version=version, por_defecto=perfil.POR_DEFECTO, hallazgos=perfil.HALLAZGOS)


@rutas.post("/archivos")
async def cargar(proyecto_id: uuid.UUID, ctx: Cargador, archivos: list[UploadFile] = File(...), rutas_relativas: list[str] | None = Form(default=None)) -> list[dict[str, Any]]:
    """Recibe archivos de una carpeta. `rutas_relativas[i]` es la ruta de `archivos[i]` dentro de la carpeta escogida."""
    proyecto = obtener_proyecto(ctx, proyecto_id)
    if len(archivos) > MAX_ARCHIVOS_POR_ENVIO:
        raise DatosInvalidos(f"Envíe como máximo {MAX_ARCHIVOS_POR_ENVIO} archivos por vez; la pantalla los reparte sola")
    if rutas_relativas and len(rutas_relativas) != len(archivos):
        raise DatosInvalidos("Cada archivo debe llegar con su ruta dentro de la carpeta")
    lote = [((rutas_relativas[i] if rutas_relativas else None) or a.filename or f"archivo-{i}", await a.read()) for i, a in enumerate(archivos)]
    return servicios.recibir(ctx, proyecto, lote)


@rutas.get("/resumen")
def resumen(proyecto_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    return servicios.resumen(ctx, obtener_proyecto(ctx, proyecto_id))


class UnidadAvance(BaseModel):
    id: uuid.UUID
    identificador: str
    nombre: str
    folios: int | None
    caja: str | None
    carpeta: str | None
    archivos: int
    imagenes: int
    estado: str
    alertas: list[dict[str, Any]]


class PaginaUnidades(BaseModel):
    total: int
    unidades: list[UnidadAvance]


@rutas.get("/unidades", response_model=PaginaUnidades)
def unidades(proyecto_id: uuid.UUID, ctx: Lector, filtro: str | None = Query(default=None, description="sin_imagenes | en_revision | recaptura | aprobada | con_alertas"), desplazamiento: int = 0, limite: int = Query(default=100, le=500)):
    total, filas = servicios.unidades(ctx, obtener_proyecto(ctx, proyecto_id), filtro, limite, desplazamiento)
    return PaginaUnidades(total=total, unidades=filas)


@rutas.get("/archivos", response_model=PaginaRecursos)
def listar(proyecto_id: uuid.UUID, ctx: Lector, estado: str | None = None, unidad_id: uuid.UUID | None = None, desplazamiento: int = 0, limite: int = Query(default=100, le=500)):
    total, lista = servicios.listar(ctx, obtener_proyecto(ctx, proyecto_id), estado, unidad_id, limite, desplazamiento)
    return PaginaRecursos(total=total, recursos=[_salida(r) for r in lista])


@rutas.get("/archivos/{recurso_id}/contenido")
def ver_contenido(proyecto_id: uuid.UUID, recurso_id: uuid.UUID, ctx: Lector):
    """El original, verificado contra su huella antes de entregarlo. Ver también queda en la auditoría."""
    proyecto = obtener_proyecto(ctx, proyecto_id)
    recurso = servicios.obtener(ctx, proyecto, recurso_id)
    datos, archivo = servicios.contenido(ctx, recurso)
    ctx.auditar(accion="VER_ARCHIVO", objeto="RecursoDigital", objeto_id=recurso.id, detalle=recurso.ruta_original)
    ctx.db.commit()
    nombre = archivo.nombre_original.replace('"', "")
    return Response(content=datos, media_type=archivo.mime, headers={"Content-Disposition": f'inline; filename="{nombre}"', "X-Content-SHA256": archivo.sha256, "Cache-Control": "no-store"})


@rutas.post("/archivos/{recurso_id}/decidir", response_model=RecursoSalida)
def decidir(proyecto_id: uuid.UUID, recurso_id: uuid.UUID, datos: Decision, ctx: Revisor):
    proyecto = obtener_proyecto(ctx, proyecto_id)
    return _salida(servicios.decidir(ctx, proyecto, servicios.obtener(ctx, proyecto, recurso_id), datos.decision, datos.motivo))


@rutas.post("/archivos/{recurso_id}/asignar", response_model=RecursoSalida)
def asignar(proyecto_id: uuid.UUID, recurso_id: uuid.UUID, datos: Asignacion, ctx: Revisor):
    proyecto = obtener_proyecto(ctx, proyecto_id)
    return _salida(servicios.asignar(ctx, proyecto, servicios.obtener(ctx, proyecto, recurso_id), datos.unidad_id, datos.parte, datos.pagina, datos.motivo))
