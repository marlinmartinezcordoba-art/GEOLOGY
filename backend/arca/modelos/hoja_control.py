"""Hoja de control del expediente (Acuerdo 002 de 2014 del AGN), hecha sobre lo digitalizado.

Cada trámite (renglón) dice qué documento es, su fecha, sus folios y qué páginas digitalizadas le
corresponden, para que quien revisa lo vea al lado. Cada dato guarda su **origen**: si lo escribió una
persona, si lo calculó ARCA desde las páginas, si salió de la lista de la TRD o si se importó de un
libro de cálculo (con archivo, pestaña y fila). La hoja la elabora una persona y la verifica otra.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, Json, TenantMixin


class HojaControl(IdMixin, TenantMixin, Base):
    __tablename__ = "hojas_control"
    __table_args__ = (UniqueConstraint("unidad_id"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    estado: Mapped[str] = mapped_column(String(20), index=True)  # borrador | en_revision | devuelta | verificada
    imagenes_por_folio: Mapped[int] = mapped_column(Integer, default=1)  # 1 = cada imagen es un folio; 2 = recto y verso
    origen: Mapped[str] = mapped_column(String(20), default="digitalizacion")  # digitalizacion | importada | manual
    importacion: Mapped[dict] = mapped_column(Json, default=dict)  # archivo, huella y pestaña si se importó
    observaciones: Mapped[str] = mapped_column(Text, default="")
    novedad: Mapped[str] = mapped_column(Text, default="")  # motivo de la última devolución
    total_folios: Mapped[int | None] = mapped_column(Integer)  # lo contado en la hoja al enviarla
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enviada_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    verificada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verificada_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class TramiteHoja(IdMixin, TenantMixin, Base):
    """Un renglón de la hoja: un documento del expediente."""

    __tablename__ = "hoja_tramites"

    hoja_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hojas_control.id", ondelete="RESTRICT"), index=True)
    orden: Mapped[int] = mapped_column(Integer)
    fecha: Mapped[date | None] = mapped_column(Date)  # completa (día, mes y año)
    fecha_texto: Mapped[str | None] = mapped_column(String(10))  # aaaa-mm-dd, aaaa-mm o aaaa; vacío = sin fecha (S. F.)
    tipo_documental: Mapped[str] = mapped_column(String(300), default="")
    detalle: Mapped[str] = mapped_column(Text, default="")  # lo que distingue a este documento: asunto, número, remitente…
    folio_desde: Mapped[int | None] = mapped_column(Integer)
    folio_hasta: Mapped[int | None] = mapped_column(Integer)
    pagina_desde: Mapped[int | None] = mapped_column(Integer)  # páginas del expediente digitalizado (para el visor)
    pagina_hasta: Mapped[int | None] = mapped_column(Integer)
    no_radicado: Mapped[str] = mapped_column(String(100), default="")
    observaciones: Mapped[str] = mapped_column(Text, default="")
    # Metadatos del documento: asunto, remitente, destinatario, firmantes, lugar, número (con su origen en `origen["metadatos.x"]`).
    metadatos: Mapped[dict] = mapped_column(Json, default=dict, server_default="{}")
    origen: Mapped[dict] = mapped_column(Json, default=dict)  # {campo: {"fuente": ..., "detalle": ...}}
    revision: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | conforme | observada
    observacion_revision: Mapped[str] = mapped_column(Text, default="")
