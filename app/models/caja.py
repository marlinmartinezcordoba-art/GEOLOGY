"""Cajas definitivas X-100. Una caja pertenece a un solo periodo institucional."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Caja(Base):
    __tablename__ = "caja"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, index=True)   # AH-CJ-00001
    periodo: Mapped[str] = mapped_column(String(6), index=True)                # se fija con la primera carpeta
    total_carpetas: Mapped[int] = mapped_column(Integer, default=0)
    cerrada: Mapped[bool] = mapped_column(Boolean, default=False)
    cerrada_en: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cerrada_por: Mapped[Optional[str]] = mapped_column(String(150))
    estante: Mapped[Optional[str]] = mapped_column(String(30))
    observaciones: Mapped[Optional[str]] = mapped_column(Text)
    creada_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
