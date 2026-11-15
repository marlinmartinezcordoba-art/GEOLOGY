"""Alistamiento físico por expediente (D-44).

El alistamiento es el trabajo físico sobre cada expediente antes de digitalizarlo: depurar, ordenar
cronológicamente, foliar, retirar el material abrasivo, cambiar la carpeta, rotular. Es lo que más se paga en un
proyecto de historias laborales y lo que más revisa la interventoría.

- **Plan.** La dirección fija, con motivo, las actividades del proyecto: código, nombre, si piden cantidad (folios o
  unidades) y si son obligatorias. ARCA trae una propuesta de ejemplo que se ajusta al pliego.
- **Registro.** El equipo marca una actividad hecha por expediente o por caja entera, con la cantidad de cada
  expediente cuando la actividad la pide (para la foliación, ARCA sugiere los folios del FUID). Queda quién y cuándo.
  Deshacer exige motivo y queda en la auditoría.
- **Avance.** Por caja y por actividad, y cada actividad se puede contar sola en productividad
  (`alistamiento.<codigo>` cuenta expedientes; `alistamiento.<codigo>.cantidad` suma la cantidad).
- **Controles.** La hoja de control avisa si al expediente le falta alistamiento o si la foliación registrada no
  coincide con los folios de la hoja. Si el plan lo exige, el paquete de entrega solo lleva expedientes alistados.
"""

import re
import uuid
from typing import Any

from sqlalchemy import select

from arca.modelos import EstadoProyecto, IntervencionExpediente, PlanAlistamiento, Proyecto, UnidadDocumental, Usuario
from arca.modelos.base import ahora_utc
from arca.modulos.m08_inventarios.fuid import clave_de
from arca.nucleo.errores import DatosInvalidos, NoEncontrado, TransicionInvalida

CANTIDADES = {"ninguna": "Sin cantidad", "folios": "Folios", "unidades": "Unidades (carpetas, ganchos…)"}
PROPUESTA = [
    {"codigo": "depuracion", "nombre": "Depuración (retiro de duplicados y documentos de apoyo)", "cantidad": "ninguna", "obligatoria": True},
    {"codigo": "ordenacion", "nombre": "Ordenación cronológica", "cantidad": "ninguna", "obligatoria": True},
    {"codigo": "foliacion", "nombre": "Foliación", "cantidad": "folios", "obligatoria": True},
    {"codigo": "material", "nombre": "Retiro de material abrasivo (ganchos, clips, grapas)", "cantidad": "ninguna", "obligatoria": True},
    {"codigo": "carpeta", "nombre": "Cambio de unidad de conservación (carpeta)", "cantidad": "unidades", "obligatoria": True},
    {"codigo": "rotulacion", "nombre": "Rotulación de la carpeta", "cantidad": "ninguna", "obligatoria": True},
]
MAX_POR_REGISTRO = 2000


def _abierto(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


# --- Plan -------------------------------------------------------------------------------------


def plan_de(ctx, proyecto: Proyecto) -> PlanAlistamiento | None:
    return ctx.db.scalar(select(PlanAlistamiento).where(PlanAlistamiento.proyecto_id == proyecto.id))


def ver_plan(ctx, proyecto: Proyecto) -> dict[str, Any]:
    plan = plan_de(ctx, proyecto)
    if plan is None:
        return {"vigente": False, "actividades": PROPUESTA, "exigir_para_entrega": True, "cantidades": CANTIDADES,
                "aviso": "Actividades de ejemplo: ajústelas al pliego y guárdelas para empezar a registrar."}
    return {"vigente": True, "actividades": plan.actividades, "exigir_para_entrega": plan.exigir_para_entrega, "version": plan.version,
            "motivo": plan.motivo, "actualizado_en": plan.actualizado_en, "cantidades": CANTIDADES}


def guardar_plan(ctx, proyecto: Proyecto, actividades: list[dict[str, Any]], exigir: bool, motivo: str) -> PlanAlistamiento:
    _abierto(proyecto)
    limpias, codigos, errores = [], set(), []
    for a in actividades:
        codigo = re.sub(r"[^a-z0-9_]", "_", str(a.get("codigo") or "").strip().lower())[:40]
        nombre = str(a.get("nombre") or "").strip()[:200]
        cantidad = a.get("cantidad") or "ninguna"
        if not codigo or not nombre:
            errores.append(f"Actividad «{nombre or codigo}»: le falta el código o el nombre")
        elif codigo in codigos:
            errores.append(f"El código «{codigo}» está repetido")
        elif cantidad not in CANTIDADES:
            errores.append(f"Actividad «{nombre}»: la cantidad es «ninguna», «folios» o «unidades»")
        else:
            codigos.add(codigo)
            limpias.append({"codigo": codigo, "nombre": nombre, "cantidad": cantidad, "obligatoria": bool(a.get("obligatoria", True))})
    if not limpias:
        errores.append("El plan necesita al menos una actividad")
    if errores:
        raise DatosInvalidos("; ".join(errores))
    plan = plan_de(ctx, proyecto)
    if plan is None:
        plan = PlanAlistamiento(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, version=0)
        ctx.db.add(plan)
    plan.actividades, plan.exigir_para_entrega, plan.motivo = limpias, exigir, motivo.strip()
    plan.version, plan.actualizado_en, plan.actualizado_por = (plan.version or 0) + 1, ahora_utc(), ctx.usuario.id
    ctx.auditar(accion="PLAN_ALISTAMIENTO", objeto="Proyecto", objeto_id=proyecto.id,
                detalle=f"{proyecto.codigo} · v{plan.version} · {', '.join(a['nombre'] for a in limpias)} · {motivo.strip()}")
    ctx.db.commit()
    return plan


def _exigir_plan(ctx, proyecto: Proyecto) -> PlanAlistamiento:
    plan = plan_de(ctx, proyecto)
    if plan is None:
        raise TransicionInvalida("Primero la dirección debe guardar las actividades de alistamiento del proyecto")
    return plan


# --- Registro ---------------------------------------------------------------------------------


def _unidades(ctx, proyecto: Proyecto, cajas: list[str], unidades: list[uuid.UUID]) -> list[UnidadDocumental]:
    salida: dict[uuid.UUID, UnidadDocumental] = {}
    if cajas:
        claves = {clave_de(c) for c in cajas if c.strip()}
        for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id, UnidadDocumental.caja.is_not(None))):
            if clave_de(u.caja) in claves:
                salida[u.id] = u
    for uid in unidades:
        u = ctx.db.get(UnidadDocumental, uid)
        if u is None or u.proyecto_id != proyecto.id:
            raise NoEncontrado("Una de las unidades no es del proyecto")
        salida[u.id] = u
    return sorted(salida.values(), key=lambda u: (u.caja or "", u.identificador))


def registrar(ctx, proyecto: Proyecto, actividad: str, cajas: list[str], unidades: list[uuid.UUID], cantidades: dict[str, int], observacion: str) -> int:
    """Marca la actividad hecha en las unidades (de las cajas indicadas o una por una). Volver a registrar actualiza."""
    _abierto(proyecto)
    plan = _exigir_plan(ctx, proyecto)
    a = next((x for x in plan.actividades if x["codigo"] == actividad), None)
    if a is None:
        raise DatosInvalidos(f"La actividad «{actividad}» no está en el plan de alistamiento")
    lista = _unidades(ctx, proyecto, cajas, unidades)
    if not lista:
        raise DatosInvalidos("No hay expedientes para registrar: indique las cajas o las unidades")
    if len(lista) > MAX_POR_REGISTRO:
        raise DatosInvalidos(f"Son {len(lista)} expedientes: registre de a {MAX_POR_REGISTRO} como máximo")
    faltan = []
    if a["cantidad"] != "ninguna":
        for u in lista:
            valor = cantidades.get(str(u.id))
            if valor is None or int(valor) < 0:
                faltan.append(u.identificador)
        if faltan:
            raise DatosInvalidos(f"«{a['nombre']}» pide la cantidad de {CANTIDADES[a['cantidad']].lower()} de cada expediente; falta en: {', '.join(faltan[:10])}")
    existentes = {i.unidad_id: i for i in ctx.db.scalars(select(IntervencionExpediente).where(
        IntervencionExpediente.unidad_id.in_([u.id for u in lista]), IntervencionExpediente.actividad == actividad))}
    ahora = ahora_utc()
    for u in lista:
        i = existentes.get(u.id) or IntervencionExpediente(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, unidad_id=u.id, actividad=actividad)
        if u.id not in existentes:
            ctx.db.add(i)
        i.cantidad = int(cantidades[str(u.id)]) if a["cantidad"] != "ninguna" else None
        i.observacion, i.hecho_en, i.hecho_por = observacion.strip()[:1000], ahora, ctx.usuario.id
    ctx.auditar(accion="REGISTRAR_ALISTAMIENTO", objeto="Proyecto", objeto_id=proyecto.id,
                detalle=f"{proyecto.codigo} · {a['nombre']} · {len(lista)} expedientes" + (f" · cajas {', '.join(cajas[:10])}" if cajas else "")
                + (f" · {sum(int(cantidades[str(u.id)]) for u in lista)} {a['cantidad']}" if a["cantidad"] != "ninguna" else ""))
    ctx.db.commit()
    return len(lista)


def deshacer(ctx, proyecto: Proyecto, unidad_id: uuid.UUID, actividad: str, motivo: str) -> None:
    _abierto(proyecto)
    i = ctx.db.scalar(select(IntervencionExpediente).where(IntervencionExpediente.unidad_id == unidad_id, IntervencionExpediente.actividad == actividad))
    if i is None or i.proyecto_id != proyecto.id:
        raise NoEncontrado("Esa actividad no está registrada en el expediente")
    u = ctx.db.get(UnidadDocumental, unidad_id)
    ctx.db.delete(i)
    ctx.auditar(accion="DESHACER_ALISTAMIENTO", objeto="UnidadDocumental", objeto_id=unidad_id, detalle=f"{u.identificador} · {actividad} · {motivo.strip()}")
    ctx.db.commit()


# --- Avance y controles -----------------------------------------------------------------------


def _hechas(ctx, proyecto: Proyecto) -> dict[uuid.UUID, dict[str, IntervencionExpediente]]:
    salida: dict[uuid.UUID, dict[str, IntervencionExpediente]] = {}
    for i in ctx.db.scalars(select(IntervencionExpediente).where(IntervencionExpediente.proyecto_id == proyecto.id)):
        salida.setdefault(i.unidad_id, {})[i.actividad] = i
    return salida


def pendientes_de(ctx, proyecto: Proyecto, u: UnidadDocumental, plan: PlanAlistamiento | None = None) -> list[str]:
    """Nombres de las actividades obligatorias que le faltan al expediente (vacío si no hay plan)."""
    plan = plan or plan_de(ctx, proyecto)
    if plan is None:
        return []
    hechas = set(ctx.db.scalars(select(IntervencionExpediente.actividad).where(IntervencionExpediente.unidad_id == u.id)))
    return [a["nombre"] for a in plan.actividades if a["obligatoria"] and a["codigo"] not in hechas]


def folios_registrados(ctx, u: UnidadDocumental) -> int | None:
    """Los folios que dejó la foliación del alistamiento (la primera actividad que cuenta folios)."""
    proyecto = ctx.db.get(Proyecto, u.proyecto_id)
    plan = plan_de(ctx, proyecto)
    if plan is None:
        return None
    codigos = [a["codigo"] for a in plan.actividades if a["cantidad"] == "folios"]
    if not codigos:
        return None
    return ctx.db.scalar(select(IntervencionExpediente.cantidad).where(IntervencionExpediente.unidad_id == u.id, IntervencionExpediente.actividad == codigos[0]))


def avisos_hoja(ctx, u: UnidadDocumental, total_folios: int | None) -> list[str]:
    proyecto = ctx.db.get(Proyecto, u.proyecto_id)
    plan = plan_de(ctx, proyecto)
    if plan is None:
        return []
    avisos = []
    faltan = pendientes_de(ctx, proyecto, u, plan)
    if faltan:
        avisos.append(f"alistamiento físico pendiente: {', '.join(faltan)}")
    folios = folios_registrados(ctx, u)
    if folios is not None and total_folios and folios != total_folios:
        avisos.append(f"la foliación del alistamiento registró {folios} folios y la hoja de control suma {total_folios}")
    return avisos


def cajas(ctx, proyecto: Proyecto) -> dict[str, Any]:
    """Avance por caja: cuántos expedientes tienen cada actividad hecha."""
    plan = plan_de(ctx, proyecto)
    actividades = plan.actividades if plan else []
    hechas = _hechas(ctx, proyecto)
    por_caja: dict[str, dict[str, Any]] = {}
    for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id)):
        caja = u.caja or ""
        c = por_caja.setdefault(caja, {"caja": caja, "expedientes": 0, "hechas": dict.fromkeys((a["codigo"] for a in actividades), 0), "completos": 0})
        c["expedientes"] += 1
        h = hechas.get(u.id, {})
        for a in actividades:
            if a["codigo"] in h:
                c["hechas"][a["codigo"]] += 1
        if actividades and all(a["codigo"] in h for a in actividades if a["obligatoria"]):
            c["completos"] += 1
    filas = sorted(por_caja.values(), key=lambda x: (clave_de(x["caja"]) if x["caja"] else "~"))
    total = sum(c["expedientes"] for c in filas)
    resumen = {"expedientes": total, "completos": sum(c["completos"] for c in filas),
               "por_actividad": {a["codigo"]: sum(c["hechas"][a["codigo"]] for c in filas) for a in actividades}}
    return {"actividades": actividades, "resumen": resumen, "cajas": filas}


def expedientes(ctx, proyecto: Proyecto, caja: str) -> list[dict[str, Any]]:
    """Los expedientes de una caja con lo que tiene hecho cada uno (quién, cuándo, cantidad)."""
    hechas = _hechas(ctx, proyecto)
    quienes = {u.id: u.nombre_completo for u in ctx.db.scalars(select(Usuario).where(Usuario.id.in_(
        {i.hecho_por for h in hechas.values() for i in h.values() if i.hecho_por})))} if hechas else {}
    clave = clave_de(caja) if caja else ""
    salida = []
    for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id).order_by(UnidadDocumental.identificador)):
        if (clave_de(u.caja) if u.caja else "") != clave:
            continue
        h = hechas.get(u.id, {})
        salida.append({"unidad_id": u.id, "identificador": u.identificador, "nombre": u.nombre, "carpeta": u.carpeta, "folios_fuid": u.folios,
                       "hechas": {k: {"cantidad": i.cantidad, "observacion": i.observacion, "hecho_en": i.hecho_en, "hecho_por": quienes.get(i.hecho_por)} for k, i in h.items()}})
    return salida


def eventos_productividad(ctx, proyecto: Proyecto, fuente: str) -> list[tuple[Any, float]]:
    """Para productividad: `alistamiento.<codigo>` cuenta expedientes; `alistamiento.<codigo>.cantidad` suma la cantidad."""
    partes = fuente.split(".")
    if len(partes) < 2:
        return []
    codigo, sumar = partes[1], len(partes) > 2 and partes[2] == "cantidad"
    filas = ctx.db.execute(select(IntervencionExpediente.hecho_en, IntervencionExpediente.cantidad).where(
        IntervencionExpediente.proyecto_id == proyecto.id, IntervencionExpediente.actividad == codigo)).all()
    return [(h, (c or 0) if sumar else 1) for h, c in filas]
