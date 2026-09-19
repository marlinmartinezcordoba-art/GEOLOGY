"""Consumo diario de cada motor de lenguaje, para repartir la carga.

La columna proveedor guarda la clave del motor, que es proveedor/modelo, por ejemplo
"claude/claude-sonnet-4-5". Así cada modelo lleva su propia cuenta y su propia cuota.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConsumoModelo(Base):
    __tablename__ = "consumo_modelo"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    proveedor: Mapped[str] = mapped_column(String(120))   # clave del motor: proveedor/modelo
    peticiones: Mapped[int] = mapped_column(Integer, default=0)
    agotado_en: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ultimo_error: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("fecha", "proveedor"),)
