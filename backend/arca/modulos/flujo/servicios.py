"""Flujo automático de cada unidad: al cargar lo digitalizado, ARCA avanza solo hasta donde tiene que decidir una persona.

Etapas, en orden (D-39):
1. **Calidad.** Si hay archivos por revisar o en recaptura, el flujo espera a la persona de calidad.
2. **OCR.** Se leen las páginas pendientes por tandas (el trabajo se vuelve a encolar hasta terminar).
3. **Hoja de control**, si el lote la lleva: ARCA la crea y la propone desde el OCR. Espera a que una persona confirme
   lo propuesto y la envíe, y a que otra la verifique.
4. **Descripción ISAD(G)**, si el lote la lleva: con la hoja verificada (o, si el lote no lleva hoja, con el OCR), ARCA la
   crea y propone título y alcance. Espera a que una persona la confirme y otra la apruebe.
5. **Listo.**

El flujo nunca decide por una persona: solo hace lo que es cálculo o propuesta. Actúa a nombre de quien originó el
trabajo y cada cosa que hace queda en la auditoría como «flujo automático».
"""

import uuid
from typing import Any

from sqlalchemy import func, select

from arca.api.deps import Contexto, Peticion
from arca.modelos import (
    EstadoRecurso,
    FlujoUnidad,
    Membresia,
    Proyecto,
    RecursoDigital,
    Trabajo,
    TramiteHoja,
    UnidadDocumental,
    Usuario,
)
from arca.modelos.base import ahora_utc
from arca.modulos.flujo.cola import MAX_INTENTOS, encolar
from arca.nucleo.config import ajustes
from arca.nucleo.errores import ErrorDominio

ETAPAS: dict[str, tuple[str, bool]] = {  # clave: (nombre, espera a una persona)
    "en_cola": ("En cola", False),
    "sin_digitalizar": ("Sin digitalizar", False),
    "esperando_calidad": ("Calidad por revisar", True),
    "ocr": ("Leyendo con OCR", False),
    "hoja_por_confirmar": ("Hoja de control por confirmar", True),
    "hoja_en_verificacion": ("Hoja de control por verificar", True),
    "hoja_devuelta": ("Hoja de control devuelta", True),
    "descripcion_por_confirmar": ("Descripción por confirmar", True),
    "descripcion_en_revision": ("Descripción por aprobar", True),
    "descripcion_devuelta": ("Descripción devuelta", True),
    "listo": ("Listo", False),
    "error": ("Con error", True),
}
POR_REVISAR = (EstadoRecurso.EN_REVISION.value, EstadoRecurso.RECAPTURA.value)


def contexto_de(db, trabajo: Trabajo) -> Contexto:
    """El contexto de la persona a cuyo nombre actúa el trabajo, en la organización del trabajo."""
    usuario = db.get(Usuario, trabajo.usuario_id)
    membresia = db.scalar(select(Membresia).where(Membresia.usuario_id == usuario.id, Membresia.tenant_id == trabajo.tenant_id))
    return Contexto(db=db, usuario=usuario, organizacion=membresia.organizacion, membresia=membresia,
                    origen=Peticion(ip=None, agente="ARCA · flujo automático", correlacion_id=f"flujo-{trabajo.id}"))


def _registrar(ctx, u: UnidadDocumental, etapa: str, detalle: str, hecho: str | None = None) -> None:
    f = ctx.db.scalar(select(FlujoUnidad).where(FlujoUnidad.unidad_id == u.id))
    if f is None:
        f = FlujoUnidad(tenant_id=ctx.tenant_id, proyecto_id=u.proyecto_id, unidad_id=u.id, etapa=etapa, hechos=[])
        ctx.db.add(f)
    f.etapa, f.detalle, f.espera_persona, f.actualizado_en = etapa, detalle[:500], ETAPAS[etapa][1], ahora_utc()
    if hecho:
        f.hechos = ([*(f.hechos or []), {"fecha": ahora_utc().isoformat(), "que": hecho}])[-30:]


def paso(ctx, proyecto: Proyecto, u: UnidadDocumental) -> dict[str, Any]:
    """Avanza la unidad todo lo que pueda sin una persona. Devuelve la etapa en que queda y si hay que seguir."""
    from arca.modulos.descripcion import servicios as descripcion  # noqa: PLC0415 — el flujo orquesta; los módulos no se conocen entre sí
    from arca.modulos.hoja_control import servicios as hoja  # noqa: PLC0415
    from arca.modulos.m10_digitalizacion.paginas import paginas  # noqa: PLC0415
    from arca.modulos.m13_ocr import lector  # noqa: PLC0415
    from arca.modulos.m13_ocr import servicios as ocr  # noqa: PLC0415
    from arca.modulos.procesos.servicios import procesos_de  # noqa: PLC0415

    hechos: list[str] = []

    def fin(etapa: str, detalle: str, seguir: bool = False) -> dict[str, Any]:
        _registrar(ctx, u, etapa, detalle, "; ".join(hechos) or None)
        return {"etapa": etapa, "detalle": detalle, "seguir": seguir, "hechos": hechos}

    pags = paginas(ctx, u)
    if not pags:
        return fin("sin_digitalizar", "No tiene imágenes cargadas")
    por_revisar = ctx.db.scalar(select(func.count()).where(RecursoDigital.unidad_id == u.id, RecursoDigital.estado.in_(POR_REVISAR))) or 0
    if por_revisar:
        return fin("esperando_calidad", f"{por_revisar} archivos por revisar o en recaptura en el control de calidad")
    procesos = procesos_de(ctx, proyecto, u)
    ocr_completo = False
    if lector.disponible():
        r = ocr.leer_unidad(ctx, proyecto, u, limite=ajustes().paginas_ocr_por_tanda)
        if r["procesadas"]:
            hechos.append(f"OCR de {r['procesadas']} páginas")
            if not r["pendientes"]:
                hechos.extend(hoja.legibilidad(ctx, pags))
        if r["pendientes"]:
            return fin("ocr", f"Leídas {r['paginas'] - r['pendientes']} de {r['paginas']} páginas", seguir=True)
        ocr_completo = True
    if procesos["hoja_control"]:
        h = hoja.hoja_de(ctx, u)
        if h is None:
            h = hoja.crear(ctx, proyecto, u, 1)
            h.creado_por = None  # la creó el flujo: elabora quien la confirma y la envía (segregación de funciones)
            ctx.db.commit()
            hechos.append("hoja de control creada")
        if h.estado in hoja.EDITABLES and ocr_completo:
            tramites = list(ctx.db.scalars(select(TramiteHoja).where(TramiteHoja.hoja_id == h.id)))
            sin_trabajar = len(tramites) <= 1 and not any(t.tipo_documental or t.fecha_texto or t.detalle for t in tramites)
            if sin_trabajar and h.estado == "borrador":
                r = hoja.proponer_desde_ocr(ctx, proyecto, h, reemplazar=False)
                hechos.append(f"hoja propuesta desde el OCR: {r['frase']}")
        if h.estado == "en_revision":
            return fin("hoja_en_verificacion", "La verifica una persona distinta de quien la elaboró")
        if h.estado == "devuelta":
            return fin("hoja_devuelta", h.novedad or "Corregir lo observado y volver a enviar")
        if h.estado == "borrador":
            return fin("hoja_por_confirmar", "Confirmar o corregir lo propuesto y enviarla a verificación" if ocr_completo else "Partir en documentos y completar los trámites (sin OCR)")
    if procesos["isadg"]:
        if not procesos["hoja_control"] and lector.disponible() and not ocr_completo:
            return fin("ocr", "Esperando el OCR para describir", seguir=True)
        d = descripcion.descripcion_de(ctx, u)
        if d is None:
            d = descripcion.crear(ctx, proyecto, u)
            d.creado_por = None  # la creó el flujo: elabora quien la confirma y la envía
            ctx.db.commit()
            hechos.append("descripción ISAD(G) propuesta")
        elif d.estado in descripcion.ESTADOS_EDITABLES:
            descripcion.recalcular(ctx, proyecto, u, d)
        if d.estado == "en_revision":
            return fin("descripcion_en_revision", "La aprueba una persona distinta de quien la elaboró")
        if d.estado == "devuelta":
            return fin("descripcion_devuelta", d.novedad or "Corregir lo observado y volver a enviar")
        if d.estado == "borrador":
            return fin("descripcion_por_confirmar", "Escribir o confirmar el título y el alcance, y enviarla a revisión")
    return fin("listo", "Todo lo que el lote lleva está hecho")


def ejecutar(db, trabajo: Trabajo) -> None:
    """Corre un trabajo tomado de la cola. Si falla, lo deja con su error (y lo reintenta hasta tres veces)."""
    ctx = contexto_de(db, trabajo)
    if trabajo.tipo == "paquete":
        _paquete(db, ctx, trabajo)
        return
    try:
        u = db.get(UnidadDocumental, trabajo.unidad_id)
        p = db.get(Proyecto, trabajo.proyecto_id)
        r = paso(ctx, p, u)
        if r["hechos"]:
            ctx.auditar(accion="FLUJO_AUTOMATICO", objeto="UnidadDocumental", objeto_id=u.id,
                        detalle=f"{p.codigo} · {u.identificador} · {'; '.join(r['hechos'])} · queda en: {ETAPAS[r['etapa']][0]} · originado por: {trabajo.motivo}")
        trabajo.estado, trabajo.resultado, trabajo.terminado_en, trabajo.error = "hecho", {"etapa": r["etapa"], "hechos": r["hechos"]}, ahora_utc(), ""
        if r["seguir"]:
            encolar(db, trabajo.tenant_id, trabajo.proyecto_id, trabajo.unidad_id, trabajo.usuario_id, "continúa el OCR")
        db.commit()
    except Exception as e:  # noqa: BLE001 — un trabajo que falla no tumba al trabajador: queda registrado
        db.rollback()
        t = db.get(Trabajo, trabajo.id)
        mensaje = str(e) if isinstance(e, ErrorDominio) else f"{type(e).__name__}: {e}"
        t.error, t.terminado_en = mensaje[:1000], ahora_utc()
        t.estado = "pendiente" if t.intentos < MAX_INTENTOS and not isinstance(e, ErrorDominio) else "error"
        if t.estado == "error" and t.unidad_id:
            u = db.get(UnidadDocumental, t.unidad_id)
            _registrar(contexto_de(db, t), u, "error", mensaje[:500])
        db.commit()


def _paquete(db, ctx, trabajo: Trabajo) -> None:
    """Arma un paquete de entrega (D-40). Si falla, el paquete queda con su error; no se reintenta solo."""
    from arca.modelos import PaqueteEntrega  # noqa: PLC0415
    from arca.modulos.entrega import servicios as entrega  # noqa: PLC0415 — el flujo es el único que orquesta módulos

    pid = uuid.UUID(str((trabajo.parametros or {}).get("paquete_id")))
    try:
        entrega.generar(ctx, db.get(PaqueteEntrega, pid))
        t = db.get(Trabajo, trabajo.id)
        t.estado, t.resultado, t.terminado_en, t.error = "hecho", {"paquete_id": str(pid)}, ahora_utc(), ""
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        mensaje = (str(e) if isinstance(e, ErrorDominio) else f"{type(e).__name__}: {e}")[:1000]
        t, p = db.get(Trabajo, trabajo.id), db.get(PaqueteEntrega, pid)
        t.estado, t.error, t.terminado_en = "error", mensaje, ahora_utc()
        if p:
            p.estado, p.error, p.terminado_en = "error", mensaje, ahora_utc()
        db.commit()


def iniciar(ctx, proyecto: Proyecto, solo_pendientes: bool = True) -> int:
    """Pone en cola todas las unidades digitalizadas (o las que no están listas) del proyecto."""
    listos = set(ctx.db.scalars(select(FlujoUnidad.unidad_id).where(FlujoUnidad.proyecto_id == proyecto.id, FlujoUnidad.etapa == "listo"))) if solo_pendientes else set()
    ids = set(ctx.db.scalars(select(RecursoDigital.unidad_id).where(RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.unidad_id.is_not(None))))
    n = sum(1 for uid in ids - listos if encolar(ctx.db, ctx.tenant_id, proyecto.id, uid, ctx.usuario.id, "iniciado desde el tablero del flujo"))
    ctx.auditar(accion="INICIAR_FLUJO", objeto="Proyecto", objeto_id=proyecto.id, detalle=f"{proyecto.codigo} · {n} unidades en cola")
    ctx.db.commit()
    return n


def resumen(ctx, proyecto: Proyecto) -> dict[str, Any]:
    etapas = dict(ctx.db.execute(select(FlujoUnidad.etapa, func.count()).where(FlujoUnidad.proyecto_id == proyecto.id).group_by(FlujoUnidad.etapa)).all())
    cola = dict(ctx.db.execute(select(Trabajo.estado, func.count()).where(Trabajo.proyecto_id == proyecto.id).group_by(Trabajo.estado)).all())
    ultimo = ctx.db.scalar(select(func.max(Trabajo.terminado_en)).where(Trabajo.proyecto_id == proyecto.id))
    a = ajustes()
    en_proceso = a.trabajos_en_proceso if a.trabajos_en_proceso is not None else a.entorno == "local"
    return {"etapas": [{"clave": k, "nombre": n, "espera_persona": e, "unidades": etapas.get(k, 0)} for k, (n, e) in ETAPAS.items()],
            "cola": {"pendientes": cola.get("pendiente", 0), "en_curso": cola.get("en_curso", 0), "hechos": cola.get("hecho", 0), "errores": cola.get("error", 0)},
            "ultimo": ultimo, "trabajador": "en la aplicación" if en_proceso else "proceso aparte (python -m arca.modulos.flujo.trabajador)"}


def unidades(ctx, proyecto: Proyecto, etapa: str | None, desplazamiento: int, limite: int) -> tuple[int, list[dict[str, Any]]]:
    consulta = select(FlujoUnidad, UnidadDocumental).join(UnidadDocumental, FlujoUnidad.unidad_id == UnidadDocumental.id).where(FlujoUnidad.proyecto_id == proyecto.id)
    if etapa:
        consulta = consulta.where(FlujoUnidad.etapa == etapa)
    total = ctx.db.scalar(select(func.count()).select_from(consulta.subquery()))
    filas = ctx.db.execute(consulta.order_by(FlujoUnidad.espera_persona.desc(), FlujoUnidad.actualizado_en.desc()).offset(desplazamiento).limit(limite)).all()
    return total, [{"unidad_id": u.id, "identificador": u.identificador, "nombre": u.nombre, "caja": u.caja, "etapa": f.etapa, "etapa_nombre": ETAPAS[f.etapa][0],
                    "espera_persona": f.espera_persona, "detalle": f.detalle, "hechos": (f.hechos or [])[-5:], "actualizado_en": f.actualizado_en} for f, u in filas]


def errores(ctx, proyecto: Proyecto) -> list[dict[str, Any]]:
    filas = ctx.db.execute(select(Trabajo, UnidadDocumental.identificador).outerjoin(UnidadDocumental, Trabajo.unidad_id == UnidadDocumental.id)
                           .where(Trabajo.proyecto_id == proyecto.id, Trabajo.estado == "error").order_by(Trabajo.terminado_en.desc()).limit(50)).all()
    return [{"id": t.id, "unidad": ident, "motivo": t.motivo, "error": t.error, "intentos": t.intentos, "terminado_en": t.terminado_en} for t, ident in filas]


def reintentar(ctx, proyecto: Proyecto, trabajo_id: uuid.UUID) -> None:
    t = ctx.db.get(Trabajo, trabajo_id)
    if t is None or t.proyecto_id != proyecto.id or t.estado != "error":
        from arca.nucleo.errores import NoEncontrado  # noqa: PLC0415

        raise NoEncontrado("El trabajo no existe o no tiene error")
    t.estado, t.intentos, t.error = "pendiente", 0, ""
    if t.tipo == "paquete":
        from arca.modelos import PaqueteEntrega  # noqa: PLC0415

        p = ctx.db.get(PaqueteEntrega, uuid.UUID(str((t.parametros or {}).get("paquete_id"))))
        if p:
            p.estado, p.error = "en_cola", ""
    ctx.auditar(accion="REINTENTAR_TRABAJO", objeto="Trabajo", objeto_id=t.id, detalle=t.motivo)
    ctx.db.commit()
