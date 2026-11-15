"""Inspección de calidad por lote con muestreo de aceptación (D-42).

1. **Plan.** La dirección fija, con motivo, el plan del proyecto: qué se inspecciona (expedientes o imágenes), cuánto se
   muestrea (un porcentaje con un mínimo, o la tabla de tamaños que pida el pliego), el catálogo de defectos con su
   severidad y cuántos defectos de cada severidad se aceptan. ARCA trae una propuesta, pero no inspecciona hasta que la
   dirección guarde un plan: los valores los pone el pliego.
2. **Muestra.** Quien inspecciona abre la inspección de un lote (de la base de cajas). ARCA cuenta el lote, calcula la
   muestra y la elige al azar con una semilla registrada: la misma semilla da la misma muestra, así cualquiera puede
   comprobarla.
3. **Revisión.** Por cada elemento de la muestra se anotan sus defectos (o «sin defectos»). Quien cargó un archivo no
   puede inspeccionarlo.
4. **Decisión.** Al cerrar, ARCA cuenta los defectos por severidad y decide: si alguna severidad pasa lo aceptado, el
   lote se rechaza. Nadie decide a mano. Los defectos del original (deterioro, ilegible de origen) se registran pero no
   cuentan. Un lote rechazado se corrige y se reinspecciona con una muestra nueva.

Cada inspección cerrada queda en el registro de calidad de productividad (fCalidad) y se expide un acta. Si el plan lo
pide, el paquete de entrega solo incluye expedientes de lotes aceptados.
"""

import io
import math
import random
import re
import uuid
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from arca.modelos import (
    EstadoProyecto,
    InspeccionLote,
    ItemInspeccion,
    PlanMuestreo,
    Proyecto,
    RecursoDigital,
    RegistroCalidad,
    UnidadDocumental,
    Usuario,
)
from arca.modelos.base import ahora_utc
from arca.modulos.m08_inventarios.fuid import clave_de
from arca.modulos.m10_digitalizacion.paginas import NO_CUENTAN, paginas
from arca.modulos.procesos.servicios import mapa_lotes
from arca.nucleo.errores import AccesoDenegado, DatosInvalidos, NoEncontrado, TransicionInvalida

UNIDADES = {"expedientes": "Expedientes", "imagenes": "Imágenes"}
METODOS = {"porcentaje": "Porcentaje con mínimo", "tabla": "Tabla de tamaños de muestra"}
SEVERIDADES = {"critico": "Crítico", "mayor": "Mayor", "menor": "Menor", "limitacion": "Limitación del original"}
CUENTAN = ("critico", "mayor", "menor")
PLURALES = {"critico": "críticos", "mayor": "mayores", "menor": "menores", "limitacion": "limitaciones del original"}
MAX_MUESTRA = 2000

DEFECTOS_BASE = [
    {"codigo": "faltante", "nombre": "Página o folio faltante", "severidad": "critico"},
    {"codigo": "ilegible", "nombre": "Imagen ilegible por la captura", "severidad": "critico"},
    {"codigo": "ajena", "nombre": "Imagen de otro expediente", "severidad": "critico"},
    {"codigo": "orden", "nombre": "Páginas fuera de orden", "severidad": "mayor"},
    {"codigo": "recortada", "nombre": "Imagen recortada o incompleta", "severidad": "mayor"},
    {"codigo": "folios", "nombre": "Folios mal contados en la hoja de control", "severidad": "mayor"},
    {"codigo": "dato", "nombre": "Dato de la hoja de control errado", "severidad": "mayor"},
    {"codigo": "inclinada", "nombre": "Imagen inclinada", "severidad": "menor"},
    {"codigo": "ruido", "nombre": "Ruido, manchas o bordes negros", "severidad": "menor"},
    {"codigo": "contraste", "nombre": "Brillo o contraste deficiente", "severidad": "menor"},
    {"codigo": "deterioro", "nombre": "Deterioro del documento original", "severidad": "limitacion"},
    {"codigo": "origen_ilegible", "nombre": "Original ilegible de origen", "severidad": "limitacion"},
]
PROPUESTA = {"unidad": "expedientes", "metodo": "porcentaje", "porcentaje": 10.0, "minimo": 5, "tabla": [],
             "aceptacion": {"critico": 0, "mayor": 1, "menor": 3}, "defectos": DEFECTOS_BASE, "frente": "", "exigir_para_entrega": True}


def _abierto(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


# --- Plan --------------------------------------------------------------------------------------


def plan_de(ctx, proyecto: Proyecto) -> PlanMuestreo | None:
    return ctx.db.scalar(select(PlanMuestreo).where(PlanMuestreo.proyecto_id == proyecto.id))


def como_dict(plan: PlanMuestreo) -> dict[str, Any]:
    return {"unidad": plan.unidad, "metodo": plan.metodo, "porcentaje": plan.porcentaje, "minimo": plan.minimo, "tabla": plan.tabla,
            "aceptacion": plan.aceptacion, "defectos": plan.defectos, "frente": plan.frente, "exigir_para_entrega": plan.exigir_para_entrega, "version": plan.version}


def ver_plan(ctx, proyecto: Proyecto) -> dict[str, Any]:
    plan = plan_de(ctx, proyecto)
    if plan is None:
        return {"vigente": False, "plan": PROPUESTA, "aviso": "Plan de ejemplo: ajústelo al pliego y guárdelo para poder inspeccionar.",
                "unidades": UNIDADES, "metodos": METODOS, "severidades": SEVERIDADES}
    return {"vigente": True, "plan": como_dict(plan), "motivo": plan.motivo, "actualizado_en": plan.actualizado_en,
            "unidades": UNIDADES, "metodos": METODOS, "severidades": SEVERIDADES}


def _validar(datos: dict[str, Any]) -> dict[str, Any]:
    errores = []
    unidad, metodo = datos.get("unidad"), datos.get("metodo")
    if unidad not in UNIDADES:
        errores.append("La unidad de inspección es «expedientes» o «imagenes»")
    if metodo not in METODOS:
        errores.append("El método es «porcentaje» o «tabla»")
    porcentaje, minimo = float(datos.get("porcentaje") or 0), int(datos.get("minimo") or 0)
    tabla = []
    if metodo == "porcentaje":
        if not 0 < porcentaje <= 100:
            errores.append("El porcentaje de muestreo va entre 0 y 100")
        if minimo < 1:
            errores.append("La muestra mínima es de al menos 1")
    if metodo == "tabla":
        for i, f in enumerate(sorted(datos.get("tabla") or [], key=lambda x: int(x.get("desde") or 0)), start=1):
            desde, hasta, muestra = int(f.get("desde") or 0), int(f.get("hasta") or 0), int(f.get("muestra") or 0)
            if desde < 1 or hasta < desde or muestra < 1:
                errores.append(f"Fila {i} de la tabla: «desde» ≥ 1, «hasta» ≥ «desde» y muestra ≥ 1")
            elif tabla and desde <= tabla[-1]["hasta"]:
                errores.append(f"Fila {i} de la tabla: el rango {desde}–{hasta} se cruza con el anterior")
            tabla.append({"desde": desde, "hasta": hasta, "muestra": muestra})
        if not tabla:
            errores.append("La tabla de tamaños de muestra está vacía")
    aceptacion = {}
    for s in CUENTAN:
        valor = (datos.get("aceptacion") or {}).get(s)
        if valor is None or int(valor) < 0:
            errores.append(f"Falta cuántos defectos {PLURALES[s]} se aceptan (0 o más)")
        else:
            aceptacion[s] = int(valor)
    defectos, codigos = [], set()
    for d in datos.get("defectos") or []:
        codigo = re.sub(r"[^a-z0-9_]", "_", str(d.get("codigo") or "").strip().lower())[:40]
        nombre = str(d.get("nombre") or "").strip()[:200]
        if not codigo or not nombre or d.get("severidad") not in SEVERIDADES:
            errores.append(f"Defecto «{nombre or codigo}»: le falta el código, el nombre o una severidad válida")
        elif codigo in codigos:
            errores.append(f"El código de defecto «{codigo}» está repetido")
        else:
            codigos.add(codigo)
            defectos.append({"codigo": codigo, "nombre": nombre, "severidad": d["severidad"]})
    if not any(d["severidad"] in CUENTAN for d in defectos):
        errores.append("El catálogo necesita al menos un defecto crítico, mayor o menor")
    if errores:
        raise DatosInvalidos("; ".join(errores))
    return {"unidad": unidad, "metodo": metodo, "porcentaje": porcentaje if metodo == "porcentaje" else 0, "minimo": minimo if metodo == "porcentaje" else 0,
            "tabla": tabla, "aceptacion": aceptacion, "defectos": defectos, "frente": str(datos.get("frente") or "").strip()[:40],
            "exigir_para_entrega": bool(datos.get("exigir_para_entrega", True))}


def guardar_plan(ctx, proyecto: Proyecto, datos: dict[str, Any], motivo: str) -> PlanMuestreo:
    """Lo fija la dirección, con motivo. Las inspecciones abiertas siguen con el plan con el que se abrieron."""
    _abierto(proyecto)
    v = _validar(datos)
    plan = plan_de(ctx, proyecto)
    if plan is None:
        plan = PlanMuestreo(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, version=0, **{k: v[k] for k in v})
        ctx.db.add(plan)
    else:
        for k, valor in v.items():
            setattr(plan, k, valor)
    plan.version, plan.motivo, plan.actualizado_en, plan.actualizado_por = (plan.version or 0) + 1, motivo.strip(), ahora_utc(), ctx.usuario.id
    regla = f"{v['porcentaje']:g} % (mínimo {v['minimo']})" if v["metodo"] == "porcentaje" else f"tabla de {len(v['tabla'])} rangos"
    ctx.auditar(accion="PLAN_MUESTREO", objeto="Proyecto", objeto_id=proyecto.id,
                detalle=f"{proyecto.codigo} · v{plan.version} · {UNIDADES[v['unidad']].lower()} · {regla} · aceptación C{v['aceptacion']['critico']}/M{v['aceptacion']['mayor']}/m{v['aceptacion']['menor']} · {motivo.strip()}")
    ctx.db.commit()
    return plan


def tamano_muestra(plan: dict[str, Any], tamano: int) -> int:
    if tamano <= 0:
        return 0
    if plan["metodo"] == "porcentaje":
        n = max(plan["minimo"], math.ceil(tamano * plan["porcentaje"] / 100))
    else:
        fila = next((f for f in plan["tabla"] if f["desde"] <= tamano <= f["hasta"]), None)
        if fila is None:
            raise DatosInvalidos(f"La tabla del plan no tiene un tamaño de muestra para un lote de {tamano}: complétela")
        n = fila["muestra"]
    return min(n, tamano, MAX_MUESTRA)


# --- Lotes y universo --------------------------------------------------------------------------


def _unidades_del_lote(ctx, proyecto: Proyecto, lote: str) -> list[UnidadDocumental]:
    """Las unidades digitalizadas del lote, en orden de caja e identificador (el orden fija la muestra con la semilla)."""
    mapa = mapa_lotes(ctx, proyecto)
    con_imagenes = set(ctx.db.scalars(select(RecursoDigital.unidad_id).where(RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.unidad_id.is_not(None),
                                                                              RecursoDigital.estado.not_in(NO_CUENTAN))))
    unidades = [u for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id))
                if u.id in con_imagenes and mapa.get(clave_de(u.caja or ""), "") == lote]
    return sorted(unidades, key=lambda u: (u.caja or "", u.identificador))


def _universo(ctx, proyecto: Proyecto, lote: str, unidad: str) -> list[tuple[UnidadDocumental, int | None]]:
    unidades = _unidades_del_lote(ctx, proyecto, lote)
    if unidad == "expedientes":
        return [(u, None) for u in unidades]
    return [(u, p["n"]) for u in unidades for p in paginas(ctx, u)]


def estado_lotes(ctx, proyecto: Proyecto) -> dict[str, InspeccionLote]:
    """La última inspección cerrada (aceptada o rechazada) de cada lote."""
    salida: dict[str, InspeccionLote] = {}
    for i in ctx.db.scalars(select(InspeccionLote).where(InspeccionLote.proyecto_id == proyecto.id, InspeccionLote.estado.in_(("aceptada", "rechazada")))
                            .order_by(InspeccionLote.numero)):
        salida[i.lote] = i
    return salida


def lotes(ctx, proyecto: Proyecto) -> list[dict[str, Any]]:
    mapa = mapa_lotes(ctx, proyecto)
    nombres = sorted(set(mapa.values()) | {""})
    imagenes = dict(ctx.db.execute(select(RecursoDigital.unidad_id, func.sum(func.coalesce(RecursoDigital.paginas, 1))).where(
        RecursoDigital.proyecto_id == proyecto.id, RecursoDigital.unidad_id.is_not(None), RecursoDigital.estado.not_in(NO_CUENTAN)).group_by(RecursoDigital.unidad_id)).all())
    ultimas = estado_lotes(ctx, proyecto)
    abiertas = {i.lote: i for i in ctx.db.scalars(select(InspeccionLote).where(InspeccionLote.proyecto_id == proyecto.id, InspeccionLote.estado == "abierta"))}
    cajas: dict[str, int] = {}
    for lote in mapa.values():
        cajas[lote] = cajas.get(lote, 0) + 1
    salida = []
    for nombre in nombres:
        unidades = _unidades_del_lote(ctx, proyecto, nombre)
        u = ultimas.get(nombre)
        a = abiertas.get(nombre)
        if not unidades and not u and not a and nombre == "":
            continue
        salida.append({"lote": nombre, "cajas": cajas.get(nombre, 0), "expedientes": len(unidades), "imagenes": int(sum(imagenes.get(x.id, 0) or 0 for x in unidades)),
                       "ultima": None if not u else {"id": u.id, "numero": u.numero, "estado": u.estado, "cerrada_en": u.cerrada_en},
                       "abierta": None if not a else {"id": a.id, "numero": a.numero}})
    return salida


# --- Inspección --------------------------------------------------------------------------------


def _inspeccion(ctx, proyecto: Proyecto, inspeccion_id: uuid.UUID) -> InspeccionLote:
    i = ctx.db.get(InspeccionLote, inspeccion_id)
    if i is None or i.proyecto_id != proyecto.id:
        raise NoEncontrado("La inspección no existe")
    return i


def iniciar(ctx, proyecto: Proyecto, lote: str, semilla: int | None = None) -> InspeccionLote:
    _abierto(proyecto)
    plan = plan_de(ctx, proyecto)
    if plan is None:
        raise TransicionInvalida("Primero la dirección debe guardar el plan de muestreo del proyecto")
    if ctx.db.scalar(select(InspeccionLote.id).where(InspeccionLote.proyecto_id == proyecto.id, InspeccionLote.lote == lote, InspeccionLote.estado == "abierta")):
        raise TransicionInvalida(f"El lote «{lote or 'sin lote'}» ya tiene una inspección abierta")
    p = como_dict(plan)
    universo = _universo(ctx, proyecto, lote, p["unidad"])
    if not universo:
        raise DatosInvalidos(f"El lote «{lote or 'sin lote'}» no tiene nada digitalizado para inspeccionar")
    n = tamano_muestra(p, len(universo))
    semilla = semilla if semilla is not None else random.SystemRandom().randint(1, 999_999)
    elegidos = sorted(random.Random(semilla).sample(range(len(universo)), n))
    anterior = estado_lotes(ctx, proyecto).get(lote)
    numero = (ctx.db.scalar(select(func.max(InspeccionLote.numero)).where(InspeccionLote.proyecto_id == proyecto.id)) or 0) + 1
    i = InspeccionLote(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, numero=numero, lote=lote, estado="abierta", plan=p, tamano=len(universo), muestra=n,
                       semilla=semilla, reinspeccion_de=anterior.id if anterior and anterior.estado == "rechazada" else None, creado_en=ahora_utc(), creado_por=ctx.usuario.id)
    ctx.db.add(i)
    ctx.db.flush()
    for orden, k in enumerate(elegidos, start=1):
        u, pagina = universo[k]
        ctx.db.add(ItemInspeccion(tenant_id=ctx.tenant_id, inspeccion_id=i.id, orden=orden, unidad_id=u.id, pagina=pagina))
    ctx.auditar(accion="INICIAR_INSPECCION", objeto="InspeccionLote", objeto_id=i.id,
                detalle=f"{proyecto.codigo} · n.º {numero} · lote «{lote or 'sin lote'}» · {n} de {len(universo)} {UNIDADES[p['unidad']].lower()} · semilla {semilla}"
                + (f" · reinspección de la n.º {anterior.numero}" if i.reinspeccion_de else ""))
    ctx.db.commit()
    return i


def _items(ctx, i: InspeccionLote) -> list[ItemInspeccion]:
    return list(ctx.db.scalars(select(ItemInspeccion).where(ItemInspeccion.inspeccion_id == i.id).order_by(ItemInspeccion.orden)))


def _conteo(items: list[ItemInspeccion]) -> dict[str, int]:
    conteo = dict.fromkeys(SEVERIDADES, 0)
    for it in items:
        for d in it.defectos or []:
            conteo[d["severidad"]] += 1
    return conteo


def decidir(plan: dict[str, Any], conteo: dict[str, int]) -> tuple[str, list[str]]:
    """Se rechaza si alguna severidad pasa lo que el plan acepta. Las limitaciones del original no cuentan."""
    razones = [f"{conteo[s]} defectos {PLURALES[s]} (se aceptan {plan['aceptacion'][s]})" for s in CUENTAN if conteo[s] > plan["aceptacion"][s]]
    return ("rechazada" if razones else "aceptada"), razones


def detalle(ctx, proyecto: Proyecto, inspeccion_id: uuid.UUID) -> dict[str, Any]:
    i = _inspeccion(ctx, proyecto, inspeccion_id)
    items = _items(ctx, i)
    unidades = {u.id: u for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.id.in_({it.unidad_id for it in items})))} if items else {}
    total_paginas = {uid: len(paginas(ctx, u)) for uid, u in unidades.items()}
    conteo = _conteo(items)
    resultado, razones = decidir(i.plan, conteo)
    nombres = _nombres(ctx, {i.creado_por, i.cerrada_por} | {it.revisado_por for it in items})
    return {
        "id": i.id, "numero": i.numero, "lote": i.lote, "estado": i.estado, "plan": i.plan, "tamano": i.tamano, "muestra": i.muestra, "semilla": i.semilla,
        "reinspeccion_de": i.reinspeccion_de, "observaciones": i.observaciones, "creado_en": i.creado_en, "creado_por": nombres.get(i.creado_por),
        "cerrada_en": i.cerrada_en, "cerrada_por": nombres.get(i.cerrada_por), "conteo": conteo,
        "revisados": sum(1 for it in items if it.estado == "revisado"),
        "resultado_previsto": resultado if i.estado == "abierta" else i.estado, "razones": razones,
        "items": [{"id": it.id, "orden": it.orden, "unidad_id": it.unidad_id, "identificador": unidades[it.unidad_id].identificador,
                   "nombre": unidades[it.unidad_id].nombre, "caja": unidades[it.unidad_id].caja, "pagina": it.pagina, "paginas": total_paginas[it.unidad_id], "estado": it.estado,
                   "defectos": it.defectos or [], "revisado_por": nombres.get(it.revisado_por), "revisado_en": it.revisado_en} for it in items],
    }


def _nombres(ctx, ids: set) -> dict[uuid.UUID, str]:
    ids = {x for x in ids if x}
    if not ids:
        return {}
    return {u.id: u.nombre_completo for u in ctx.db.scalars(select(Usuario).where(Usuario.id.in_(ids)))}


def revisar(ctx, proyecto: Proyecto, inspeccion_id: uuid.UUID, item_id: uuid.UUID, defectos: list[dict[str, Any]]) -> ItemInspeccion:
    """Anota los defectos de un elemento de la muestra (lista vacía = sin defectos). Se puede corregir mientras esté abierta."""
    _abierto(proyecto)
    i = _inspeccion(ctx, proyecto, inspeccion_id)
    if i.estado != "abierta":
        raise TransicionInvalida("La inspección ya está cerrada")
    it = ctx.db.get(ItemInspeccion, item_id)
    if it is None or it.inspeccion_id != i.id:
        raise NoEncontrado("El elemento no es de esta inspección")
    cargo = ctx.db.scalar(select(RecursoDigital.id).where(RecursoDigital.unidad_id == it.unidad_id, RecursoDigital.creado_por == ctx.usuario.id).limit(1))
    if cargo:
        raise AccesoDenegado("Usted cargó archivos de este expediente: lo debe inspeccionar otra persona")
    catalogo = {d["codigo"]: d for d in i.plan["defectos"]}
    anotados = []
    for d in defectos:
        c = catalogo.get(d.get("codigo"))
        if c is None:
            raise DatosInvalidos(f"El defecto «{d.get('codigo')}» no está en el catálogo del plan")
        pagina = it.pagina if it.pagina is not None else (int(d["pagina"]) if d.get("pagina") else None)
        anotados.append({"codigo": c["codigo"], "nombre": c["nombre"], "severidad": c["severidad"], "pagina": pagina, "nota": str(d.get("nota") or "").strip()[:500]})
    it.defectos, it.estado, it.revisado_en, it.revisado_por = anotados, "revisado", ahora_utc(), ctx.usuario.id
    u = ctx.db.get(UnidadDocumental, it.unidad_id)
    ctx.auditar(accion="REVISAR_MUESTRA", objeto="InspeccionLote", objeto_id=i.id,
                detalle=f"n.º {i.numero} · elemento {it.orden} · {u.identificador}" + (f" p. {it.pagina}" if it.pagina else "")
                + (" · " + ", ".join(f"{d['nombre']} ({SEVERIDADES[d['severidad']].lower()})" for d in anotados) if anotados else " · sin defectos"))
    ctx.db.commit()
    return it


def cerrar(ctx, proyecto: Proyecto, inspeccion_id: uuid.UUID, observaciones: str = "") -> InspeccionLote:
    """ARCA decide con el plan: aceptado o rechazado. Queda en el registro de calidad de productividad."""
    _abierto(proyecto)
    i = _inspeccion(ctx, proyecto, inspeccion_id)
    if i.estado != "abierta":
        raise TransicionInvalida("La inspección ya está cerrada")
    items = _items(ctx, i)
    faltan = sum(1 for it in items if it.estado != "revisado")
    if faltan:
        raise TransicionInvalida(f"Faltan {faltan} elementos de la muestra por revisar")
    conteo = _conteo(items)
    i.estado, razones = decidir(i.plan, conteo)
    i.criticos, i.mayores, i.menores, i.limitaciones = conteo["critico"], conteo["mayor"], conteo["menor"], conteo["limitacion"]
    i.observaciones, i.cerrada_en, i.cerrada_por = observaciones.strip()[:2000], ahora_utc(), ctx.usuario.id
    local = i.cerrada_en.astimezone(ZoneInfo(ctx.organizacion.zona_horaria))
    ctx.db.add(RegistroCalidad(
        tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, origen="inspeccion", creado_en=ahora_utc(), creado_por=ctx.usuario.id, fecha=local.date(),
        frente=i.plan.get("frente") or "", lote=i.lote, unidad_inspeccion=UNIDADES[i.plan["unidad"]].lower(), tamano_lote=i.tamano, muestra=i.muestra,
        criticos=i.criticos, mayores=i.mayores, menores=i.menores, limitaciones_original=i.limitaciones,
        resultado="Aprobado" if i.estado == "aceptada" else "Rechazado", analista=ctx.usuario.nombre_completo,
        observaciones=f"Inspección n.º {i.numero} en ARCA · semilla {i.semilla}" + (f" · {'; '.join(razones)}" if razones else "") + (f" · {i.observaciones}" if i.observaciones else "")))
    ctx.auditar(accion="CERRAR_INSPECCION", objeto="InspeccionLote", objeto_id=i.id,
                detalle=f"{proyecto.codigo} · n.º {i.numero} · lote «{i.lote or 'sin lote'}» · {'ACEPTADO' if i.estado == 'aceptada' else 'RECHAZADO'}"
                + f" · C{i.criticos}/M{i.mayores}/m{i.menores} (limitaciones {i.limitaciones})" + (f" · {'; '.join(razones)}" if razones else ""))
    ctx.db.commit()
    return i


def anular(ctx, proyecto: Proyecto, inspeccion_id: uuid.UUID, motivo: str) -> InspeccionLote:
    i = _inspeccion(ctx, proyecto, inspeccion_id)
    if i.estado != "abierta":
        raise TransicionInvalida("Solo se anula una inspección abierta: una cerrada es evidencia")
    i.estado, i.observaciones, i.cerrada_en, i.cerrada_por = "anulada", motivo.strip(), ahora_utc(), ctx.usuario.id
    ctx.auditar(accion="ANULAR_INSPECCION", objeto="InspeccionLote", objeto_id=i.id, detalle=f"{proyecto.codigo} · n.º {i.numero} · {motivo.strip()}")
    ctx.db.commit()
    return i


def listar(ctx, proyecto: Proyecto) -> list[dict[str, Any]]:
    filas = list(ctx.db.scalars(select(InspeccionLote).where(InspeccionLote.proyecto_id == proyecto.id).order_by(InspeccionLote.numero.desc())))
    revisados = dict(ctx.db.execute(select(ItemInspeccion.inspeccion_id, func.count()).where(ItemInspeccion.inspeccion_id.in_([i.id for i in filas]),
                                                                                          ItemInspeccion.estado == "revisado").group_by(ItemInspeccion.inspeccion_id)).all()) if filas else {}
    return [{"id": i.id, "numero": i.numero, "lote": i.lote, "estado": i.estado, "unidad": i.plan.get("unidad"), "tamano": i.tamano, "muestra": i.muestra,
             "revisados": revisados.get(i.id, 0), "semilla": i.semilla, "criticos": i.criticos, "mayores": i.mayores, "menores": i.menores, "limitaciones": i.limitaciones,
             "reinspeccion_de": i.reinspeccion_de, "creado_en": i.creado_en, "cerrada_en": i.cerrada_en} for i in filas]


def acta(ctx, proyecto: Proyecto, inspeccion_id: uuid.UUID) -> tuple[bytes, str]:
    """El acta de la inspección cerrada, en Excel: el plan, la muestra con sus defectos y la decisión."""
    import openpyxl  # noqa: PLC0415
    from openpyxl.styles import Font  # noqa: PLC0415

    d = detalle(ctx, proyecto, inspeccion_id)
    if d["estado"] not in ("aceptada", "rechazada"):
        raise TransicionInvalida("El acta se expide cuando la inspección está cerrada")
    plan = d["plan"]
    libro = openpyxl.Workbook()
    h = libro.active
    h.title = "Acta"
    regla = f"{plan['porcentaje']:g} % con mínimo de {plan['minimo']}" if plan["metodo"] == "porcentaje" else "tabla de tamaños de muestra del plan"
    filas = [
        ["Acta de inspección de calidad por lote"],
        ["Proyecto", f"{proyecto.codigo} · {proyecto.nombre}"], ["Entidad", proyecto.entidad_cliente], ["Inspección", f"n.º {d['numero']}"],
        ["Lote", d["lote"] or "Sin lote"], ["Unidad de inspección", UNIDADES[plan["unidad"]]], ["Tamaño del lote", d["tamano"]],
        ["Muestra", f"{d['muestra']} ({regla})"], ["Semilla de la muestra", d["semilla"]], ["Plan", f"versión {plan.get('version', 1)}"],
        ["Se aceptan", f"{plan['aceptacion']['critico']} críticos · {plan['aceptacion']['mayor']} mayores · {plan['aceptacion']['menor']} menores"],
        ["Encontrados", f"{d['conteo']['critico']} críticos · {d['conteo']['mayor']} mayores · {d['conteo']['menor']} menores · {d['conteo']['limitacion']} limitaciones del original (no cuentan)"],
        ["Decisión", "LOTE ACEPTADO" if d["estado"] == "aceptada" else "LOTE RECHAZADO: " + "; ".join(d["razones"])],
        ["Abrió", f"{d['creado_por']} · {d['creado_en']:%Y-%m-%d %H:%M}"], ["Cerró", f"{d['cerrada_por']} · {d['cerrada_en']:%Y-%m-%d %H:%M}"],
        ["Observaciones", d["observaciones"]], [],
        ["N.º", "Expediente", "Caja", "Página", "Defectos", "Severidad", "Nota", "Revisó"],
    ]
    for f in filas:
        h.append(f)
    for it in d["items"]:
        if not it["defectos"]:
            h.append([it["orden"], it["identificador"], it["caja"], it["pagina"], "Sin defectos", "", "", it["revisado_por"]])
        for x in it["defectos"]:
            h.append([it["orden"], it["identificador"], it["caja"], x.get("pagina") or it["pagina"], x["nombre"], SEVERIDADES[x["severidad"]], x["nota"], it["revisado_por"]])
    h["A1"].font = Font(bold=True, size=13)
    for c in h[len(filas)]:
        c.font = Font(bold=True)
    for col, ancho in zip("ABCDEFGH", (22, 40, 10, 8, 40, 22, 40, 28), strict=True):
        h.column_dimensions[col].width = ancho
    salida = io.BytesIO()
    libro.save(salida)
    ctx.auditar(accion="EXPEDIR_ACTA_INSPECCION", objeto="InspeccionLote", objeto_id=d["id"], detalle=f"{proyecto.codigo} · n.º {d['numero']}")
    ctx.db.commit()
    return salida.getvalue(), f"Acta_inspeccion_{proyecto.codigo}_n{d['numero']}.xlsx"
