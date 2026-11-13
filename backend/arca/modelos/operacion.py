"""M06 Proyectos, contratos, sedes y equipo, y M03 parámetros versionados por vigencia."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, CamposControlMixin, IdMixin, Json, TenantMixin


class EstadoProyecto(StrEnum):
    BORRADOR = "borrador"
    ACTIVO = "activo"
    CERRADO = "cerrado"


class UnidadMeta(StrEnum):
    """Unidades de medida de las metas. Se miden por separado: nunca se suman folios con imágenes (ARC-04)."""

    CAJAS = "cajas"
    CARPETAS = "carpetas"
    EXPEDIENTES = "expedientes"
    FOLIOS = "folios"
    IMAGENES = "imagenes"
    METROS_LINEALES = "metros_lineales"


class Proyecto(IdMixin, TenantMixin, CamposControlMixin, Base):
    __tablename__ = "proyectos"
    __table_args__ = (UniqueConstraint("tenant_id", "codigo"),)

    codigo: Mapped[str] = mapped_column(String(40))
    nombre: Mapped[str] = mapped_column(String(300))
    # Entidad para la que se ejecuta el proyecto y contrato que lo respalda.
    entidad_cliente: Mapped[str] = mapped_column(String(300))
    numero_contrato: Mapped[str | None] = mapped_column(String(80))
    objeto: Mapped[str] = mapped_column(Text, default="")
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    # {"cajas": 1200, "imagenes": 450000}: claves de UnidadMeta.
    metas: Mapped[dict] = mapped_column(Json, default=dict)
    responsable_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(20), default=EstadoProyecto.BORRADOR.value, index=True)
    motivo_estado: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)


class VersionProyecto(IdMixin, TenantMixin, Base):
    """Instantánea del alcance cada vez que cambia: el alcance y las metas quedan versionados (M06)."""

    __tablename__ = "proyecto_versiones"
    __table_args__ = (UniqueConstraint("proyecto_id", "version"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    instantanea: Mapped[dict] = mapped_column(Json)
    motivo: Mapped[str] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class Sede(IdMixin, TenantMixin, CamposControlMixin, Base):
    __tablename__ = "sedes"
    __table_args__ = (UniqueConstraint("proyecto_id", "nombre"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    ciudad: Mapped[str] = mapped_column(String(120), default="")
    direccion: Mapped[str] = mapped_column(String(300), default="")
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class MiembroProyecto(IdMixin, TenantMixin, CamposControlMixin, Base):
    __tablename__ = "proyecto_equipo"
    __table_args__ = (UniqueConstraint("proyecto_id", "usuario_id"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    # Función dentro del proyecto (en GEOLOGY: «hoja de control», «descripción» o «ambas»).
    funcion: Mapped[str] = mapped_column(String(120), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Parametro(IdMixin, TenantMixin, Base):
    """Un parámetro es una serie de versiones. Rige la versión de mayor `vigente_desde` que no sea futura.

    Nunca se edita una versión: se publica una nueva con su vigencia, y la vigencia no puede ser pasada,
    de modo que un proceso histórico se sigue explicando con la configuración que tuvo (M03).
    """

    __tablename__ = "parametros"
    __table_args__ = (UniqueConstraint("tenant_id", "proyecto_id", "clave", "version"),)

    proyecto_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    clave: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[int] = mapped_column(Integer)
    valor: Mapped[dict | list | str | int | float | bool | None] = mapped_column(Json)
    vigente_desde: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    motivo: Mapped[str] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
