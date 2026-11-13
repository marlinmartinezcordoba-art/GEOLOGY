"""M08 · API del inventario FUID de un proyecto."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from arca.api.deps import Contexto, requiere
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.modulos.m08_inventarios import fuid, servicios
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/inventario", tags=["M08 · Inventario FUID"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Gestor = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO))]


class LoteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre_archivo: str
    hoja: str | None
    fila_encabezado: int
    encabezados: list[str]
    mapeo: dict[str, int]
    estado: str
    total_filas: int
    filas_validas: int
    filas_con_error: int
    filas_integradas: int
    motivo_estado: str | None
    creado_en: datetime


class FilaSalida(BaseModel):
    numero_fila: int
    original: list[str]
    normalizado: dict[str, Any]
    errores: list[str]
    avisos: list[str]
    unidad_id: uuid.UUID | None


class Mapeo(BaseModel):
    mapeo: dict[str, int]


class MotivoOpcional(BaseModel):
    motivo: str | None = None


class Motivo(BaseModel):
    motivo: str = Field(min_length=5)


class UnidadSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    identificador: str
    numero_orden: str | None
    codigo_serie: str | None
    nombre: str
    fecha_inicial: date | None
    fecha_final: date | None
    caja: str | None
    carpeta: str | None
    tomo: str | None
    otro: str | None
    folios: int | None
    soporte: str
    notas: str | None


class PaginaUnidades(BaseModel):
    total: int
    unidades: list[UnidadSalida]


@rutas.get("/campos")
def campos(_: Lector) -> dict[str, str]:
    """Campos que ARCA reconoce en un FUID, para el mapeo de columnas."""
    return fuid.NOMBRES_CAMPO


@rutas.get("/lotes", response_model=list[LoteSalida])
def listar_lotes(proyecto_id: uuid.UUID, ctx: Lector):
    return servicios.lotes(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.post("/lotes", status_code=status.HTTP_201_CREATED, response_model=LoteSalida)
async def importar(proyecto_id: uuid.UUID, ctx: Gestor, archivo: UploadFile = File(...)):
    proyecto = obtener_proyecto(ctx, proyecto_id)
    return servicios.importar(ctx, proyecto, await archivo.read(), archivo.filename or "fuid.xlsx")


@rutas.get("/lotes/{lote_id}", response_model=LoteSalida)
def ver_lote(proyecto_id: uuid.UUID, lote_id: uuid.UUID, ctx: Lector):
    return servicios.obtener_lote(ctx, obtener_proyecto(ctx, proyecto_id), lote_id)


@rutas.get("/lotes/{lote_id}/filas", response_model=list[FilaSalida])
def filas(proyecto_id: uuid.UUID, lote_id: uuid.UUID, ctx: Lector, solo_errores: bool = False, desde: int = 0, limite: int = Query(default=200, le=1000)):
    lote = servicios.obtener_lote(ctx, obtener_proyecto(ctx, proyecto_id), lote_id)
    return [servicios.resumen_fila(f) for f in servicios.filas(ctx, lote, solo_errores, limite, desde)]


@rutas.put("/lotes/{lote_id}/mapeo", response_model=LoteSalida)
def remapear(proyecto_id: uuid.UUID, lote_id: uuid.UUID, datos: Mapeo, ctx: Gestor):
    proyecto = obtener_proyecto(ctx, proyecto_id)
    return servicios.remapear(ctx, proyecto, servicios.obtener_lote(ctx, proyecto, lote_id), datos.mapeo)


@rutas.post("/lotes/{lote_id}/integrar", response_model=LoteSalida)
def integrar(proyecto_id: uuid.UUID, lote_id: uuid.UUID, datos: MotivoOpcional, ctx: Gestor):
    proyecto = obtener_proyecto(ctx, proyecto_id)
    return servicios.integrar(ctx, proyecto, servicios.obtener_lote(ctx, proyecto, lote_id), datos.motivo)


@rutas.post("/lotes/{lote_id}/descartar", response_model=LoteSalida)
def descartar(proyecto_id: uuid.UUID, lote_id: uuid.UUID, datos: Motivo, ctx: Gestor):
    proyecto = obtener_proyecto(ctx, proyecto_id)
    return servicios.descartar(ctx, proyecto, servicios.obtener_lote(ctx, proyecto, lote_id), datos.motivo)


@rutas.get("/unidades", response_model=PaginaUnidades)
def unidades(proyecto_id: uuid.UUID, ctx: Lector, q: str | None = None, desplazamiento: int = 0, limite: int = Query(default=100, le=500)):
    total, lista = servicios.unidades(ctx, obtener_proyecto(ctx, proyecto_id), q, limite, desplazamiento)
    return PaginaUnidades(total=total, unidades=lista)
