"""M25 Auditoría inalterable (reciclada de Kustos, comun/servicios/auditoria.py).

`registrar()` agrega el evento a la sesión y se confirma junto con la operación que lo origina: si la
operación falla, el evento no queda. Un intento bloqueado se registra aparte con `registrar_bloqueo()`.
"""

import hashlib
import hmac
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from arca.modelos import CadenaAuditoria, EventoAuditoria, SelloAuditoria, Usuario
from arca.modelos.base import ahora_utc, en_utc
from arca.nucleo.config import ajustes

PLATAFORMA = "plataforma"
_CERO = "0" * 64


def _serializable(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {str(k): _serializable(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple | set):
        return [_serializable(v) for v in valor]
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, uuid.UUID | date | datetime | Decimal):
        return str(valor)
    return valor


def huella_evento(e: EventoAuditoria) -> str:
    contenido = json.dumps(
        [
            e.secuencia,
            str(e.tenant_id),
            str(e.usuario_id),
            e.usuario_nombre,
            e.accion,
            e.objeto,
            str(e.objeto_id),
            e.detalle,
            e.motivo,
            e.cambios,
            e.resultado,
            e.ip,
            e.agente,
            e.correlacion_id,
            en_utc(e.fecha).isoformat(),
            e.hash_anterior,
        ],
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def sello_de(clave: str, secuencia: int, hash_evento: str) -> str:
    return hmac.new(ajustes().clave_sellado.encode(), f"{clave}|{secuencia}|{hash_evento}".encode(), hashlib.sha256).hexdigest()


def _clave(tenant_id: uuid.UUID | None) -> str:
    return str(tenant_id) if tenant_id else PLATAFORMA


def _eslabon(db: Session, clave: str) -> CadenaAuditoria:
    fila = db.get(CadenaAuditoria, clave, with_for_update=True)
    if fila is None:
        fila = CadenaAuditoria(clave=clave, ultima_secuencia=0, ultimo_hash=_CERO, ultimo_sello_secuencia=0)
        db.add(fila)
        db.flush()
    return fila


def registrar(
    db: Session,
    *,
    tenant_id: uuid.UUID | None,
    usuario: Usuario | None,
    accion: str,
    objeto: str,
    objeto_id: uuid.UUID | None = None,
    detalle: str = "",
    motivo: str | None = None,
    cambios: dict[str, Any] | None = None,
    resultado: str = "exito",
    ip: str | None = None,
    agente: str | None = None,
    correlacion_id: str | None = None,
    usuario_nombre: str | None = None,
) -> EventoAuditoria:
    clave = _clave(tenant_id)
    eslabon = _eslabon(db, clave)
    evento = EventoAuditoria(
        tenant_id=tenant_id,
        secuencia=eslabon.ultima_secuencia + 1,
        fecha=ahora_utc(),
        usuario_id=usuario.id if usuario else None,
        usuario_nombre=usuario_nombre or (usuario.nombre_completo if usuario else "Sistema ARCA"),
        accion=accion.upper(),
        objeto=objeto,
        objeto_id=objeto_id,
        detalle=detalle,
        motivo=motivo,
        cambios=_serializable(cambios) if cambios else None,
        resultado=resultado,
        ip=ip,
        agente=(agente or "")[:300] or None,
        correlacion_id=correlacion_id,
        hash_anterior=eslabon.ultimo_hash,
    )
    evento.hash_evento = huella_evento(evento)
    eslabon.ultima_secuencia = evento.secuencia
    eslabon.ultimo_hash = evento.hash_evento
    db.add(evento)
    if evento.secuencia - eslabon.ultimo_sello_secuencia >= ajustes().sellar_cada_eventos:
        _sellar(db, clave, evento.secuencia, evento.hash_evento)
        eslabon.ultimo_sello_secuencia = evento.secuencia
    return evento


def _sellar(db: Session, clave: str, secuencia: int, hash_evento: str) -> SelloAuditoria:
    sello = SelloAuditoria(clave=clave, secuencia=secuencia, hash_evento=hash_evento, sello=sello_de(clave, secuencia, hash_evento), fecha=ahora_utc())
    db.add(sello)
    return sello


def sellar_ahora(db: Session, tenant_id: uuid.UUID | None) -> SelloAuditoria | None:
    """Sello bajo demanda o programado (por ejemplo al cierre del día)."""
    clave = _clave(tenant_id)
    eslabon = _eslabon(db, clave)
    if eslabon.ultima_secuencia in (0, eslabon.ultimo_sello_secuencia):
        return None
    sello = _sellar(db, clave, eslabon.ultima_secuencia, eslabon.ultimo_hash)
    eslabon.ultimo_sello_secuencia = eslabon.ultima_secuencia
    return sello


def registrar_bloqueo(fabrica, **datos: Any) -> None:
    """Un intento bloqueado también es evidencia: se guarda en su propia transacción."""
    with fabrica() as db:
        registrar(db, resultado="bloqueado", **datos)
        db.commit()


def aplicar_cambios(objeto: Any, nuevos: dict[str, Any]) -> dict[str, list[Any]]:
    """Aplica `nuevos` al objeto y devuelve {campo: [anterior, nuevo]} solo de lo que cambió."""
    diferencias: dict[str, list[Any]] = {}
    for campo, valor in nuevos.items():
        anterior = getattr(objeto, campo)
        if anterior != valor:
            diferencias[campo] = [anterior, valor]
            setattr(objeto, campo, valor)
    return diferencias


def verificar_integridad(db: Session, tenant_id: uuid.UUID | None) -> dict[str, Any]:
    """Recorre la cadena, recalcula cada huella y comprueba los sellos HMAC."""
    clave = _clave(tenant_id)
    consulta = select(EventoAuditoria).order_by(EventoAuditoria.secuencia)
    consulta = consulta.where(EventoAuditoria.tenant_id == tenant_id) if tenant_id else consulta.where(EventoAuditoria.tenant_id.is_(None))
    sellos = {s.secuencia: s for s in db.scalars(select(SelloAuditoria).where(SelloAuditoria.clave == clave))}
    anterior, esperado, revisados, sellos_ok = _CERO, 1, 0, 0

    def falla(problema: str, secuencia: int) -> dict[str, Any]:
        return {"integra": False, "revisados": revisados, "sellos_verificados": sellos_ok, "problema": problema, "secuencia": secuencia}

    for e in db.scalars(consulta):
        revisados += 1
        if e.secuencia != esperado:
            return falla(f"Falta el evento {esperado} (sigue el {e.secuencia})", esperado)
        if e.hash_anterior != anterior or huella_evento(e) != e.hash_evento:
            return falla(f"El evento {e.secuencia} fue modificado", e.secuencia)
        sello = sellos.get(e.secuencia)
        if sello:
            if sello.hash_evento != e.hash_evento or not hmac.compare_digest(sello.sello, sello_de(clave, e.secuencia, e.hash_evento)):
                return falla(f"El sello del evento {e.secuencia} no corresponde: la cadena fue reescrita", e.secuencia)
            sellos_ok += 1
        anterior, esperado = e.hash_evento, esperado + 1
    # Si la cadena dice tener más eventos de los que hay, borraron el final.
    eslabon = db.get(CadenaAuditoria, clave)
    if eslabon is not None and eslabon.ultima_secuencia != esperado - 1:
        return falla(f"Faltan eventos al final de la cadena (se esperaban {eslabon.ultima_secuencia})", esperado)
    return {"integra": True, "revisados": revisados, "sellos_verificados": sellos_ok, "problema": None, "secuencia": None}
