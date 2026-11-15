"""Flujo automático: cola de trabajos en segundo plano y etapa en que va cada unidad (D-39).

La cola vive en la base de datos: no requiere instalar nada más. Un trabajo se toma con una actualización condicionada
(solo si sigue pendiente), así dos trabajadores no toman el mismo. Cada trabajo actúa a nombre de la persona cuya acción
lo originó, y lo que hace queda en la auditoría como «flujo automático».
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, Json, TenantMixin


class Trabajo(IdMixin, TenantMixin, Base):
    __tablename__ = "trabajos"

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    tipo: Mapped[str] = mapped_column(String(40))  # flujo_unidad
    estado: Mapped[str] = mapped_column(String(20), index=True)  # pendiente | en_curso | hecho | error
    motivo: Mapped[str] = mapped_column(String(200), default="")  # qué lo originó: «carga de archivos», «hoja verificada»…
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    resultado: Mapped[dict] = mapped_column(Json, default=dict)
    parametros: Mapped[dict] = mapped_column(Json, default=dict, server_default="{}")
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    iniciado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaqueteEntrega(IdMixin, TenantMixin, Base):
    """Un paquete de entrega digital (ZIP) con los expedientes listos, para cargarlos en el SGDEA de la entidad (D-40)."""

    __tablename__ = "paquetes_entrega"

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(20))  # en_cola | listo | error
    filtro: Mapped[dict] = mapped_column(Json, default=dict)
    unidades: Mapped[int] = mapped_column(Integer, default=0)
    pendientes: Mapped[list] = mapped_column(Json, default=list)  # las que no entraron y por qué
    archivo_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("archivos.id", ondelete="RESTRICT"))
    resumen: Mapped[dict] = mapped_column(Json, default=dict, server_default="{}")  # cuántos quedaron en PDF/A, con texto…
    error: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    terminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FlujoUnidad(IdMixin, TenantMixin, Base):
    """Dónde va cada unidad en el flujo y qué espera."""

    __tablename__ = "flujo_unidades"
    __table_args__ = (UniqueConstraint("unidad_id"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"))
    etapa: Mapped[str] = mapped_column(String(40), index=True)
    detalle: Mapped[str] = mapped_column(Text, default="")
    espera_persona: Mapped[bool] = mapped_column(default=False)  # la siguiente acción es de una persona
    hechos: Mapped[list] = mapped_column(Json, default=list)  # lo que el flujo hizo solo, con fecha
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
