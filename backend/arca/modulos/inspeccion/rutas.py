"""Inspección de calidad por lote · API: plan de muestreo, lotes, inspecciones, revisión de la muestra, cierre y acta."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from arca.api.deps import Contexto, requiere
from arca.modulos.inspeccion import servicios
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/inspeccion", tags=["Inspección de calidad por lote"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Inspector = Annotated[Contexto, Depends(requiere(Permiso.CALIDAD))]
Director = Annotated[Contexto, Depends(requiere(Permiso.PROYECTOS))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Plan(BaseModel):
    unidad: str
    metodo: str
    porcentaje: float = 0
    minimo: int = 0
    tabla: list[dict[str, int]] = Field(default_factory=list, max_length=60)
    aceptacion: dict[str, int]
    defectos: list[dict[str, str]] = Field(min_length=1, max_length=80)
    frente: str = ""
    exigir_para_entrega: bool = True
    motivo: str = Field(min_length=5, max_length=500)


class Inicio(BaseModel):
    lote: str = ""
    semilla: int | None = Field(default=None, ge=1, le=999_999)


class Defecto(BaseModel):
    codigo: str
    nota: str = ""
    pagina: int | None = None


class Revision(BaseModel):
    defectos: list[Defecto] = Field(default_factory=list, max_length=50)


class Cierre(BaseModel):
    observaciones: str = Field(default="", max_length=2000)


class Anulacion(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


@rutas.get("/plan")
def ver_plan(proyecto_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    return servicios.ver_plan(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.put("/plan")
def guardar_plan(proyecto_id: uuid.UUID, datos: Plan, ctx: Director) -> dict[str, Any]:
    p = obtener_proyecto(ctx, proyecto_id)
    servicios.guardar_plan(ctx, p, datos.model_dump(exclude={"motivo"}), datos.motivo)
    return servicios.ver_plan(ctx, p)


@rutas.get("/lotes")
def lotes(proyecto_id: uuid.UUID, ctx: Lector) -> list[dict[str, Any]]:
    return servicios.lotes(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.get("/inspecciones")
def listar(proyecto_id: uuid.UUID, ctx: Lector) -> list[dict[str, Any]]:
    return servicios.listar(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.post("/inspecciones", status_code=status.HTTP_201_CREATED)
def iniciar(proyecto_id: uuid.UUID, datos: Inicio, ctx: Inspector) -> dict[str, Any]:
    p = obtener_proyecto(ctx, proyecto_id)
    i = servicios.iniciar(ctx, p, datos.lote.strip(), datos.semilla)
    return servicios.detalle(ctx, p, i.id)


@rutas.get("/inspecciones/{inspeccion_id}")
def detalle(proyecto_id: uuid.UUID, inspeccion_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    return servicios.detalle(ctx, obtener_proyecto(ctx, proyecto_id), inspeccion_id)


@rutas.put("/inspecciones/{inspeccion_id}/items/{item_id}")
def revisar(proyecto_id: uuid.UUID, inspeccion_id: uuid.UUID, item_id: uuid.UUID, datos: Revision, ctx: Inspector) -> dict[str, Any]:
    p = obtener_proyecto(ctx, proyecto_id)
    servicios.revisar(ctx, p, inspeccion_id, item_id, [d.model_dump() for d in datos.defectos])
    return servicios.detalle(ctx, p, inspeccion_id)


@rutas.post("/inspecciones/{inspeccion_id}/cerrar")
def cerrar(proyecto_id: uuid.UUID, inspeccion_id: uuid.UUID, datos: Cierre, ctx: Inspector) -> dict[str, Any]:
    p = obtener_proyecto(ctx, proyecto_id)
    servicios.cerrar(ctx, p, inspeccion_id, datos.observaciones)
    return servicios.detalle(ctx, p, inspeccion_id)


@rutas.post("/inspecciones/{inspeccion_id}/anular")
def anular(proyecto_id: uuid.UUID, inspeccion_id: uuid.UUID, datos: Anulacion, ctx: Director) -> dict[str, Any]:
    p = obtener_proyecto(ctx, proyecto_id)
    servicios.anular(ctx, p, inspeccion_id, datos.motivo)
    return servicios.detalle(ctx, p, inspeccion_id)


@rutas.get("/inspecciones/{inspeccion_id}/acta")
def acta(proyecto_id: uuid.UUID, inspeccion_id: uuid.UUID, ctx: Lector) -> Response:
    datos, nombre = servicios.acta(ctx, obtener_proyecto(ctx, proyecto_id), inspeccion_id)
    return Response(datos, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
