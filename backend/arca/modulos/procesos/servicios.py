"""Procesos por lote: qué lleva cada lote de trabajo (el de la base de cajas): hoja de control, descripción ISAD(G) o ambas.

Módulo aparte a propósito: lo consultan la hoja de control y la descripción, y ninguno de los dos depende del otro
(D-24, D-26). Lo que no se configure para un lote toma lo del proyecto; el proyecto, si nadie lo configuró, lleva
hoja de control y no ISAD(G).
"""

from typing import Any

from sqlalchemy import func, select

from arca.modelos import CajaProyecto, ConfiguracionLote, EstadoProyecto, Proyecto, UnidadDocumental
from arca.modelos.base import ahora_utc
from arca.modulos.m08_inventarios.fuid import clave_de
from arca.nucleo.errores import DatosInvalidos, TransicionInvalida


def _abierto(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")



def lote_de(ctx, proyecto: Proyecto, unidad: UnidadDocumental) -> str:
    if not unidad.caja:
        return ""
    return ctx.db.scalar(select(CajaProyecto.lote).where(CajaProyecto.proyecto_id == proyecto.id, CajaProyecto.clave == clave_de(unidad.caja))) or ""


def configuraciones(ctx, proyecto: Proyecto) -> dict[str, ConfiguracionLote]:
    return {c.lote: c for c in ctx.db.scalars(select(ConfiguracionLote).where(ConfiguracionLote.proyecto_id == proyecto.id))}


def mapa_lotes(ctx, proyecto: Proyecto) -> dict[str, str]:
    """Lote de cada caja de la base de cajas, por su clave."""
    return dict(ctx.db.execute(select(CajaProyecto.clave, CajaProyecto.lote).where(CajaProyecto.proyecto_id == proyecto.id)).all())


def procesos_de(ctx, proyecto: Proyecto, unidad: UnidadDocumental, confs: dict[str, ConfiguracionLote] | None = None, mapa: dict[str, str] | None = None) -> dict[str, Any]:
    """Qué procesos lleva la unidad según su lote (base de cajas), o según el proyecto si su lote no está configurado."""
    confs = configuraciones(ctx, proyecto) if confs is None else confs
    lote = (mapa.get(clave_de(unidad.caja), "") if unidad.caja else "") if mapa is not None else lote_de(ctx, proyecto, unidad)
    c = confs.get(lote) if lote else None
    origen = f"lote «{lote}»" if c else "configuración del proyecto"
    c = c or confs.get("")
    return {"lote": lote, "hoja_control": c.hoja_control if c else True, "isadg": c.isadg if c else False,
            "origen": origen if c else "valor por defecto (hoja de control, sin ISAD(G))"}


def lotes(ctx, proyecto: Proyecto) -> list[dict[str, Any]]:
    """El proyecto y cada lote de la base de cajas, con lo que lleva y cuántas cajas y unidades tiene."""
    confs = configuraciones(ctx, proyecto)
    cajas = dict(ctx.db.execute(select(CajaProyecto.lote, func.count()).where(CajaProyecto.proyecto_id == proyecto.id).group_by(CajaProyecto.lote)).all())
    lote_por_caja = dict(ctx.db.execute(select(CajaProyecto.clave, CajaProyecto.lote).where(CajaProyecto.proyecto_id == proyecto.id)).all())
    unidades: dict[str, int] = {}
    for caja in ctx.db.scalars(select(UnidadDocumental.caja).where(UnidadDocumental.proyecto_id == proyecto.id)):
        unidades[lote_por_caja.get(clave_de(caja or ""), "")] = unidades.get(lote_por_caja.get(clave_de(caja or ""), ""), 0) + 1
    base = confs.get("")
    salida = [{"lote": "", "nombre": "Todo el proyecto (lo que no tenga lote o cuyo lote no se configure)", "hoja_control": base.hoja_control if base else True,
               "isadg": base.isadg if base else False, "configurado": base is not None, "cajas": cajas.get("", 0), "unidades": unidades.get("", 0),
               "motivo": base.motivo if base else ""}]
    for nombre in sorted({k for k in cajas if k} | {k for k in confs if k}):
        c = confs.get(nombre)
        salida.append({"lote": nombre, "nombre": f"Lote {nombre}", "hoja_control": c.hoja_control if c else salida[0]["hoja_control"],
                       "isadg": c.isadg if c else salida[0]["isadg"], "configurado": c is not None, "cajas": cajas.get(nombre, 0), "unidades": unidades.get(nombre, 0),
                       "motivo": c.motivo if c else ""})
    return salida


def configurar(ctx, proyecto: Proyecto, lote: str, hoja_control: bool, isadg: bool, motivo: str) -> ConfiguracionLote:
    _abierto(proyecto)
    if not hoja_control and not isadg:
        raise DatosInvalidos("El lote debe llevar al menos uno de los dos procesos: hoja de control o descripción ISAD(G)")
    c = configuraciones(ctx, proyecto).get(lote.strip())
    antes = f"hoja {'sí' if c.hoja_control else 'no'}, ISAD(G) {'sí' if c.isadg else 'no'}" if c else "sin configurar"
    if c is None:
        c = ConfiguracionLote(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, lote=lote.strip()[:80])
        ctx.db.add(c)
    c.hoja_control, c.isadg, c.motivo, c.actualizado_en, c.actualizado_por = hoja_control, isadg, motivo.strip(), ahora_utc(), ctx.usuario.id
    ctx.db.flush()
    ctx.auditar(accion="CONFIGURAR_LOTE", objeto="ConfiguracionLote", objeto_id=c.id, motivo=motivo or None,
                detalle=f"{proyecto.codigo} · {('lote ' + c.lote) if c.lote else 'todo el proyecto'} · antes: {antes} · ahora: hoja {'sí' if hoja_control else 'no'}, ISAD(G) {'sí' if isadg else 'no'}")
    ctx.db.commit()
    return c
