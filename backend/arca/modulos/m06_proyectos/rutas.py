"""M06 · API de proyectos, versiones de alcance, sedes y equipo."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field

from arca.api.deps import Contexto, requiere
from arca.modelos import EstadoProyecto
from arca.modulos.m06_proyectos import servicios
from arca.nucleo.errores import TransicionInvalida
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos", tags=["M06 · Proyectos"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.PROYECTOS_LEER))]
Gestor = Annotated[Contexto, Depends(requiere(Permiso.PROYECTOS))]


class ProyectoNuevo(BaseModel):
    codigo: str = Field(min_length=2, max_length=40)
    nombre: str = Field(min_length=3, max_length=300)
    entidad_cliente: str = Field(min_length=2, max_length=300)
    numero_contrato: str | None = Field(default=None, max_length=80)
    objeto: str = ""
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    metas: dict[str, int | float] = Field(default_factory=dict, description="Por unidad: cajas, carpetas, expedientes, folios, imagenes, metros_lineales")
    responsable_id: uuid.UUID | None = None


class ProyectoCambios(BaseModel):
    nombre: str | None = Field(default=None, max_length=300)
    entidad_cliente: str | None = Field(default=None, max_length=300)
    numero_contrato: str | None = Field(default=None, max_length=80)
    objeto: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    metas: dict[str, int | float] | None = None
    responsable_id: uuid.UUID | None = None
    motivo: str = Field(min_length=5)


class Motivo(BaseModel):
    motivo: str = Field(min_length=5)


class ProyectoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    nombre: str
    entidad_cliente: str
    numero_contrato: str | None
    objeto: str
    fecha_inicio: date | None
    fecha_fin: date | None
    metas: dict[str, int | float]
    responsable_id: uuid.UUID | None
    estado: str
    motivo_estado: str | None
    version: int
    creado_en: datetime


class VersionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    instantanea: dict[str, Any]
    motivo: str
    creado_en: datetime
    creado_por: uuid.UUID | None


class SedeNueva(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    ciudad: str = Field(default="", max_length=120)
    direccion: str = Field(default="", max_length=300)


class SedeSalida(SedeNueva):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    activa: bool


class MiembroNuevo(BaseModel):
    usuario_id: uuid.UUID
    funcion: str = Field(default="", max_length=120)


class MiembroSalida(MiembroNuevo):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    activo: bool


@rutas.get("", response_model=list[ProyectoSalida])
def listar(ctx: Lector, estado: EstadoProyecto | None = None):
    return servicios.listar(ctx, estado.value if estado else None)


@rutas.post("", status_code=status.HTTP_201_CREATED, response_model=ProyectoSalida)
def crear(datos: ProyectoNuevo, ctx: Gestor):
    return servicios.crear(ctx, datos.model_dump())


@rutas.get("/{proyecto_id}", response_model=ProyectoSalida)
def ver(proyecto_id: uuid.UUID, ctx: Lector):
    return servicios.obtener(ctx, proyecto_id)


@rutas.patch("/{proyecto_id}", response_model=ProyectoSalida)
def editar(proyecto_id: uuid.UUID, datos: ProyectoCambios, ctx: Gestor):
    p = servicios.obtener(ctx, proyecto_id)
    return servicios.editar(ctx, p, datos.model_dump(exclude_unset=True, exclude={"motivo"}), datos.motivo)


@rutas.post("/{proyecto_id}/activar", response_model=ProyectoSalida)
def activar(proyecto_id: uuid.UUID, datos: Motivo, ctx: Gestor):
    p = servicios.obtener(ctx, proyecto_id)
    if p.estado != EstadoProyecto.BORRADOR.value:
        raise TransicionInvalida("Solo se activa un proyecto en borrador; uno cerrado se reabre")
    return servicios.cambiar_estado(ctx, p, EstadoProyecto.ACTIVO, datos.motivo)


@rutas.post("/{proyecto_id}/cerrar", response_model=ProyectoSalida)
def cerrar(proyecto_id: uuid.UUID, datos: Motivo, ctx: Gestor):
    return servicios.cambiar_estado(ctx, servicios.obtener(ctx, proyecto_id), EstadoProyecto.CERRADO, datos.motivo)


@rutas.post("/{proyecto_id}/reabrir", response_model=ProyectoSalida)
def reabrir(proyecto_id: uuid.UUID, datos: Motivo, ctx: Gestor):
    p = servicios.obtener(ctx, proyecto_id)
    if p.estado != EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("Solo se reabre un proyecto cerrado")
    return servicios.cambiar_estado(ctx, p, EstadoProyecto.ACTIVO, datos.motivo)


@rutas.get("/{proyecto_id}/versiones", response_model=list[VersionSalida])
def versiones(proyecto_id: uuid.UUID, ctx: Lector):
    return servicios.versiones(ctx, servicios.obtener(ctx, proyecto_id))


@rutas.get("/{proyecto_id}/sedes", response_model=list[SedeSalida])
def listar_sedes(proyecto_id: uuid.UUID, ctx: Lector):
    return servicios.sedes(ctx, servicios.obtener(ctx, proyecto_id))


@rutas.post("/{proyecto_id}/sedes", status_code=status.HTTP_201_CREATED, response_model=SedeSalida)
def agregar_sede(proyecto_id: uuid.UUID, datos: SedeNueva, ctx: Gestor):
    return servicios.agregar_sede(ctx, servicios.obtener(ctx, proyecto_id), datos.nombre, datos.ciudad, datos.direccion)


@rutas.get("/{proyecto_id}/equipo", response_model=list[MiembroSalida])
def listar_equipo(proyecto_id: uuid.UUID, ctx: Lector):
    return servicios.equipo(ctx, servicios.obtener(ctx, proyecto_id))


@rutas.post("/{proyecto_id}/equipo", status_code=status.HTTP_201_CREATED, response_model=MiembroSalida)
def asignar(proyecto_id: uuid.UUID, datos: MiembroNuevo, ctx: Gestor):
    return servicios.asignar_miembro(ctx, servicios.obtener(ctx, proyecto_id), datos.usuario_id, datos.funcion)
