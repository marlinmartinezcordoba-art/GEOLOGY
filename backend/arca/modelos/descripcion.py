"""Configuración de procesos por lote y descripción archivística ISAD(G) de las unidades.

La descripción es independiente del ciclo vital (D-24): se hace en la fase que esté la unidad. Depende de la
digitalización: se construye sobre lo digitalizado, sobre la hoja de control verificada si el lote la lleva y
sobre la clasificación. Cada elemento guarda su origen, igual que la hoja de control. La elabora una persona y la
aprueba otra.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, Json, TenantMixin


class ConfiguracionLote(IdMixin, TenantMixin, Base):
    """Qué procesos lleva un lote de trabajo (el de la base de cajas). `lote` vacío = lo que vale para todo el proyecto."""

    __tablename__ = "configuracion_lotes"
    __table_args__ = (UniqueConstraint("proyecto_id", "lote"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    lote: Mapped[str] = mapped_column(String(80), default="")
    hoja_control: Mapped[bool] = mapped_column(Boolean, default=True)
    isadg: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo: Mapped[str] = mapped_column(Text, default="")
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class DescripcionUnidad(IdMixin, TenantMixin, Base):
    __tablename__ = "descripciones"
    __table_args__ = (UniqueConstraint("unidad_id"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    estado: Mapped[str] = mapped_column(String(20), index=True)  # borrador | en_revision | devuelta | aprobada
    campos: Mapped[dict] = mapped_column(Json, default=dict)  # {elemento: valor}
    origen: Mapped[dict] = mapped_column(Json, default=dict)  # {elemento: {"fuente": ..., "detalle": ...}}
    observaciones: Mapped[dict] = mapped_column(Json, default=dict)  # {elemento: observación de la revisión}
    novedad: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enviada_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    aprobada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprobada_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
