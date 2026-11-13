"""Base declarativa y campos transversales (reciclado de Kustos, models/base.py).

Principios:
- Identificadores de sistema UUID e inmutables; los códigos legibles son metadatos.
- Todo registro de negocio pertenece a una organización (tenant): `TenantMixin`. El aislamiento se
  aplica en cada consulta a partir de la membresía activa, nunca a partir de lo que envía el cliente.
- Nada se borra físicamente: se cierra, se suspende o se desactiva con motivo y queda en la auditoría.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, MetaData, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Json = JSON().with_variant(JSONB(), "postgresql")


def ahora_utc() -> datetime:
    return datetime.now(UTC)


def en_utc(fecha: datetime) -> datetime:
    """SQLite devuelve fechas sin zona; todas las fechas de ARCA se guardan en UTC."""
    return fecha.replace(tzinfo=UTC) if fecha.tzinfo is None else fecha.astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_CONVENCION_NOMBRES)


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class CamposControlMixin:
    """Campos transversales del modelo de datos (Instrucciones §6): quién y cuándo creó y modificó."""

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    creado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc, onupdate=ahora_utc)
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class TenantMixin:
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizaciones.id", ondelete="RESTRICT"), index=True)
