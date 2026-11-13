"""M01 · API del operador de la plataforma (/plataforma) y perfil de la organización activa (/organizacion)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select

from arca.api.deps import Contexto, Operador, Origen, Sesion, requiere
from arca.modelos import EstadoOrganizacion, Organizacion, TipoIdentificacion
from arca.modulos.m01_organizaciones import servicios
from arca.modulos.m25_auditoria.servicios import verificar_integridad
from arca.nucleo.permisos import Permiso

plataforma = APIRouter(prefix="/plataforma", tags=["M01 · Plataforma SaaS"])
organizacion = APIRouter(prefix="/organizacion", tags=["M01 · Organización"])


class AdministradorInicial(BaseModel):
    correo: EmailStr
    nombre_completo: str = Field(min_length=3, max_length=200)


class OrganizacionNueva(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    razon_social: str = Field(min_length=2, max_length=300)
    tipo_identificacion: TipoIdentificacion = TipoIdentificacion.NIT
    identificacion: str = Field(min_length=3, max_length=40)
    zona_horaria: str = "America/Bogota"
    idioma: str = "es-CO"
    limites: dict[str, int] = Field(default_factory=dict)
    administrador: AdministradorInicial


class OrganizacionCambios(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=200)
    razon_social: str | None = Field(default=None, min_length=2, max_length=300)
    zona_horaria: str | None = None
    idioma: str | None = None
    limites: dict[str, int] | None = None
    motivo: str = Field(min_length=5)


class Motivo(BaseModel):
    motivo: str = Field(min_length=5, description="Por qué se hace el cambio; queda en la auditoría")


class OrganizacionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    razon_social: str
    tipo_identificacion: str
    identificacion: str
    estado: str
    motivo_estado: str | None
    zona_horaria: str
    idioma: str
    limites: dict
    creado_en: datetime


class OrganizacionCreada(BaseModel):
    organizacion: OrganizacionSalida
    administrador_correo: str
    clave_temporal: str | None = Field(description="Solo si el administrador es nuevo. Se muestra una única vez.")


class PerfilOrganizacion(OrganizacionSalida):
    uso: dict[str, int]


@plataforma.post("/organizaciones", status_code=status.HTTP_201_CREATED, response_model=OrganizacionCreada)
def crear_organizacion(datos: OrganizacionNueva, db: Sesion, operador: Operador, origen: Origen):
    org, admin, temporal = servicios.crear(db, operador, datos.model_dump(mode="json"), origen)
    return OrganizacionCreada(organizacion=OrganizacionSalida.model_validate(org), administrador_correo=admin.correo, clave_temporal=temporal)


@plataforma.get("/organizaciones", response_model=list[OrganizacionSalida])
def listar_organizaciones(db: Sesion, _: Operador):
    return db.scalars(select(Organizacion).order_by(Organizacion.nombre)).all()


@plataforma.get("/organizaciones/{organizacion_id}", response_model=OrganizacionSalida)
def ver_organizacion(organizacion_id: uuid.UUID, db: Sesion, _: Operador):
    return servicios.obtener(db, organizacion_id)


@plataforma.patch("/organizaciones/{organizacion_id}", response_model=OrganizacionSalida)
def editar_organizacion(organizacion_id: uuid.UUID, datos: OrganizacionCambios, db: Sesion, operador: Operador, origen: Origen):
    org = servicios.obtener(db, organizacion_id)
    nuevos = datos.model_dump(exclude_unset=True, exclude={"motivo"})
    return servicios.actualizar(db, operador, org, nuevos, datos.motivo, origen)


@plataforma.post("/organizaciones/{organizacion_id}/suspender", response_model=OrganizacionSalida)
def suspender_organizacion(organizacion_id: uuid.UUID, datos: Motivo, db: Sesion, operador: Operador, origen: Origen):
    org = servicios.obtener(db, organizacion_id)
    return servicios.cambiar_estado(db, operador, org, EstadoOrganizacion.SUSPENDIDA, datos.motivo, origen)


@plataforma.post("/organizaciones/{organizacion_id}/reactivar", response_model=OrganizacionSalida)
def reactivar_organizacion(organizacion_id: uuid.UUID, datos: Motivo, db: Sesion, operador: Operador, origen: Origen):
    org = servicios.obtener(db, organizacion_id)
    return servicios.cambiar_estado(db, operador, org, EstadoOrganizacion.ACTIVA, datos.motivo, origen)


@plataforma.get("/auditoria/verificar")
def verificar_auditoria_plataforma(db: Sesion, _: Operador):
    """Integridad de la cadena de eventos de la plataforma (no la de las organizaciones)."""
    return verificar_integridad(db, None)


@organizacion.get("", response_model=PerfilOrganizacion)
def perfil(ctx: Annotated[Contexto, Depends(requiere(Permiso.ORGANIZACION_LEER))]):
    datos = OrganizacionSalida.model_validate(ctx.organizacion).model_dump()
    return PerfilOrganizacion(**datos, uso=servicios.uso(ctx.db, ctx.organizacion))
