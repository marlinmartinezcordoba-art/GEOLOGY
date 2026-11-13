"""M25 · Consulta y verificación de la auditoría de la organización activa. Consultarla también se audita."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from arca.api.deps import Contexto, requiere
from arca.modelos import EventoAuditoria
from arca.modulos.m25_auditoria.servicios import verificar_integridad
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/auditoria", tags=["M25 · Auditoría"])
Auditor = Annotated[Contexto, Depends(requiere(Permiso.AUDITORIA))]


class EventoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    secuencia: int
    fecha: datetime
    usuario_id: uuid.UUID | None
    usuario_nombre: str
    accion: str
    objeto: str
    objeto_id: uuid.UUID | None
    detalle: str
    motivo: str | None
    cambios: dict[str, Any] | None
    resultado: str
    ip: str | None
    correlacion_id: str | None
    hash_evento: str


@rutas.get("/eventos", response_model=list[EventoSalida])
def eventos(
    ctx: Auditor,
    accion: str | None = None,
    objeto: str | None = None,
    objeto_id: uuid.UUID | None = None,
    correlacion_id: str | None = None,
    antes_de: int | None = Query(default=None, description="Paginación: secuencias menores a esta"),
    limite: int = Query(default=100, ge=1, le=500),
):
    consulta = select(EventoAuditoria).where(EventoAuditoria.tenant_id == ctx.tenant_id)
    for columna, valor in (
        (EventoAuditoria.accion, accion.upper() if accion else None),
        (EventoAuditoria.objeto, objeto),
        (EventoAuditoria.objeto_id, objeto_id),
        (EventoAuditoria.correlacion_id, correlacion_id),
    ):
        if valor is not None:
            consulta = consulta.where(columna == valor)
    if antes_de is not None:
        consulta = consulta.where(EventoAuditoria.secuencia < antes_de)
    resultado = list(ctx.db.scalars(consulta.order_by(EventoAuditoria.secuencia.desc()).limit(limite)))
    ctx.auditar(accion="CONSULTAR_AUDITORIA", objeto="Auditoria", detalle=f"{len(resultado)} eventos")
    ctx.db.commit()
    return resultado


@rutas.get("/verificar")
def verificar(ctx: Auditor) -> dict[str, Any]:
    resultado = verificar_integridad(ctx.db, ctx.tenant_id)
    ctx.auditar(
        accion="VERIFICAR_AUDITORIA",
        objeto="Auditoria",
        detalle="Íntegra" if resultado["integra"] else f"ALERTA: {resultado['problema']}",
        resultado="exito" if resultado["integra"] else "error",
    )
    ctx.db.commit()
    return resultado
