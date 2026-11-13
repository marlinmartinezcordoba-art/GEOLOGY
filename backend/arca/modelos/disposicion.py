"""Disposición final: eliminación, selección (muestreo) y digitalización, con el aval del Comité.

Eliminar es irreversible. Por eso un proceso de eliminación pasa siempre por: inventario → aprobación del
Comité registrada por alguien distinto de quien lo preparó → publicación del inventario por el plazo que se
fije → ejecución con acta. La unidad eliminada no se borra de ARCA: queda en fase «eliminada» con su
historial, su inventario y el acta, que se conservan.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, Json, TenantMixin

TIPOS_DISPOSICION = {"eliminacion": "E", "seleccion": "S", "digitalizacion": "D"}


class ProcesoDisposicion(IdMixin, TenantMixin, Base):
    __tablename__ = "procesos_disposicion"
    __table_args__ = (UniqueConstraint("proyecto_id", "numero"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String(20))  # eliminacion | seleccion | digitalizacion
    estado: Mapped[str] = mapped_column(String(20), index=True)  # borrador | aprobado | publicado | ejecutado | anulado
    fecha_corte: Mapped[date] = mapped_column(Date)
    observaciones: Mapped[str] = mapped_column(Text, default="")
    origen_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("procesos_disposicion.id", ondelete="RESTRICT"))
    comite_acta: Mapped[str | None] = mapped_column(String(200))
    comite_fecha: Mapped[date | None] = mapped_column(Date)
    aprobado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprobado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    publicacion_inicio: Mapped[date | None] = mapped_column(Date)
    publicacion_dias: Mapped[int | None] = mapped_column(Integer)
    publicacion_enlace: Mapped[str | None] = mapped_column(String(500))
    muestreo: Mapped[dict] = mapped_column(Json, default=dict)
    destino_fisico: Mapped[str | None] = mapped_column(String(20))  # conservar | eliminar (después de digitalizar)
    metodo: Mapped[str | None] = mapped_column(String(200))  # cómo se eliminó: picado, reciclaje…
    acta_numero: Mapped[str | None] = mapped_column(String(100))
    ejecutado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ejecutado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    novedad: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class ElementoDisposicion(IdMixin, TenantMixin, Base):
    __tablename__ = "disposicion_elementos"
    __table_args__ = (UniqueConstraint("proceso_id", "unidad_id"),)

    proceso_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procesos_disposicion.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    clasificacion_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clasificaciones.id", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(20), default="incluida")  # incluida | retirada | seleccionada | no_seleccionada | ejecutada
    aviso: Mapped[str] = mapped_column(Text, default="")
    observacion: Mapped[str] = mapped_column(Text, default="")
