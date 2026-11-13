"""M13 · OCR del expediente digitalizado: leer cada página una sola vez, guardar el texto con su confianza.

El trabajo se hace por tandas (un número máximo de páginas por petición) hasta que exista la cola de procesos
en segundo plano (D-04). Volver a llamar continúa donde quedó: una página ya leída no se vuelve a leer, salvo que
se pida expresamente.
"""

import io
import time
import uuid
from typing import Any

from sqlalchemy import func, select

from arca.modelos import EstadoProyecto, Proyecto, RecursoDigital, TextoPagina, UnidadDocumental
from arca.modelos.base import ahora_utc
from arca.modulos.m10_digitalizacion.paginas import NO_CUENTAN, imagen_pagina, paginas
from arca.modulos.m13_ocr import lector
from arca.nucleo.errores import TransicionInvalida

CONFIANZA_BAJA = 60
SEGURIDAD_GIRO = 2.0  # «Orientation confidence» de Tesseract desde la que se gira sin comprobar


def _abierto(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


def leidas(ctx, recurso_ids: set[uuid.UUID]) -> dict[tuple[uuid.UUID, int], TextoPagina]:
    if not recurso_ids:
        return {}
    return {(t.recurso_id, t.pagina): t for t in ctx.db.scalars(select(TextoPagina).where(TextoPagina.recurso_id.in_(recurso_ids)))}


def textos(ctx, unidad: UnidadDocumental) -> list[dict[str, Any]]:
    """Por cada página del expediente: su texto, su confianza y su estado de OCR (o «pendiente»)."""
    lista = paginas(ctx, unidad)
    hechas = leidas(ctx, {p["recurso_id"] for p in lista})
    salida = []
    for p in lista:
        t = hechas.get((p["recurso_id"], p["pagina_en_archivo"]))
        salida.append({"n": p["n"], "estado": t.estado if t else "pendiente", "texto": t.texto if t else "", "confianza": t.confianza if t else None,
                       "palabras": t.palabras if t else 0, "lineas": t.lineas if t else [], "motor": t.motor if t else "", "detalle": t.detalle if t else ""})
    return salida


def _girar(imagen: bytes, giro: int) -> bytes:
    from PIL import Image  # noqa: PLC0415

    salida = io.BytesIO()
    Image.open(io.BytesIO(imagen)).rotate(-giro, expand=True).save(salida, "PNG")
    return salida.getvalue()


def _leer_derecha(imagen: bytes, idioma: str) -> tuple[int, lector.Lectura]:
    """Endereza la página antes de leerla. Si el detector de orientación está seguro, se gira; si duda (pasa en páginas
    con poco texto), se lee de las dos formas y se queda la lectura más confiable. Devuelve (grados girados, lectura)."""
    giro, seguridad = lector.orientacion(imagen)
    if not giro:
        return 0, lector.leer(imagen, idioma)
    girada = lector.leer(_girar(imagen, giro), idioma)
    if seguridad >= SEGURIDAD_GIRO:
        return giro, girada
    tal_cual = lector.leer(imagen, idioma)
    puntaje = lambda x: (x.confianza or 0) * min(x.palabras, 50)  # noqa: E731
    return (giro, girada) if puntaje(girada) > puntaje(tal_cual) else (0, tal_cual)


def leer_unidad(ctx, proyecto: Proyecto, unidad: UnidadDocumental, limite: int = 30, releer: bool = False, idioma: str = "spa") -> dict[str, Any]:
    """Lee con OCR las páginas pendientes del expediente, hasta `limite` por llamada."""
    _abierto(proyecto)
    lector.exigir(idioma)
    lista = paginas(ctx, unidad)
    hechas = leidas(ctx, {p["recurso_id"] for p in lista})
    procesadas = errores = 0
    for p in lista:
        clave = (p["recurso_id"], p["pagina_en_archivo"])
        anterior = hechas.get(clave)
        if anterior and not releer:
            continue
        if procesadas >= limite:
            break
        inicio = time.monotonic()
        try:
            imagen = imagen_pagina(ctx, unidad, p["n"], ancho=6000, corregir=False)
            giro, r = _leer_derecha(imagen, idioma)
            estado, texto, lineas, conf, palabras, detalle = ("leida" if r.palabras else "sin_texto"), r.texto, [[x.texto, x.confianza] for x in r.lineas], r.confianza, r.palabras, ""
        except Exception as e:  # noqa: BLE001 — una página que no se lee es un hallazgo, no una caída del lote
            estado, texto, lineas, conf, palabras, detalle, giro = "error", "", [], None, 0, str(e)[:300], 0
            errores += 1
        t = anterior or TextoPagina(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, recurso_id=p["recurso_id"], pagina=p["pagina_en_archivo"], motor="")
        t.estado, t.texto, t.lineas, t.confianza, t.palabras, t.detalle = estado, texto, lineas, conf, palabras, detalle
        t.motor, t.idioma, t.duracion_ms, t.creado_en, t.creado_por = lector.version(), idioma, int((time.monotonic() - inicio) * 1000), ahora_utc(), ctx.usuario.id
        t.rotacion = giro if estado != "error" else 0
        if anterior is None:
            ctx.db.add(t)
        procesadas += 1
        ctx.db.flush()
    pendientes = sum(1 for p in lista if (p["recurso_id"], p["pagina_en_archivo"]) not in leidas(ctx, {p["recurso_id"] for p in lista}))
    if procesadas:
        ctx.auditar(accion="OCR", objeto="UnidadDocumental", objeto_id=unidad.id,
                    detalle=f"{unidad.identificador} · {procesadas} páginas leídas con {lector.version()} ({idioma}) · {errores} con error · {pendientes} pendientes")
    ctx.db.commit()
    return {"procesadas": procesadas, "errores": errores, "pendientes": pendientes, "paginas": len(lista), "motor": lector.version()}


def resumen(ctx, proyecto: Proyecto) -> dict[str, Any]:
    """Cuántas páginas digitalizadas tiene el proyecto y cuántas ya pasaron por el OCR, con su confianza."""
    total = sum(max(1, n or 1) for n in ctx.db.scalars(select(RecursoDigital.paginas).where(
        RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.unidad_id.is_not(None), RecursoDigital.estado.not_in(NO_CUENTAN))))
    filas = ctx.db.execute(select(TextoPagina.estado, func.count(), func.avg(TextoPagina.confianza)).where(TextoPagina.proyecto_id == proyecto.id).group_by(TextoPagina.estado)).all()
    por_estado = {e: n for e, n, _ in filas}
    leidas_conf = next((c for e, _, c in filas if e == "leida"), None)
    bajas = int(ctx.db.scalar(select(func.count()).where(TextoPagina.proyecto_id == proyecto.id, TextoPagina.estado == "leida", TextoPagina.confianza < CONFIANZA_BAJA)) or 0)
    hechas = sum(por_estado.values())
    return {"disponible": lector.disponible(), "motor": lector.version(), "idiomas": list(lector.idiomas()), "paginas": total, "leidas": por_estado.get("leida", 0),
            "sin_texto": por_estado.get("sin_texto", 0), "errores": por_estado.get("error", 0), "pendientes": max(0, total - hechas),
            "confianza_media": round(leidas_conf, 1) if leidas_conf is not None else None, "confianza_baja": bajas}


def leer_proyecto(ctx, proyecto: Proyecto, limite: int = 30) -> dict[str, Any]:
    """Una tanda sobre todo el proyecto: sigue con el primer expediente que tenga páginas pendientes."""
    _abierto(proyecto)
    lector.exigir()
    hechas_total = {"procesadas": 0, "errores": 0, "unidades": []}
    ids = list(ctx.db.scalars(select(RecursoDigital.unidad_id).where(RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.unidad_id.is_not(None),
                                                                     RecursoDigital.estado.not_in(NO_CUENTAN)).distinct()))
    for uid in ids:
        if hechas_total["procesadas"] >= limite:
            break
        u = ctx.db.get(UnidadDocumental, uid)
        r = leer_unidad(ctx, proyecto, u, limite - hechas_total["procesadas"])
        if r["procesadas"]:
            hechas_total["procesadas"] += r["procesadas"]
            hechas_total["errores"] += r["errores"]
            hechas_total["unidades"].append(u.identificador)
    return {**hechas_total, **{k: v for k, v in resumen(ctx, proyecto).items() if k in ("pendientes", "paginas", "leidas")}}
