"""Paquete de entrega · API: pedir un paquete (se arma en la cola), ver los paquetes y descargar el ZIP."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from arca.api.deps import Contexto, requiere
from arca.modulos.entrega import servicios
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/entrega", tags=["Paquete de entrega"])
Expedidor = Annotated[Contexto, Depends(requiere(Permiso.EXPEDIR))]
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]


class Solicitud(BaseModel):
    cajas: list[str] = Field(default_factory=list, max_length=500)
    lote: str = ""
    solo_listos: bool = True


@rutas.post("/paquetes", status_code=status.HTTP_202_ACCEPTED)
def solicitar(proyecto_id: uuid.UUID, datos: Solicitud, ctx: Expedidor) -> dict[str, Any]:
    p = servicios.solicitar(ctx, obtener_proyecto(ctx, proyecto_id), datos.cajas, datos.lote.strip(), datos.solo_listos)
    return {"id": p.id, "numero": p.numero, "estado": p.estado, "unidades": p.unidades, "pendientes": len(p.pendientes)}


@rutas.get("/paquetes")
def listar(proyecto_id: uuid.UUID, ctx: Lector) -> list[dict[str, Any]]:
    return servicios.listar(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.get("/paquetes/{paquete_id}/archivo")
def descargar(proyecto_id: uuid.UUID, paquete_id: uuid.UUID, ctx: Expedidor) -> Response:
    datos, a = servicios.archivo(ctx, obtener_proyecto(ctx, proyecto_id), paquete_id)
    return Response(datos, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{a.nombre_original}"', "X-SHA256": a.sha256})
