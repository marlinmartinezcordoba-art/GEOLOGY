"""Transferencias documentales y ciclo vital de las unidades (archivo de gestión → central → histórico).

Una transferencia la prepara y la envía quien entrega y la recibe otra persona, unidad por unidad. Solo lo
recibido cambia de fase; lo devuelto se queda donde estaba con la observación. Cada cambio de fase queda en
`movimientos_fase`, con la transferencia que lo causó, o con el motivo si es la fase de partida de un fondo.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, TenantMixin

FASES = {"gestion": "Archivo de gestión", "central": "Archivo central", "historico": "Archivo histórico", "eliminada": "Eliminada"}
TIPOS_TRANSFERENCIA = {"primaria": ("gestion", "central"), "secundaria": ("central", "historico")}


class Transferencia(IdMixin, TenantMixin, Base):
    __tablename__ = "transferencias"
    __table_args__ = (UniqueConstraint("proyecto_id", "numero"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String(20))  # primaria | secundaria
    estado: Mapped[str] = mapped_column(String(20), index=True)  # borrador | enviada | devuelta | recibida | anulada
    codigo_dependencia: Mapped[str] = mapped_column(String(40), default="")
    dependencia: Mapped[str] = mapped_column(String(300), default="")
    fecha_corte: Mapped[date] = mapped_column(Date)
    observaciones: Mapped[str] = mapped_column(Text, default="")
    novedad: Mapped[str] = mapped_column(Text, default="")  # motivo de la última devolución o anulación
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enviada_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    recibida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recibida_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class ElementoTransferencia(IdMixin, TenantMixin, Base):
    __tablename__ = "transferencia_elementos"
    __table_args__ = (UniqueConstraint("transferencia_id", "unidad_id"),)

    transferencia_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transferencias.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    clasificacion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clasificaciones.id", ondelete="RESTRICT"))
    elegible: Mapped[bool] = mapped_column(Boolean, default=True)  # cumplía la retención en la fecha de corte
    aviso: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(String(20), default="incluida")  # incluida | recibida | devuelta
    observacion: Mapped[str] = mapped_column(Text, default="")


class MovimientoFase(IdMixin, TenantMixin, Base):
    __tablename__ = "movimientos_fase"

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    desde: Mapped[str | None] = mapped_column(String(20))
    hasta: Mapped[str] = mapped_column(String(20))
    transferencia_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transferencias.id", ondelete="RESTRICT"))
    motivo: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
