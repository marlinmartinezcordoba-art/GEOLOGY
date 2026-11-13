"""M13 · Texto leído por OCR de cada página digitalizada.

Se guarda por archivo y página del archivo (no por página del expediente), así una recaptura o un cambio de orden
no confunde a qué imagen pertenece el texto. Queda el motor y su versión, el idioma, la confianza y las líneas con
su confianza, que es lo que permite decir de dónde salió cada dato que se proponga.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, Json, TenantMixin


class TextoPagina(IdMixin, TenantMixin, Base):
    __tablename__ = "textos_pagina"
    __table_args__ = (UniqueConstraint("recurso_id", "pagina"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    recurso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recursos_digitales.id", ondelete="RESTRICT"), index=True)
    pagina: Mapped[int] = mapped_column(Integer)  # página dentro del archivo
    estado: Mapped[str] = mapped_column(String(20))  # leida | sin_texto | error
    texto: Mapped[str] = mapped_column(Text, default="")
    lineas: Mapped[list] = mapped_column(Json, default=list)  # [[texto, confianza], …]
    confianza: Mapped[float | None] = mapped_column(Float)
    palabras: Mapped[int] = mapped_column(Integer, default=0)
    motor: Mapped[str] = mapped_column(String(100))
    idioma: Mapped[str] = mapped_column(String(20), default="spa")
    detalle: Mapped[str] = mapped_column(Text, default="")  # el error, si lo hubo
    duracion_ms: Mapped[int | None] = mapped_column(Integer)
    # Giro detectado (0, 90, 180 o 270): la página se muestra y se lee derecha; el original no se toca.
    rotacion: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
