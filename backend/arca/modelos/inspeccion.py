"""Inspección de calidad por lote con muestreo de aceptación (D-42).

La dirección fija el plan del proyecto (qué se inspecciona, cuánto se muestrea, qué defectos hay y cuántos se aceptan).
Quien inspecciona revisa una muestra que ARCA elige al azar con semilla registrada (la misma semilla da la misma
muestra), anota los defectos de cada elemento y ARCA decide: el lote se acepta o se rechaza según el plan.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, Json, TenantMixin


class PlanMuestreo(IdMixin, TenantMixin, Base):
    """El plan de muestreo vigente del proyecto. Cada inspección guarda una copia del plan con el que se hizo."""

    __tablename__ = "planes_muestreo"
    __table_args__ = (UniqueConstraint("proyecto_id"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad: Mapped[str] = mapped_column(String(20))  # expedientes | imagenes
    metodo: Mapped[str] = mapped_column(String(20))  # porcentaje | tabla
    porcentaje: Mapped[float] = mapped_column(Float, default=0)
    minimo: Mapped[int] = mapped_column(Integer, default=0)
    tabla: Mapped[list] = mapped_column(Json, default=list)  # [{desde, hasta, muestra}]
    aceptacion: Mapped[dict] = mapped_column(Json, default=dict)  # {critico, mayor, menor}: defectos que se aceptan
    defectos: Mapped[list] = mapped_column(Json, default=list)  # [{codigo, nombre, severidad}]
    frente: Mapped[str] = mapped_column(String(40), default="")  # frente de productividad al que se cuenta la inspección
    exigir_para_entrega: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    motivo: Mapped[str] = mapped_column(Text, default="")
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class InspeccionLote(IdMixin, TenantMixin, Base):
    __tablename__ = "inspecciones_lote"
    __table_args__ = (UniqueConstraint("proyecto_id", "numero"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    lote: Mapped[str] = mapped_column(String(80), default="", index=True)
    estado: Mapped[str] = mapped_column(String(20), index=True)  # abierta | aceptada | rechazada | anulada
    plan: Mapped[dict] = mapped_column(Json, default=dict)  # copia del plan con el que se hizo
    tamano: Mapped[int] = mapped_column(Integer, default=0)  # tamaño del lote (expedientes o imágenes)
    muestra: Mapped[int] = mapped_column(Integer, default=0)
    semilla: Mapped[int] = mapped_column(Integer)
    criticos: Mapped[int] = mapped_column(Integer, default=0)
    mayores: Mapped[int] = mapped_column(Integer, default=0)
    menores: Mapped[int] = mapped_column(Integer, default=0)
    limitaciones: Mapped[int] = mapped_column(Integer, default=0)  # defectos del original: se registran, no cuentan
    reinspeccion_de: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inspecciones_lote.id", ondelete="RESTRICT"))
    observaciones: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cerrada_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class ItemInspeccion(IdMixin, TenantMixin, Base):
    """Un elemento de la muestra: un expediente, o una imagen (página) de un expediente."""

    __tablename__ = "items_inspeccion"

    inspeccion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inspecciones_lote.id", ondelete="RESTRICT"), index=True)
    orden: Mapped[int] = mapped_column(Integer)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    pagina: Mapped[int | None] = mapped_column(Integer)  # solo si se inspeccionan imágenes
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | revisado
    defectos: Mapped[list] = mapped_column(Json, default=list)  # [{codigo, nombre, severidad, pagina, nota}]
    revisado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revisado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
