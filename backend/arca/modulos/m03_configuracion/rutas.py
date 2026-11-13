"""M03 · API de parámetros versionados."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field

from arca.api.deps import Contexto, requiere
from arca.modulos.m03_configuracion import servicios
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/configuracion", tags=["M03 · Configuración"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.CONFIGURACION_LEER))]
Gestor = Annotated[Contexto, Depends(requiere(Permiso.CONFIGURACION))]


class ParametroNuevo(BaseModel):
    clave: str = Field(min_length=3, max_length=120)
    valor: Any
    vigente_desde: datetime | None = Field(default=None, description="Vacío = desde ahora. No puede ser pasada.")
    proyecto_id: uuid.UUID | None = None
    motivo: str = Field(min_length=5)


class ParametroSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clave: str
    version: int
    valor: Any
    vigente_desde: datetime
    proyecto_id: uuid.UUID | None
    motivo: str
    creado_en: datetime
    creado_por: uuid.UUID | None


@rutas.get("/parametros/conocidos")
def parametros_conocidos(_: Lector) -> dict[str, str]:
    """Parámetros que ARCA ya interpreta, con su significado."""
    return servicios.CONOCIDOS


@rutas.get("/parametros", response_model=list[ParametroSalida])
def listar_vigentes(
    ctx: Lector, proyecto_id: uuid.UUID | None = None, fecha: datetime | None = Query(default=None, description="Ver lo que regía en esa fecha")
):
    return servicios.vigentes(ctx.db, ctx.tenant_id, proyecto_id, fecha)


@rutas.get("/parametros/{clave}/historial", response_model=list[ParametroSalida])
def historial(clave: str, ctx: Lector, proyecto_id: uuid.UUID | None = None):
    return servicios.historial(ctx.db, ctx.tenant_id, clave, proyecto_id)


@rutas.post("/parametros", status_code=status.HTTP_201_CREATED, response_model=ParametroSalida)
def publicar(datos: ParametroNuevo, ctx: Gestor):
    return servicios.publicar(ctx.db, ctx, datos.clave, datos.valor, datos.motivo, datos.vigente_desde, datos.proyecto_id)
