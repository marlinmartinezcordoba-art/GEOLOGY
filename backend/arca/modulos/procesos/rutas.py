"""Procesos por lote · API: qué lleva cada lote de trabajo."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from arca.api.deps import Contexto, requiere
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.modulos.procesos import servicios
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}", tags=["Procesos por lote"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Director = Annotated[Contexto, Depends(requiere(Permiso.PROYECTOS))]


class Configuracion(BaseModel):
    lote: str = Field(default="", max_length=80, description="Vacío = todo el proyecto")
    hoja_control: bool
    isadg: bool
    motivo: str = Field(min_length=5)



@rutas.get("/procesos-por-lote")
def lotes(proyecto_id: uuid.UUID, ctx: Lector) -> list[dict[str, Any]]:
    """El proyecto y cada lote de la base de cajas: si lleva hoja de control, descripción ISAD(G) o ambas."""
    return servicios.lotes(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.put("/procesos-por-lote")
def configurar(proyecto_id: uuid.UUID, datos: Configuracion, ctx: Director) -> list[dict[str, Any]]:
    p = obtener_proyecto(ctx, proyecto_id)
    servicios.configurar(ctx, p, datos.lote, datos.hoja_control, datos.isadg, datos.motivo)
    return servicios.lotes(ctx, p)
