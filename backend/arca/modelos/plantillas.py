"""Plantillas parametrizables y versionadas (D-27): FUID de salida, rótulo de caja y rótulo de carpeta.

La entidad entrega su formato en Excel y marca con {{campo}} dónde va cada dato; ARCA lo llena sin tocar el
código. Una plantilla es una serie de versiones con vigencia: se publica una nueva o se reemplaza la vigente,
y cada documento expedido guarda la versión con la que se hizo, para poder demostrarlo después.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, Json, TenantMixin


class Plantilla(IdMixin, TenantMixin, Base):
    """Un formato de la entidad. Sin proyecto = de toda la organización; con proyecto = solo para ese proyecto."""

    __tablename__ = "plantillas"
    __table_args__ = (UniqueConstraint("tenant_id", "proyecto_id", "tipo", "nombre"),)

    proyecto_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    tipo: Mapped[str] = mapped_column(String(30), index=True)  # fuid | rotulo_caja | rotulo_carpeta
    nombre: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class VersionPlantilla(IdMixin, TenantMixin, Base):
    __tablename__ = "plantilla_versiones"
    __table_args__ = (UniqueConstraint("plantilla_id", "version"),)

    plantilla_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plantillas.id", ondelete="RESTRICT"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    codigo_formato: Mapped[str] = mapped_column(String(80), default="")  # el código del formato en el sistema de calidad de la entidad
    archivo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("archivos.id", ondelete="RESTRICT"))
    campos: Mapped[list] = mapped_column(Json, default=list)  # marcadores encontrados en el archivo
    valores_fijos: Mapped[dict] = mapped_column(Json, default=dict)  # datos de la entidad que no salen del sistema
    vigente_desde: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(String(20), default="vigente")  # vigente | reemplazada | programada
    motivo: Mapped[str] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class Expedicion(IdMixin, TenantMixin, Base):
    """Un documento expedido (FUID, rótulos): con qué versión de plantilla, sobre qué datos y por quién."""

    __tablename__ = "expediciones"

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plantilla_versiones.id", ondelete="RESTRICT"))
    archivo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("archivos.id", ondelete="RESTRICT"))
    filtro: Mapped[dict] = mapped_column(Json, default=dict)
    elementos: Mapped[int] = mapped_column(Integer, default=0)  # unidades en el FUID o rótulos generados
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
