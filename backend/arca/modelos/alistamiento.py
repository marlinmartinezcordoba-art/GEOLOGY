"""Alistamiento físico por expediente (D-44): las intervenciones que se le hacen a cada expediente antes de digitalizarlo.

La dirección fija las actividades del proyecto (depuración, ordenación cronológica, foliación, retiro de material
abrasivo, cambio de carpeta, rotulación…). El equipo registra cada una por expediente o por caja entera, con la
cantidad cuando la actividad la pide (folios, carpetas), y queda quién la hizo y cuándo.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, Json, TenantMixin


class PlanAlistamiento(IdMixin, TenantMixin, Base):
    __tablename__ = "planes_alistamiento"
    __table_args__ = (UniqueConstraint("proyecto_id"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    actividades: Mapped[list] = mapped_column(Json, default=list)  # [{codigo, nombre, cantidad: ninguna|folios|unidades, obligatoria}]
    exigir_para_entrega: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    motivo: Mapped[str] = mapped_column(Text, default="")
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class IntervencionExpediente(IdMixin, TenantMixin, Base):
    """Una actividad de alistamiento hecha a un expediente. Deshacerla la borra y queda en la auditoría con su motivo."""

    __tablename__ = "intervenciones_expediente"
    __table_args__ = (UniqueConstraint("unidad_id", "actividad"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    actividad: Mapped[str] = mapped_column(String(40))
    cantidad: Mapped[int | None] = mapped_column(Integer)  # folios o unidades, si la actividad la pide
    observacion: Mapped[str] = mapped_column(Text, default="")
    hecho_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    hecho_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class DiagnosticoExpediente(IdMixin, TenantMixin, Base):
    """Diagnóstico de conservación de un expediente: estado general y hallazgos, al recibirlo para el alistamiento."""

    __tablename__ = "diagnosticos_expediente"
    __table_args__ = (UniqueConstraint("unidad_id"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    estado: Mapped[str] = mapped_column(String(20))  # bueno | regular | malo
    hallazgos: Mapped[list] = mapped_column(Json, default=list)  # códigos del catálogo
    folios_afectados: Mapped[int | None] = mapped_column(Integer)
    observacion: Mapped[str] = mapped_column(Text, default="")
    registrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registrado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
