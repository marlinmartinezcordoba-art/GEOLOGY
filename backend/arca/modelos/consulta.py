"""M23 · Índice de consulta: el texto de cada unidad, normalizado para buscar sin importar tildes ni mayúsculas.

Por unidad se indexan cuatro fuentes: los metadatos (FUID y clasificación), el texto OCR de cada página, los trámites
de la hoja de control verificada y la descripción ISAD(G) aprobada. El índice se mantiene al día solo: cada unidad
guarda una firma de sus fuentes y, antes de buscar, se reindexa lo que cambió. El texto original se guarda al lado
del normalizado, con la misma longitud, para mostrar el fragmento donde apareció lo buscado.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, TenantMixin


class IndiceUnidad(IdMixin, TenantMixin, Base):
    __tablename__ = "consulta_unidades"
    __table_args__ = (UniqueConstraint("unidad_id"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"))
    firma: Mapped[str] = mapped_column(String(300))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EntradaIndice(IdMixin, TenantMixin, Base):
    __tablename__ = "consulta_entradas"

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    fuente: Mapped[str] = mapped_column(String(20))  # metadatos | ocr | hoja | descripcion
    referencia: Mapped[str] = mapped_column(String(200), default="")  # «página 3», «trámite 2», «3.1.2 Título»
    pagina: Mapped[int | None] = mapped_column(Integer)  # página del expediente, para abrir el visor ahí
    reservada: Mapped[bool] = mapped_column(Boolean, default=False)  # la TRD clasifica o reserva el acceso
    texto: Mapped[str] = mapped_column(Text, default="")
    normal: Mapped[str] = mapped_column(Text, default="")
