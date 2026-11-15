"""Transferencias documentales: primaria (archivo de gestión → central) y secundaria (central → histórico).

Reglas (Acuerdo 004 de 2019 del AGN y D-24, D-32):
- Solo se transfiere lo clasificado y confirmado, que está en la fase de origen y no va en otra transferencia abierta.
- Es elegible lo que cumplió la retención en la fecha de corte: en la primaria, el tiempo en gestión (AG); en la
  secundaria, el de gestión más el de central (AC), y solo si la disposición final es conservación total,
  selección o digitalización. Lo que tiene eliminación no va al histórico: va a la disposición final.
- Se puede incluir una unidad que aún no cumple (transferencia anticipada), pero queda con aviso.
- Quien envía no recibe (segregación de funciones). Se recibe unidad por unidad: lo recibido cambia de fase;
  lo devuelto se queda donde estaba, con la observación. Cada cambio de fase queda en el historial.
- El inventario de la transferencia sale en el FUID de la entidad (plantilla vigente) con su huella.
"""

import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select

from arca.modelos import (
    ClasificacionUnidad,
    ElementoInstrumento,
    ElementoTransferencia,
    EstadoProyecto,
    MovimientoFase,
    Proyecto,
    Transferencia,
    UnidadDocumental,
)
from arca.modelos.base import ahora_utc
from arca.modelos.transferencias import FASES, TIPOS_TRANSFERENCIA
from arca.modulos.entregables import servicios as entregables
from arca.modulos.m04_instrumentos.clasificacion import calendario
from arca.modulos.m08_inventarios.fuid import clave_de
from arca.nucleo.errores import AccesoDenegado, Conflicto, DatosInvalidos, NoEncontrado, TransicionInvalida

ABIERTAS = ("borrador", "enviada", "devuelta")
EDITABLES = ("borrador", "devuelta")
AL_HISTORICO = {"CT", "S", "D"}
NOMBRE_TIPO = {"primaria": "Transferencia primaria", "secundaria": "Transferencia secundaria"}


def _natural(texto: str | None) -> list:
    """«C-2» antes que «C-10», como se archivan las cajas y las carpetas."""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.split(r"(\d+)", texto or "") if t]


def _abierto(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


def _tipo(tipo: str) -> tuple[str, str]:
    if tipo not in TIPOS_TRANSFERENCIA:
        raise DatosInvalidos("Tipo de transferencia desconocido: use primaria o secundaria")
    return TIPOS_TRANSFERENCIA[tipo]


def _contexto(ctx, proyecto: Proyecto) -> dict[str, Any]:
    """Todo lo necesario para decidir, en una sola lectura: unidades, clasificación confirmada, elementos y dependencias."""
    unidades = {u.id: u for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id))}
    clasif = {c.unidad_id: c for c in ctx.db.scalars(select(ClasificacionUnidad).where(ClasificacionUnidad.proyecto_id == proyecto.id, ClasificacionUnidad.estado == "confirmada"))}
    elementos = {e.id: e for e in ctx.db.scalars(select(ElementoInstrumento).where(ElementoInstrumento.id.in_({c.elemento_id for c in clasif.values()})))} if clasif else {}
    versiones = {c.version_id for c in clasif.values()}
    deps = {(e.version_id, e.codigo): e.nombre for e in ctx.db.scalars(select(ElementoInstrumento).where(ElementoInstrumento.version_id.in_(versiones), ElementoInstrumento.nivel == "dependencia"))} if versiones else {}
    ocupadas = dict(ctx.db.execute(
        select(ElementoTransferencia.unidad_id, Transferencia.numero).join(Transferencia, ElementoTransferencia.transferencia_id == Transferencia.id)
        .where(Transferencia.proyecto_id == proyecto.id, Transferencia.estado.in_(ABIERTAS), ElementoTransferencia.estado != "devuelta")
    ).all())
    ocupadas = {uid: f"la transferencia n.º {n}" for uid, n in ocupadas.items()}
    from arca.modulos.disposicion.servicios import ocupadas as en_disposicion  # importación diferida: evita un ciclo entre módulos

    for uid, donde in en_disposicion(ctx, proyecto).items():
        ocupadas.setdefault(uid, f"el {donde}")
    from arca.modulos.historias.servicios import bases_de_retencion  # noqa: PLC0415 — historias laborales: desde el retiro

    return {"unidades": unidades, "clasif": clasif, "elementos": elementos, "deps": deps, "ocupadas": ocupadas, "bases": bases_de_retencion(ctx, proyecto)}


def _evaluar(datos: dict[str, Any], u: UnidadDocumental, tipo: str, corte: date) -> dict[str, Any]:
    """¿Puede ir esta unidad en una transferencia de este tipo? (puede, elegible, aviso, dependencia)."""
    origen, _ = TIPOS_TRANSFERENCIA[tipo]
    c = datos["clasif"].get(u.id)
    r: dict[str, Any] = {"puede": False, "elegible": False, "aviso": "", "codigo_dependencia": "", "dependencia": "", "clasificacion": c}
    if u.fase != origen:
        r["aviso"] = f"está en {FASES.get(u.fase, u.fase).lower()}, no en {FASES[origen].lower()}"
        return r
    if c is None:
        r["aviso"] = "no está clasificada (o la clasificación no está confirmada)"
        return r
    e = datos["elementos"][c.elemento_id]
    r["codigo_dependencia"], r["dependencia"] = e.codigo_dependencia, datos["deps"].get((c.version_id, e.codigo_dependencia), e.codigo_dependencia)
    if u.id in datos["ocupadas"]:
        r["aviso"] = f"ya va en {datos['ocupadas'][u.id]}"
        return r
    r["puede"] = True
    cal = calendario(u, e, corte, desde=datos["bases"].get(u.id))
    if tipo == "secundaria" and e.disposicion not in AL_HISTORICO:
        r["puede"], r["aviso"] = False, f"su disposición final es {cal['disposicion'] or 'desconocida'}: no va al archivo histórico"
        return r
    fin = cal["fin_gestion"] if tipo == "primaria" else cal["fin_central"]
    if cal.get("base") == "retiro" and cal["fin_gestion"] is None:
        r["aviso"] = "historia laboral abierta: la persona sigue vinculada (sin fecha de retiro)"
    elif fin is None:
        r["aviso"] = "sin fecha final o sin tiempos de retención: no se puede saber si cumplió"
    elif fin > corte:
        r["aviso"] = f"anticipada: su retención en {'gestión' if tipo == 'primaria' else 'central'} termina el {fin.isoformat()}"
    else:
        r["elegible"] = True
    if tipo == "secundaria" and e.disposicion == "S":
        if u.disposicion_aplicada != "seleccionada":
            r["puede"], r["elegible"], r["aviso"] = False, False, "selección pendiente: haga el muestreo en Disposición final; solo va al histórico lo seleccionado"
        else:
            r["aviso"] = r["aviso"] or "quedó en la muestra de selección"
    return r


def plan(ctx, proyecto: Proyecto, corte: date) -> dict[str, Any]:
    """Cuántas unidades hay en cada fase y cuántas se pueden transferir a la fecha de corte, por dependencia."""
    datos = _contexto(ctx, proyecto)
    fases = {f: 0 for f in FASES}
    tipos: dict[str, dict[str, Any]] = {t: {"elegibles": 0, "anticipables": 0, "sin_calendario": 0, "por_dependencia": {}} for t in TIPOS_TRANSFERENCIA}
    sin_clasificar = 0
    for u in datos["unidades"].values():
        fases[u.fase] = fases.get(u.fase, 0) + 1
        if u.id not in datos["clasif"]:
            sin_clasificar += 1
        for t, (origen, _) in TIPOS_TRANSFERENCIA.items():
            if u.fase != origen:
                continue
            ev = _evaluar(datos, u, t, corte)
            if not ev["puede"]:
                continue
            g = tipos[t]
            if ev["elegible"]:
                g["elegibles"] += 1
                d = g["por_dependencia"].setdefault(ev["codigo_dependencia"], {"codigo": ev["codigo_dependencia"], "dependencia": ev["dependencia"], "elegibles": 0, "folios": 0})
                d["elegibles"] += 1
                d["folios"] += u.folios or 0
            elif "sin fecha" in ev["aviso"]:
                g["sin_calendario"] += 1
            else:
                g["anticipables"] += 1
    for g in tipos.values():
        g["por_dependencia"] = sorted(g["por_dependencia"].values(), key=lambda d: d["codigo"])
    return {"fecha_corte": corte, "fases": fases, "sin_clasificar": sin_clasificar, "tipos": tipos}


def listar(ctx, proyecto: Proyecto) -> list[Transferencia]:
    return list(ctx.db.scalars(select(Transferencia).where(Transferencia.proyecto_id == proyecto.id).order_by(Transferencia.numero.desc())))


def obtener(ctx, proyecto: Proyecto, transferencia_id: uuid.UUID) -> Transferencia:
    t = ctx.db.get(Transferencia, transferencia_id)
    if t is None or t.proyecto_id != proyecto.id:
        raise NoEncontrado("La transferencia no existe")
    return t


def elementos(ctx, t: Transferencia) -> list[tuple[ElementoTransferencia, UnidadDocumental]]:
    filas = ctx.db.execute(select(ElementoTransferencia, UnidadDocumental).join(UnidadDocumental, ElementoTransferencia.unidad_id == UnidadDocumental.id)
                           .where(ElementoTransferencia.transferencia_id == t.id)).all()
    return sorted(((e, u) for e, u in filas), key=lambda x: (_natural(x[1].caja), _natural(x[1].carpeta), _natural(x[1].identificador)))


def _agregar(ctx, t: Transferencia, datos: dict[str, Any], u: UnidadDocumental, ev: dict[str, Any]) -> None:
    ctx.db.add(ElementoTransferencia(tenant_id=ctx.tenant_id, transferencia_id=t.id, unidad_id=u.id, clasificacion_id=ev["clasificacion"].id,
                                     elegible=ev["elegible"], aviso=ev["aviso"]))
    datos["ocupadas"][u.id] = f"la transferencia n.º {t.numero}"


def crear(ctx, proyecto: Proyecto, tipo: str, corte: date, codigo_dependencia: str, observaciones: str) -> Transferencia:
    """Crea el borrador con todo lo elegible a la fecha de corte (de una dependencia, o de todas)."""
    _abierto(proyecto)
    _tipo(tipo)
    datos = _contexto(ctx, proyecto)
    numero = (ctx.db.scalar(select(func.max(Transferencia.numero)).where(Transferencia.proyecto_id == proyecto.id)) or 0) + 1
    t = Transferencia(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, numero=numero, tipo=tipo, estado="borrador", codigo_dependencia=codigo_dependencia.strip(),
                      fecha_corte=corte, observaciones=observaciones.strip(), creado_en=ahora_utc(), creado_por=ctx.usuario.id)
    ctx.db.add(t)
    ctx.db.flush()
    incluidas = 0
    for u in datos["unidades"].values():
        ev = _evaluar(datos, u, tipo, corte)
        if ev["puede"] and ev["elegible"] and (not t.codigo_dependencia or ev["codigo_dependencia"] == t.codigo_dependencia):
            if not t.dependencia and t.codigo_dependencia:
                t.dependencia = ev["dependencia"]
            _agregar(ctx, t, datos, u, ev)
            incluidas += 1
    ctx.auditar(accion="CREAR_TRANSFERENCIA", objeto="Transferencia", objeto_id=t.id,
                detalle=f"{proyecto.codigo} · {NOMBRE_TIPO[tipo]} n.º {numero} · corte {corte.isoformat()} · {incluidas} unidades{' · dependencia ' + t.codigo_dependencia if t.codigo_dependencia else ''}")
    ctx.db.commit()
    return t


def _editable(t: Transferencia) -> None:
    if t.estado not in EDITABLES:
        raise TransicionInvalida("Solo se modifica una transferencia en borrador o devuelta")


def agregar(ctx, proyecto: Proyecto, t: Transferencia, unidad_ids: list[uuid.UUID]) -> dict[str, Any]:
    _abierto(proyecto)
    _editable(t)
    datos = _contexto(ctx, proyecto)
    agregadas, rechazadas = 0, []
    for uid in dict.fromkeys(unidad_ids):
        u = datos["unidades"].get(uid)
        if u is None:
            raise NoEncontrado("Alguna de las unidades no existe en el proyecto")
        ev = _evaluar(datos, u, t.tipo, t.fecha_corte)
        if t.codigo_dependencia and ev["puede"] and ev["codigo_dependencia"] != t.codigo_dependencia:
            ev["puede"], ev["aviso"] = False, f"es de la dependencia {ev['codigo_dependencia']}, no de la {t.codigo_dependencia}"
        if not ev["puede"]:
            rechazadas.append(f"{u.identificador}: {ev['aviso']}")
            continue
        _agregar(ctx, t, datos, u, ev)
        agregadas += 1
    if agregadas:
        ctx.auditar(accion="AGREGAR_A_TRANSFERENCIA", objeto="Transferencia", objeto_id=t.id, detalle=f"n.º {t.numero} · {agregadas} unidades")
    ctx.db.commit()
    return {"agregadas": agregadas, "rechazadas": rechazadas}


def quitar(ctx, proyecto: Proyecto, t: Transferencia, unidad_ids: list[uuid.UUID]) -> int:
    _abierto(proyecto)
    _editable(t)
    filas = list(ctx.db.scalars(select(ElementoTransferencia).where(ElementoTransferencia.transferencia_id == t.id, ElementoTransferencia.unidad_id.in_(unidad_ids))))
    for e in filas:
        ctx.db.delete(e)
    ctx.auditar(accion="QUITAR_DE_TRANSFERENCIA", objeto="Transferencia", objeto_id=t.id, detalle=f"n.º {t.numero} · {len(filas)} unidades")
    ctx.db.commit()
    return len(filas)


def enviar(ctx, proyecto: Proyecto, t: Transferencia) -> Transferencia:
    _abierto(proyecto)
    _editable(t)
    filas = elementos(ctx, t)
    if not filas:
        raise TransicionInvalida("La transferencia no tiene unidades")
    sin_folios = [u.identificador for _, u in filas if not u.folios]
    if sin_folios:
        raise TransicionInvalida(f"{len(sin_folios)} unidades no tienen número de folios ({', '.join(sin_folios[:5])}{'…' if len(sin_folios) > 5 else ''}): complételo en el FUID")
    for e, _ in filas:
        e.estado, e.observacion = "incluida", ""
    t.estado, t.enviada_en, t.enviada_por = "enviada", ahora_utc(), ctx.usuario.id
    ctx.auditar(accion="ENVIAR_TRANSFERENCIA", objeto="Transferencia", objeto_id=t.id,
                detalle=f"{NOMBRE_TIPO[t.tipo]} n.º {t.numero} · {len(filas)} unidades · {sum(u.folios or 0 for _, u in filas)} folios")
    ctx.db.commit()
    return t


def recibir(ctx, proyecto: Proyecto, t: Transferencia, devueltas: dict[uuid.UUID, str], motivo: str) -> dict[str, int]:
    """Recibe la transferencia. `devueltas` = {unidad_id: observación}: esas no se reciben. Todo lo demás cambia de fase."""
    _abierto(proyecto)
    if t.estado != "enviada":
        raise TransicionInvalida("Solo se recibe una transferencia enviada")
    if t.enviada_por == ctx.usuario.id:
        raise AccesoDenegado("Quien envió la transferencia no puede recibirla (segregación de funciones)")
    filas = elementos(ctx, t)
    ids = {u.id for _, u in filas}
    if set(devueltas) - ids:
        raise DatosInvalidos("Alguna de las unidades devueltas no va en esta transferencia")
    if any(len((o or "").strip()) < 5 for o in devueltas.values()):
        raise DatosInvalidos("Cada unidad devuelta necesita una observación")
    if len(devueltas) == len(filas):
        raise DatosInvalidos("Si no se recibe ninguna unidad, devuelva la transferencia completa")
    origen, destino = TIPOS_TRANSFERENCIA[t.tipo]
    ahora = ahora_utc()
    recibidas = 0
    for e, u in filas:
        if u.id in devueltas:
            e.estado, e.observacion = "devuelta", devueltas[u.id].strip()
            continue
        if u.fase != origen:  # cambió por otra vía después del envío: no se mueve a ciegas
            raise Conflicto(f"La unidad {u.identificador} ya no está en {FASES[origen].lower()}")
        e.estado = "recibida"
        u.fase = destino
        ctx.db.add(MovimientoFase(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, unidad_id=u.id, desde=origen, hasta=destino, transferencia_id=t.id,
                                  motivo=f"{NOMBRE_TIPO[t.tipo]} n.º {t.numero}", creado_en=ahora, creado_por=ctx.usuario.id))
        recibidas += 1
    t.estado, t.recibida_en, t.recibida_por = "recibida", ahora, ctx.usuario.id
    t.novedad = motivo.strip()
    ctx.auditar(accion="RECIBIR_TRANSFERENCIA", objeto="Transferencia", objeto_id=t.id, motivo=motivo or None,
                detalle=f"{NOMBRE_TIPO[t.tipo]} n.º {t.numero} · {recibidas} recibidas en {FASES[destino].lower()} · {len(devueltas)} devueltas")
    ctx.db.commit()
    return {"recibidas": recibidas, "devueltas": len(devueltas)}


def devolver(ctx, proyecto: Proyecto, t: Transferencia, motivo: str) -> Transferencia:
    """El archivo receptor la devuelve completa: vuelve a quien la preparó para corregirla y reenviarla."""
    _abierto(proyecto)
    if t.estado != "enviada":
        raise TransicionInvalida("Solo se devuelve una transferencia enviada")
    if t.enviada_por == ctx.usuario.id:
        raise AccesoDenegado("Quien envió la transferencia no puede devolverla")
    t.estado, t.novedad = "devuelta", motivo.strip()
    ctx.auditar(accion="DEVOLVER_TRANSFERENCIA", objeto="Transferencia", objeto_id=t.id, motivo=motivo, detalle=f"n.º {t.numero}")
    ctx.db.commit()
    return t


def anular(ctx, proyecto: Proyecto, t: Transferencia, motivo: str) -> Transferencia:
    _abierto(proyecto)
    _editable(t)
    t.estado, t.novedad = "anulada", motivo.strip()
    ctx.auditar(accion="ANULAR_TRANSFERENCIA", objeto="Transferencia", objeto_id=t.id, motivo=motivo, detalle=f"n.º {t.numero}")
    ctx.db.commit()
    return t


def inventario(ctx, proyecto: Proyecto, t: Transferencia):
    """El FUID de la transferencia, sobre la plantilla vigente de la entidad, con objeto, número y oficina productora."""
    filas = [u for e, u in elementos(ctx, t) if e.estado != "devuelta"]
    if not filas:
        raise TransicionInvalida("La transferencia no tiene unidades")
    extra = {"objeto": NOMBRE_TIPO[t.tipo], "numero_transferencia": t.numero, "oficina_productora": t.dependencia or "Varias dependencias",
             "codigo_oficina": t.codigo_dependencia, "fecha_corte": t.fecha_corte}
    return entregables.expedir(ctx, proyecto, "fuid", None, None, None, unidad_ids=[u.id for u in filas], encabezado_extra=extra,
                               filtro_extra={"transferencia": t.numero})


def fase_de_partida(ctx, proyecto: Proyecto, unidad_ids: list[uuid.UUID], fase: str, motivo: str, cajas: list[str] | None = None) -> int:
    """Para un fondo que ya está en el archivo central o histórico: se registra dónde está, una sola vez y con motivo.

    Se indican las unidades o las cajas (todas las unidades de esas cajas).
    """
    _abierto(proyecto)
    if fase not in FASES:
        raise DatosInvalidos("Fase desconocida: use gestion, central o historico")
    if cajas:
        buscadas = {clave_de(c) for c in cajas if c.strip()}
        unidad_ids = [u.id for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id)) if u.caja and clave_de(u.caja) in buscadas]
        if not unidad_ids:
            raise NoEncontrado("No hay unidades en esas cajas")
    unidades = list(ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id, UnidadDocumental.id.in_(unidad_ids))))
    if not unidad_ids or len(unidades) != len(set(unidad_ids)):
        raise NoEncontrado("Alguna de las unidades no existe en el proyecto")
    con_historia = set(ctx.db.scalars(select(MovimientoFase.unidad_id).where(MovimientoFase.unidad_id.in_(unidad_ids))))
    if con_historia:
        raise TransicionInvalida(f"{len(con_historia)} unidades ya tienen movimientos: su fase solo cambia por transferencia")
    ocupadas = _contexto(ctx, proyecto)["ocupadas"]
    if any(u.id in ocupadas for u in unidades):
        raise TransicionInvalida("Alguna unidad va en una transferencia abierta")
    ahora = ahora_utc()
    for u in unidades:
        ctx.db.add(MovimientoFase(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, unidad_id=u.id, desde=None, hasta=fase, motivo=motivo.strip(), creado_en=ahora, creado_por=ctx.usuario.id))
        u.fase = fase
    ctx.auditar(accion="FASE_DE_PARTIDA", objeto="Proyecto", objeto_id=proyecto.id, motivo=motivo, detalle=f"{proyecto.codigo} · {len(unidades)} unidades en {FASES[fase].lower()}")
    ctx.db.commit()
    return len(unidades)


def historial(ctx, proyecto: Proyecto, unidad_id: uuid.UUID) -> list[MovimientoFase]:
    return list(ctx.db.scalars(select(MovimientoFase).where(MovimientoFase.proyecto_id == proyecto.id, MovimientoFase.unidad_id == unidad_id).order_by(MovimientoFase.creado_en)))


def resumen(ctx, t: Transferencia) -> dict[str, Any]:
    filas = elementos(ctx, t)
    return {"unidades": len(filas), "folios": sum(u.folios or 0 for _, u in filas), "anticipadas": sum(1 for e, _ in filas if not e.elegible),
            "recibidas": sum(1 for e, _ in filas if e.estado == "recibida"), "devueltas": sum(1 for e, _ in filas if e.estado == "devuelta"),
            "cajas": len({u.caja for _, u in filas if u.caja})}

