"""Historias laborales · API: configuración del proyecto, expedientes con sus alertas y el titular de cada uno."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from arca.api.deps import Contexto, requiere
from arca.modelos import ArchivoDigital
from arca.modulos.historias import servicios
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/historias", tags=["Historias laborales"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Elaborador = Annotated[Contexto, Depends(requiere(Permiso.HOJA_CONTROL))]
Director = Annotated[Contexto, Depends(requiere(Permiso.PROYECTOS))]
Expedidor = Annotated[Contexto, Depends(requiere(Permiso.EXPEDIR))]


class Config(BaseModel):
    activo: bool = True
    series: list[str] = Field(default_factory=list, max_length=50)
    tipos_obligatorios: list[str] = Field(default_factory=list, max_length=200)
    acceso_restringido: bool = True
    motivo: str = Field(min_length=5, max_length=500)


class Titular(BaseModel):
    tipo_documento: str | None = None
    numero_documento: str | None = None
    nombres: str | None = Field(default=None, max_length=300)
    cargo: str | None = Field(default=None, max_length=300)
    dependencia: str | None = Field(default=None, max_length=300)
    fecha_vinculacion: date | None = None
    fecha_retiro: date | None = None


@rutas.get("/config")
def ver_config(proyecto_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    return servicios.ver_config(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.put("/config")
def guardar_config(proyecto_id: uuid.UUID, datos: Config, ctx: Director) -> dict[str, Any]:
    p = obtener_proyecto(ctx, proyecto_id)
    servicios.guardar_config(ctx, p, datos.activo, datos.series, datos.tipos_obligatorios, datos.motivo, datos.acceso_restringido)
    return servicios.ver_config(ctx, p)


@rutas.get("/expedientes")
def expedientes(proyecto_id: uuid.UUID, ctx: Lector, alerta: str | None = None, desplazamiento: int = Query(default=0, ge=0), limite: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    return servicios.expedientes(ctx, obtener_proyecto(ctx, proyecto_id), alerta, desplazamiento, limite)


@rutas.post("/expedientes/proponer")
def proponer_todos(proyecto_id: uuid.UUID, ctx: Elaborador) -> dict[str, int]:
    """Propone el titular de todos los expedientes que no lo tengan confirmado (del FUID y del OCR)."""
    return {"propuestos": servicios.proponer_todos(ctx, obtener_proyecto(ctx, proyecto_id))}


@rutas.get("/expedientes/{unidad_id}")
def expediente(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    p = obtener_proyecto(ctx, proyecto_id)
    return servicios.revisar(ctx, p, servicios.unidad(ctx, p, unidad_id))


@rutas.put("/expedientes/{unidad_id}/titular")
def confirmar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, datos: Titular, ctx: Elaborador) -> dict[str, Any]:
    p = obtener_proyecto(ctx, proyecto_id)
    u = servicios.unidad(ctx, p, unidad_id)
    servicios.confirmar(ctx, p, u, datos.model_dump(exclude_unset=True))
    return servicios.revisar(ctx, p, u)


@rutas.post("/expedientes/{unidad_id}/lista-chequeo", status_code=status.HTTP_201_CREATED)
def lista_chequeo(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Expedidor) -> dict[str, Any]:
    """Expide la lista de chequeo en la plantilla vigente de la entidad. Se descarga como cualquier entregable."""
    p = obtener_proyecto(ctx, proyecto_id)
    e = servicios.expedir_lista_chequeo(ctx, p, servicios.unidad(ctx, p, unidad_id))
    a = ctx.db.get(ArchivoDigital, e.archivo_id)
    return {"expedicion_id": e.id, "elementos": e.elementos, "nombre_archivo": a.nombre_original, "sha256": a.sha256}
