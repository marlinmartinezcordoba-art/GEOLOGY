"""Alistamiento físico · API: plan de actividades, avance por caja, registro por caja o expediente y deshacer."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from arca.api.deps import Contexto, requiere
from arca.modulos.alistamiento import servicios
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/alistamiento", tags=["Alistamiento físico"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Operario = Annotated[Contexto, Depends(requiere(Permiso.CAPTURAR))]
Director = Annotated[Contexto, Depends(requiere(Permiso.PROYECTOS))]


class Plan(BaseModel):
    actividades: list[dict[str, Any]] = Field(min_length=1, max_length=40)
    exigir_para_entrega: bool = True
    motivo: str = Field(min_length=5, max_length=500)


class Registro(BaseModel):
    actividad: str
    cajas: list[str] = Field(default_factory=list, max_length=500)
    unidades: list[uuid.UUID] = Field(default_factory=list, max_length=2000)
    cantidades: dict[str, int] = Field(default_factory=dict)
    observacion: str = Field(default="", max_length=1000)


class Diagnostico(BaseModel):
    estado: str
    hallazgos: list[str] = Field(default_factory=list, max_length=20)
    folios_afectados: int | None = Field(default=None, ge=0)
    observacion: str = Field(default="", max_length=2000)


class Deshacer(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


@rutas.get("/plan")
def ver_plan(proyecto_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    return servicios.ver_plan(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.put("/plan")
def guardar_plan(proyecto_id: uuid.UUID, datos: Plan, ctx: Director) -> dict[str, Any]:
    p = obtener_proyecto(ctx, proyecto_id)
    servicios.guardar_plan(ctx, p, datos.actividades, datos.exigir_para_entrega, datos.motivo)
    return servicios.ver_plan(ctx, p)


@rutas.get("/cajas")
def cajas(proyecto_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    return servicios.cajas(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.get("/expedientes")
def expedientes(proyecto_id: uuid.UUID, ctx: Lector, caja: str = "") -> list[dict[str, Any]]:
    return servicios.expedientes(ctx, obtener_proyecto(ctx, proyecto_id), caja)


@rutas.post("/registrar")
def registrar(proyecto_id: uuid.UUID, datos: Registro, ctx: Operario) -> dict[str, int]:
    p = obtener_proyecto(ctx, proyecto_id)
    return {"registrados": servicios.registrar(ctx, p, datos.actividad, datos.cajas, datos.unidades, datos.cantidades, datos.observacion)}


@rutas.post("/expedientes/{unidad_id}/{actividad}/deshacer")
def deshacer(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, actividad: str, datos: Deshacer, ctx: Operario) -> dict[str, str]:
    servicios.deshacer(ctx, obtener_proyecto(ctx, proyecto_id), unidad_id, actividad, datos.motivo)
    return {"estado": "deshecho"}


@rutas.get("/diagnostico/catalogo")
def catalogo(proyecto_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    obtener_proyecto(ctx, proyecto_id)
    return servicios.catalogo_diagnostico()


@rutas.put("/expedientes/{unidad_id}/diagnostico")
def diagnosticar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, datos: Diagnostico, ctx: Operario) -> dict[str, Any] | None:
    p = obtener_proyecto(ctx, proyecto_id)
    return servicios.diagnostico_dict(servicios.diagnosticar(ctx, p, unidad_id, datos.estado, datos.hallazgos, datos.folios_afectados, datos.observacion))
