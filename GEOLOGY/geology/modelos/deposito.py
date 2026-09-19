"""Archivos cargados: el documento digitalizado o la hoja de control en Excel."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from geology.nucleo.bd import Base


class Archivo(Base):
    __tablename__ = "archivo_digital"
    id: Mapped[int] = mapped_column(primary_key=True)
    expediente_id: Mapped[Optional[int]] = mapped_column(ForeignKey("unidad_documental.id"), index=True)
    codigo_carpeta: Mapped[str] = mapped_column(String(20), index=True)
    fragmento: Mapped[int] = mapped_column(Integer, default=0)      # 0 completo, 1..n por partes
    nombre_original: Mapped[str] = mapped_column(String(255))
    ruta: Mapped[str] = mapped_column(String(500))
    tamano_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)     # detecta el mismo archivo cargado dos veces
    subido_por: Mapped[Optional[str]] = mapped_column(String(150))
    subido_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Recepción técnica. Se mide al entrar y no modifica el archivo.
    paginas: Mapped[Optional[int]] = mapped_column(Integer)
    dpi_minimo: Mapped[Optional[int]] = mapped_column(Integer)
    dpi_medio: Mapped[Optional[int]] = mapped_column(Integer)
    bits_por_color: Mapped[Optional[int]] = mapped_column(Integer)
    tiene_capa_de_texto: Mapped[Optional[bool]] = mapped_column(Boolean)
    avisos_tecnicos: Mapped[Optional[str]] = mapped_column(Text)

    # Matriz de preservación en PDF/A y copia de consulta trabajada. La matriz conserva las
    # imágenes intactas; la copia se endereza, se limpia y lleva capa de texto buscable.
    ruta_matriz: Mapped[Optional[str]] = mapped_column(String(500))
    ruta_consulta: Mapped[Optional[str]] = mapped_column(String(500))
    ruta_texto: Mapped[Optional[str]] = mapped_column(String(500))
    procesado_en: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error_proceso: Mapped[Optional[str]] = mapped_column(Text)

    # Cuando un documento de gran volumen (un libro de mil imágenes cargado entero) lo
    # divide el sistema en partes consecutivas, cada parte guarda qué páginas del original
    # abarca, de modo que la secuencia se pueda reconstruir y demostrar.
    pagina_inicial: Mapped[Optional[int]] = mapped_column(Integer)
    pagina_final: Mapped[Optional[int]] = mapped_column(Integer)
    dividido_por_sistema: Mapped[Optional[bool]] = mapped_column(Boolean)
    sha256_origen: Mapped[Optional[str]] = mapped_column(String(64), index=True)   # huella del archivo entero del que se cortó
