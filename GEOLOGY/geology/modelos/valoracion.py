"""Tabla de valoración documental convalidada. Reglas R8, R22 y R26."""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from geology.nucleo.bd import Base


class Fondo(Base):
    __tablename__ = "fondo_documental"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    historia_institucional: Mapped[Optional[str]] = mapped_column(Text)

    periodos: Mapped[list["Periodo"]] = relationship(back_populates="fondo")


class Periodo(Base):
    """Periodo institucional con su tabla de valoración convalidada."""
    __tablename__ = "periodo_institucional"
    id: Mapped[int] = mapped_column(primary_key=True)
    fondo_id: Mapped[int] = mapped_column(ForeignKey("fondo_documental.id"))
    numero_romano: Mapped[str] = mapped_column(String(6), index=True)
    orden: Mapped[int] = mapped_column(Integer)
    rango_texto: Mapped[str] = mapped_column(String(200))
    fecha_inicio: Mapped[Optional[date]] = mapped_column(Date)
    fecha_fin: Mapped[Optional[date]] = mapped_column(Date)
    entidad_productora: Mapped[str] = mapped_column(String(200))
    fecha_convalidacion_tvd: Mapped[Optional[date]] = mapped_column(Date)
    # Contexto que la unidad hereda, para no repetirlo en cada expediente (R33)
    historia_institucional: Mapped[Optional[str]] = mapped_column(Text)     # 3.2.2
    historia_archivistica: Mapped[Optional[str]] = mapped_column(Text)      # 3.2.3
    caracteristicas_fisicas: Mapped[Optional[str]] = mapped_column(Text)    # 3.4.4

    fondo: Mapped["Fondo"] = relationship(back_populates="periodos")
    secciones: Mapped[list["Seccion"]] = relationship(back_populates="periodo")

    __table_args__ = (UniqueConstraint("fondo_id", "numero_romano"),)


class Seccion(Base):
    """Unidad administrativa y oficina productora dentro del periodo."""
    __tablename__ = "seccion_productora"
    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodo_institucional.id"))
    codigo_dependencia: Mapped[str] = mapped_column(String(20))
    unidad_administrativa: Mapped[str] = mapped_column(String(200))
    oficina_productora: Mapped[str] = mapped_column(String(200))

    periodo: Mapped["Periodo"] = relationship(back_populates="secciones")
    series: Mapped[list["Serie"]] = relationship(back_populates="seccion")

    __table_args__ = (UniqueConstraint("periodo_id", "codigo_dependencia", "oficina_productora"),)


class Serie(Base):
    __tablename__ = "serie_documental"
    id: Mapped[int] = mapped_column(primary_key=True)
    seccion_id: Mapped[int] = mapped_column(ForeignKey("seccion_productora.id"))
    codigo: Mapped[str] = mapped_column(String(10))
    nombre: Mapped[str] = mapped_column(String(200))
    retencion_central_anios: Mapped[Optional[int]] = mapped_column(Integer)
    disposicion_final: Mapped[Optional[str]] = mapped_column(String(10))

    seccion: Mapped["Seccion"] = relationship(back_populates="series")
    subseries: Mapped[list["Subserie"]] = relationship(back_populates="serie")

    __table_args__ = (UniqueConstraint("seccion_id", "codigo"),)


class Subserie(Base):
    __tablename__ = "subserie_documental"
    id: Mapped[int] = mapped_column(primary_key=True)
    serie_id: Mapped[int] = mapped_column(ForeignKey("serie_documental.id"))
    codigo: Mapped[str] = mapped_column(String(10))
    nombre: Mapped[str] = mapped_column(String(200))
    soporte: Mapped[Optional[str]] = mapped_column(String(60))
    retencion_central_anios: Mapped[Optional[int]] = mapped_column(Integer)
    disposicion_final: Mapped[Optional[str]] = mapped_column(String(10))

    serie: Mapped["Serie"] = relationship(back_populates="subseries")

    __table_args__ = (UniqueConstraint("serie_id", "codigo"),)
