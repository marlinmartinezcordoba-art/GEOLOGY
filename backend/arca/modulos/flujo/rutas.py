"""Flujo automático · API: tablero del proyecto, unidades por etapa, errores y procesar una tanda ahora."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from arca.api.deps import Contexto, requiere
from arca.modulos.flujo import servicios, trabajador
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/flujo", tags=["Flujo automático"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Operario = Annotated[Contexto, Depends(requiere(Permiso.CAPTURAR))]


@rutas.get("")
def tablero(proyecto_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    return servicios.resumen(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.get("/unidades")
def unidades(proyecto_id: uuid.UUID, ctx: Lector, etapa: str | None = None, desplazamiento: int = Query(default=0, ge=0), limite: int = Query(default=100, le=500)) -> dict[str, Any]:
    total, filas = servicios.unidades(ctx, obtener_proyecto(ctx, proyecto_id), etapa, desplazamiento, limite)
    return {"total": total, "filas": filas}


@rutas.get("/errores")
def errores(proyecto_id: uuid.UUID, ctx: Lector) -> list[dict[str, Any]]:
    return servicios.errores(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.post("/iniciar")
def iniciar(proyecto_id: uuid.UUID, ctx: Operario) -> dict[str, int]:
    """Pone en cola las unidades digitalizadas que no están listas (por ejemplo, lo cargado antes de existir el flujo)."""
    return {"encoladas": servicios.iniciar(ctx, obtener_proyecto(ctx, proyecto_id))}


@rutas.post("/procesar")
def procesar(proyecto_id: uuid.UUID, ctx: Operario, limite: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
    """Procesa ya una tanda de la cola del proyecto (sin esperar al trabajador)."""
    p = obtener_proyecto(ctx, proyecto_id)
    ctx.db.commit()
    n = trabajador.procesar(limite=limite, proyecto_id=p.id)
    ctx.db.expire_all()
    return {"procesados": n, **servicios.resumen(ctx, p)}


@rutas.post("/errores/{trabajo_id}/reintentar")
def reintentar(proyecto_id: uuid.UUID, trabajo_id: uuid.UUID, ctx: Operario) -> dict[str, str]:
    servicios.reintentar(ctx, obtener_proyecto(ctx, proyecto_id), trabajo_id)
    return {"estado": "pendiente"}
