"""Cola de trabajos en la base de datos (D-39). No importa ningún módulo de negocio: cualquiera puede encolar."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from arca.modelos import Trabajo
from arca.modelos.base import ahora_utc

MAX_INTENTOS = 3


def encolar(db: Session, tenant_id: uuid.UUID, proyecto_id: uuid.UUID, unidad_id: uuid.UUID | None, usuario_id: uuid.UUID, motivo: str, tipo: str = "flujo_unidad") -> bool:
    """Agrega un trabajo si no hay ya uno pendiente igual. No hace commit: va en la misma transacción de quien lo pide."""
    ya = db.scalar(select(Trabajo.id).where(Trabajo.tipo == tipo, Trabajo.unidad_id == unidad_id, Trabajo.proyecto_id == proyecto_id, Trabajo.estado == "pendiente"))
    if ya:
        return False
    db.add(Trabajo(tenant_id=tenant_id, proyecto_id=proyecto_id, unidad_id=unidad_id, tipo=tipo, estado="pendiente", motivo=motivo[:200], usuario_id=usuario_id, creado_en=ahora_utc()))
    return True


def encolar_ctx(ctx, proyecto_id: uuid.UUID, unidad_id: uuid.UUID | None, motivo: str) -> bool:
    if unidad_id is None:  # un archivo sin identificar no tiene flujo todavía
        return False
    return encolar(ctx.db, ctx.tenant_id, proyecto_id, unidad_id, ctx.usuario.id, motivo)


def tomar(db: Session, proyecto_id: uuid.UUID | None = None) -> Trabajo | None:
    """El trabajo pendiente más antiguo, marcado en curso. La actualización condicionada evita que dos trabajadores lo tomen."""
    for _ in range(5):
        consulta = select(Trabajo.id).where(Trabajo.estado == "pendiente")
        if proyecto_id:
            consulta = consulta.where(Trabajo.proyecto_id == proyecto_id)
        tid = db.scalar(consulta.order_by(Trabajo.creado_en).limit(1))
        if tid is None:
            return None
        r = db.execute(update(Trabajo).where(Trabajo.id == tid, Trabajo.estado == "pendiente").values(estado="en_curso", iniciado_en=ahora_utc(), intentos=Trabajo.intentos + 1))
        db.commit()
        if r.rowcount == 1:
            return db.get(Trabajo, tid)
    return None
