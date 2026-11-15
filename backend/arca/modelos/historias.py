"""Historias laborales (D-43): el titular de cada expediente y la configuración del proyecto.

Una historia laboral es el expediente de una persona vinculada a la entidad (Acuerdo AGN 001 de 2024, Título 9,
Capítulo 5): se conforma con los tipos documentales mínimos de la serie, en orden cronológico, con acceso
restringido, y se cierra cuando termina el trámite de retiro y el pago de las prestaciones sociales.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, Json, TenantMixin


class ConfigHistorias(IdMixin, TenantMixin, Base):
    """Si el proyecto es de historias laborales, qué series lo son y cuáles tipos documentales son obligatorios."""

    __tablename__ = "config_historias"
    __table_args__ = (UniqueConstraint("proyecto_id"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    series: Mapped[list] = mapped_column(Json, default=list)  # códigos de la TRD que son historias laborales; vacío = todo el proyecto
    tipos_obligatorios: Mapped[list] = mapped_column(Json, default=list)  # tipos documentales mínimos de la serie
    motivo: Mapped[str] = mapped_column(Text, default="")
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class TitularExpediente(IdMixin, TenantMixin, Base):
    """La persona de una historia laboral. ARCA la propone (del FUID o del OCR) y una persona la confirma."""

    __tablename__ = "titulares_expediente"
    __table_args__ = (UniqueConstraint("unidad_id"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    tipo_documento: Mapped[str] = mapped_column(String(10), default="CC")  # CC | CE | TI | PA | PEP
    numero_documento: Mapped[str] = mapped_column(String(20), default="", index=True)  # solo dígitos (o letras en pasaporte)
    nombres: Mapped[str] = mapped_column(String(300), default="")
    cargo: Mapped[str] = mapped_column(String(300), default="")
    dependencia: Mapped[str] = mapped_column(String(300), default="")
    fecha_vinculacion: Mapped[date | None] = mapped_column(Date)
    fecha_retiro: Mapped[date | None] = mapped_column(Date)
    origen: Mapped[dict] = mapped_column(Json, default=dict)  # campo → {fuente, detalle}
    estado: Mapped[str] = mapped_column(String(20), default="propuesto")  # propuesto | confirmado
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
