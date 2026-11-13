"""M25 Pista de auditoría inalterable (reciclada de Kustos, models/auditoria.py).

- Cada evento se encadena al anterior de su organización con SHA-256 (hash_anterior → hash_evento).
- Cada cambio lleva su valor anterior y nuevo, el motivo y el identificador de correlación.
- Cada cierto número de eventos se emite un SELLO HMAC con una clave aparte: sin esa clave no se
  puede reescribir la tabla completa sin que se note.
- Nunca se actualiza ni se borra un evento.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, Json


class EventoAuditoria(IdMixin, Base):
    __tablename__ = "auditoria"

    # None = evento de la plataforma (operador SaaS, ingresos).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    secuencia: Mapped[int] = mapped_column(Integer, index=True)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    usuario_nombre: Mapped[str] = mapped_column(String(200))
    accion: Mapped[str] = mapped_column(String(60), index=True)
    objeto: Mapped[str] = mapped_column(String(60), index=True)
    objeto_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    detalle: Mapped[str] = mapped_column(Text, default="")
    motivo: Mapped[str | None] = mapped_column(Text)
    cambios: Mapped[dict | None] = mapped_column(Json)
    resultado: Mapped[str] = mapped_column(String(20), default="exito")  # exito | bloqueado | error
    ip: Mapped[str | None] = mapped_column(String(64))
    agente: Mapped[str | None] = mapped_column(String(300))
    correlacion_id: Mapped[str | None] = mapped_column(String(64), index=True)
    hash_anterior: Mapped[str] = mapped_column(String(64))
    hash_evento: Mapped[str] = mapped_column(String(64), index=True)


class CadenaAuditoria(Base):
    """Último eslabón por organización; se bloquea por fila al escribir para que la secuencia no se repita."""

    __tablename__ = "auditoria_cadenas"

    clave: Mapped[str] = mapped_column(String(40), primary_key=True)
    ultima_secuencia: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_hash: Mapped[str] = mapped_column(String(64), default="0" * 64)
    ultimo_sello_secuencia: Mapped[int] = mapped_column(Integer, default=0)


class SelloAuditoria(IdMixin, Base):
    __tablename__ = "auditoria_sellos"

    clave: Mapped[str] = mapped_column(String(40), index=True)
    secuencia: Mapped[int] = mapped_column(Integer)
    hash_evento: Mapped[str] = mapped_column(String(64))
    sello: Mapped[str] = mapped_column(String(64))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True))
