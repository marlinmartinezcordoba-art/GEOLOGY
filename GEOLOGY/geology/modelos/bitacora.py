"""
Bitácora. Cada cambio de estado con su responsable, su fecha y su motivo.
Nunca se borra: es lo que permite responder qué pasó con un expediente, incluso con uno
que se retiró por error (paso nuevo).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from geology.nucleo.bd import Base


class Trazabilidad(Base):
    __tablename__ = "bitacora"
    id: Mapped[int] = mapped_column(primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey("unidad_documental.id"), index=True)
    estado_anterior: Mapped[Optional[str]] = mapped_column(String(40))
    estado_nuevo: Mapped[str] = mapped_column(String(40))
    accion: Mapped[str] = mapped_column(String(80))
    usuario: Mapped[Optional[str]] = mapped_column(String(150))
    motivo: Mapped[Optional[str]] = mapped_column(Text)
    errores: Mapped[Optional[str]] = mapped_column(Text)
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    expediente: Mapped["Expediente"] = relationship(back_populates="trazabilidad")
