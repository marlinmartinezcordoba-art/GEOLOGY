"""M04 · Clasificación de las unidades documentales con la TRD o la TVD vigente del proyecto.

Reglas:
- Se clasifica en el nivel más bajo: la subserie, o la serie cuando no tiene subseries. La lista es cerrada:
  solo existe lo que dice la versión vigente del instrumento.
- Qué instrumento aplica: si el proyecto tiene una TVD cuyo periodo contiene las fechas extremas de la unidad,
  esa TVD (fondo acumulado); si no, la TRD. Una persona puede elegir otro al clasificar a mano.
- El código que trae el FUID, si está tal cual en la versión vigente, clasifica solo (no es IA: es el dato que
  entregó la entidad). Lo que se deduce del nombre del expediente queda como **propuesta** con su porqué y su
  confianza, y lo confirma una persona. Si nada coincide no se propone nada: no se elige «la primera de la tabla».
- Lo clasificado conserva la versión con que se hizo. Pasarlo a una versión nueva es una acción explícita, con
  motivo, y solo donde el mismo código sigue existiendo.
- Con las fechas y la retención se calcula el calendario: cuándo termina el archivo de gestión, cuándo el
  central y qué disposición aplica.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select

from arca.modelos import ClasificacionUnidad, ElementoInstrumento, EstadoProyecto, Instrumento, Proyecto, UnidadDocumental, VersionInstrumento
from arca.modelos.base import ahora_utc
from arca.modulos.m04_instrumentos import servicios as instrumentos
from arca.motor.clasificacion import CONFIANZA_ALTA, CONFIANZA_BAJA, CONFIANZA_MEDIA, OpcionTvd, _raices, puntuar_opcion
from arca.motor.codigos import normalizar_texto
from arca.nucleo.errores import DatosInvalidos, NoEncontrado, TransicionInvalida

ACTIVAS = ("propuesta", "confirmada")
DISPOSICION = {"CT": "conservación total", "E": "eliminación", "S": "selección", "D": "digitalización"}


@dataclass
class Vigente:
    instrumento: Instrumento
    version: VersionInstrumento
    elementos: dict[uuid.UUID, ElementoInstrumento]
    clasificables: list[ElementoInstrumento]
    por_codigo: dict[str, list[ElementoInstrumento]]
    padres: dict[str, ElementoInstrumento]


def _abierto(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


def vigentes(ctx, proyecto: Proyecto) -> list[Vigente]:
    """TRD y TVD con versión vigente, con sus series y subseries listas para buscar."""
    salida = []
    for i in instrumentos.listar(ctx, proyecto):
        if i.tipo not in ("TRD", "TVD"):
            continue
        v = next((x for x in instrumentos.versiones(ctx, i) if x.estado == "vigente"), None)
        if v is None:
            continue
        todos = [e for e in instrumentos.elementos(ctx, v) if e.nivel != "dependencia"]
        con_hijas = {e.padre for e in todos if e.nivel == "subserie"}
        clasificables = [e for e in todos if e.nivel == "subserie" or e.codigo not in con_hijas]
        por_codigo: dict[str, list[ElementoInstrumento]] = {}
        for e in todos:
            por_codigo.setdefault(normalizar_texto(e.codigo), []).append(e)
        salida.append(Vigente(i, v, {e.id: e for e in todos}, clasificables, por_codigo, {e.codigo: e for e in todos if e.nivel == "serie"}))
    return salida


def _aplica(lista: list[Vigente], u: UnidadDocumental) -> Vigente | None:
    """La TVD cuyo periodo contiene las fechas de la unidad; si no hay, la TRD; si solo hay una, esa."""
    for vg in lista:
        i = vg.instrumento
        if i.tipo == "TVD" and (i.periodo_desde or i.periodo_hasta) and (u.fecha_inicial or u.fecha_final):
            desde, hasta = u.fecha_inicial or u.fecha_final, u.fecha_final or u.fecha_inicial
            if (not i.periodo_desde or desde >= i.periodo_desde) and (not i.periodo_hasta or hasta <= i.periodo_hasta):
                return vg
    trd = [vg for vg in lista if vg.instrumento.tipo == "TRD"]
    if trd:
        return trd[0]
    return lista[0] if len(lista) == 1 else None


def _opcion(vg: Vigente, e: ElementoInstrumento) -> OpcionTvd:
    padre = vg.padres.get(e.padre or "")
    if e.nivel == "subserie":
        return OpcionTvd(periodo=str(vg.version.version), cod_serie=e.padre or "", serie=padre.nombre if padre else "", cod_subserie=e.codigo, subserie=e.nombre,
                         codigo_dependencia=e.codigo_dependencia)
    return OpcionTvd(periodo=str(vg.version.version), cod_serie=e.codigo, serie=e.nombre, cod_subserie="", subserie=e.nombre, codigo_dependencia=e.codigo_dependencia)


def _por_nombre(vg: Vigente, candidatos: list[ElementoInstrumento], u: UnidadDocumental) -> tuple[ElementoInstrumento, str] | None:
    """La serie o subserie cuyo nombre más se parece al del expediente (puntaje del motor de GEOLOGY). Empate = no se decide."""
    raices = _raices(f"{u.nombre} {u.notas or ''}")
    puntos = sorted(((puntuar_opcion(_opcion(vg, e), raices), e) for e in candidatos), key=lambda x: -x[0])
    if not puntos or puntos[0][0] == 0 or (len(puntos) > 1 and puntos[1][0] == puntos[0][0]):
        return None
    return puntos[0][1], CONFIANZA_ALTA if puntos[0][0] >= 4 else (CONFIANZA_MEDIA if puntos[0][0] >= 2 else CONFIANZA_BAJA)


def _literal(codigo: str | None) -> str:
    return "".join((codigo or "").split()).upper()


def _bajar(confianza: str) -> str:
    return {CONFIANZA_ALTA: CONFIANZA_MEDIA, CONFIANZA_MEDIA: CONFIANZA_BAJA}.get(confianza, CONFIANZA_BAJA)


def proponer_una(vg: Vigente, u: UnidadDocumental) -> tuple[ElementoInstrumento, str, str, str] | None:
    """(elemento, origen, confianza, porque) o None. Primero el código del FUID; después el nombre del expediente.

    Solo clasifica sola («inventario») la unidad cuyo código está escrito igual que en la tabla. Si coincide
    escrito de otra forma («100.02» frente a «100-02»), o solo coincide la serie, queda como propuesta («codigo»).
    Si además el nombre del expediente no se parece en nada al de la subserie, baja la confianza y se dice.
    """
    if u.codigo_serie:
        candidatos = vg.por_codigo.get(normalizar_texto(u.codigo_serie), [])
        literales = [e for e in candidatos if _literal(e.codigo) == _literal(u.codigo_serie)]
        usados, igual = (literales, True) if literales else (candidatos, False)
        otra_forma = "" if igual else f" (en la tabla se escribe «{usados[0].codigo}»)" if usados else ""
        raices = _raices(f"{u.nombre} {u.notas or ''}")

        def ajustar(e: ElementoInstrumento, confianza: str, porque: str) -> tuple[str, str]:
            if raices and puntuar_opcion(_opcion(vg, e), raices) == 0:
                return _bajar(confianza), f"{porque}; el nombre del expediente no se parece al de «{e.nombre}»: revísela"
            return confianza, porque

        directos = [e for e in usados if e in vg.clasificables]
        if len(directos) == 1:
            e = directos[0]
            if igual:
                return e, "inventario", CONFIANZA_ALTA, f"el FUID trae el código «{u.codigo_serie}», que está en la {vg.instrumento.tipo} v{vg.version.version}"
            confianza, porque = ajustar(e, CONFIANZA_MEDIA, f"el código «{u.codigo_serie}» del FUID coincide escrito de otra forma{otra_forma}")
            return e, "codigo", confianza, porque
        serie = [e for e in usados if e.nivel == "serie"]
        if len(serie) == 1:
            hijas = [e for e in vg.clasificables if e.padre == serie[0].codigo]
            if len(hijas) == 1:
                base = f"el FUID trae la serie «{u.codigo_serie}»{otra_forma} y esa serie tiene una sola subserie"
                confianza, porque = ajustar(hijas[0], CONFIANZA_ALTA if igual else CONFIANZA_MEDIA, base)
                return hijas[0], "codigo", confianza, porque
            if elegida := _por_nombre(vg, hijas, u):
                return elegida[0], "codigo", elegida[1], f"el FUID trae la serie «{u.codigo_serie}»{otra_forma}; la subserie se deduce del nombre del expediente"
    elegida = _por_nombre(vg, vg.clasificables, u)
    if elegida and elegida[1] != CONFIANZA_BAJA:
        return elegida[0], "motor", elegida[1], "se deduce del nombre del expediente; confírmela o cámbiela"
    return None


def _activas(ctx, proyecto: Proyecto) -> dict[uuid.UUID, ClasificacionUnidad]:
    filas = ctx.db.scalars(select(ClasificacionUnidad).where(ClasificacionUnidad.proyecto_id == proyecto.id, ClasificacionUnidad.estado.in_(ACTIVAS)))
    return {c.unidad_id: c for c in filas}


def _nueva(ctx, proyecto, u, vg_version_id, elemento_id, estado, origen, confianza, porque, motivo="", reemplaza: ClasificacionUnidad | None = None) -> ClasificacionUnidad:
    ahora = ahora_utc()
    if reemplaza is not None:
        reemplaza.estado = "reemplazada"
    c = ClasificacionUnidad(tenant_id=ctx.tenant_id, proyecto_id=proyecto.id, unidad_id=u.id, version_id=vg_version_id, elemento_id=elemento_id, estado=estado,
                            origen=origen, confianza=confianza, porque=porque, motivo=motivo, reemplaza_id=reemplaza.id if reemplaza else None, creado_en=ahora,
                            creado_por=ctx.usuario.id, decidido_en=ahora if estado == "confirmada" else None, decidido_por=ctx.usuario.id if estado == "confirmada" else None)
    ctx.db.add(c)
    return c


def proponer(ctx, proyecto: Proyecto) -> dict[str, int]:
    """Clasifica lo pendiente: con el código del FUID queda confirmada; con el nombre, propuesta."""
    _abierto(proyecto)
    lista = vigentes(ctx, proyecto)
    if not lista:
        raise TransicionInvalida("El proyecto no tiene TRD ni TVD vigente: apruebe una antes de clasificar")
    activas = _activas(ctx, proyecto)
    cuenta = {"confirmadas": 0, "propuestas": 0, "sin_propuesta": 0, "sin_instrumento": 0}
    for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id)):
        if u.id in activas:
            continue
        vg = _aplica(lista, u)
        if vg is None:
            cuenta["sin_instrumento"] += 1
            continue
        p = proponer_una(vg, u)
        if p is None:
            cuenta["sin_propuesta"] += 1
            continue
        elemento, origen, confianza, porque = p
        estado = "confirmada" if origen == "inventario" else "propuesta"
        _nueva(ctx, proyecto, u, vg.version.id, elemento.id, estado, origen, confianza, porque)
        cuenta["confirmadas" if estado == "confirmada" else "propuestas"] += 1
    ctx.auditar(accion="CLASIFICAR_AUTOMATICO", objeto="Proyecto", objeto_id=proyecto.id,
                detalle=f"{proyecto.codigo} · {cuenta['confirmadas']} por código del FUID, {cuenta['propuestas']} propuestas, {cuenta['sin_propuesta']} sin propuesta")
    ctx.db.commit()
    return cuenta


def _unidades(ctx, proyecto: Proyecto, ids: list[uuid.UUID]) -> list[UnidadDocumental]:
    if not ids:
        raise DatosInvalidos("No eligió ninguna unidad")
    unidades = list(ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id, UnidadDocumental.id.in_(ids))))
    if len(unidades) != len(set(ids)):
        raise NoEncontrado("Alguna de las unidades no existe en el proyecto")
    return unidades


def asignar(ctx, proyecto: Proyecto, unidad_ids: list[uuid.UUID], elemento_id: uuid.UUID, motivo: str) -> int:
    """Clasificación hecha por una persona. Si la unidad ya estaba clasificada, se reemplaza con motivo."""
    _abierto(proyecto)
    vg = next((x for x in vigentes(ctx, proyecto) if elemento_id in x.elementos), None)
    if vg is None:
        raise DatosInvalidos("La serie o subserie no pertenece a una TRD o TVD vigente del proyecto")
    e = vg.elementos[elemento_id]
    if e not in vg.clasificables:
        raise DatosInvalidos(f"La serie {e.codigo} tiene subseries: clasifique en la subserie")
    activas = _activas(ctx, proyecto)
    unidades = _unidades(ctx, proyecto, unidad_ids)
    if any(u.id in activas and activas[u.id].estado == "confirmada" for u in unidades) and len(motivo.strip()) < 5:
        raise DatosInvalidos("Para reclasificar lo ya confirmado escriba el motivo")
    for u in unidades:
        anterior = activas.get(u.id)
        if anterior and anterior.elemento_id == e.id and anterior.estado == "confirmada":
            continue
        _nueva(ctx, proyecto, u, vg.version.id, e.id, "confirmada", "manual", None, "asignada por una persona", motivo.strip(), anterior)
    ctx.auditar(accion="CLASIFICAR", objeto="ElementoInstrumento", objeto_id=e.id, motivo=motivo or None,
                detalle=f"{proyecto.codigo} · {len(unidades)} unidades → {e.codigo} {e.nombre} ({vg.instrumento.tipo} v{vg.version.version})")
    ctx.db.commit()
    return len(unidades)


def decidir(ctx, proyecto: Proyecto, ids: list[uuid.UUID], confirmar: bool, motivo: str) -> int:
    """Confirma o rechaza propuestas. Rechazar deja la unidad pendiente y exige motivo."""
    _abierto(proyecto)
    if not confirmar and len(motivo.strip()) < 5:
        raise DatosInvalidos("Para rechazar escriba el motivo")
    filas = list(ctx.db.scalars(select(ClasificacionUnidad).where(ClasificacionUnidad.proyecto_id == proyecto.id, ClasificacionUnidad.id.in_(ids))))
    if not ids or len(filas) != len(set(ids)):
        raise NoEncontrado("Alguna de las propuestas no existe")
    if any(c.estado != "propuesta" for c in filas):
        raise TransicionInvalida("Solo se confirman o rechazan propuestas")
    vigentes_ids = {vg.version.id for vg in vigentes(ctx, proyecto)}
    if confirmar and any(c.version_id not in vigentes_ids for c in filas):
        raise TransicionInvalida("La propuesta se hizo con una versión que ya no está vigente: vuelva a clasificar")
    ahora = ahora_utc()
    for c in filas:
        c.estado = "confirmada" if confirmar else "rechazada"
        c.decidido_en, c.decidido_por, c.motivo = ahora, ctx.usuario.id, motivo.strip()
    ctx.auditar(accion="CONFIRMAR_CLASIFICACION" if confirmar else "RECHAZAR_CLASIFICACION", objeto="Proyecto", objeto_id=proyecto.id, motivo=motivo or None,
                detalle=f"{proyecto.codigo} · {len(filas)} propuestas")
    ctx.db.commit()
    return len(filas)


def actualizar_version(ctx, proyecto: Proyecto, motivo: str) -> dict[str, int]:
    """Pasa lo clasificado con versiones anteriores a la vigente del mismo instrumento, donde el código sigue existiendo."""
    _abierto(proyecto)
    lista = {vg.instrumento.id: vg for vg in vigentes(ctx, proyecto)}
    unidades = {u.id: u for u in ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id))}
    cuenta = {"actualizadas": 0, "sin_equivalente": 0}
    for c in _activas(ctx, proyecto).values():
        v = ctx.db.get(VersionInstrumento, c.version_id)
        vg = lista.get(v.instrumento_id)
        if vg is None or vg.version.id == v.id:
            continue
        anterior = ctx.db.get(ElementoInstrumento, c.elemento_id)
        nuevos = [e for e in vg.clasificables if e.codigo == anterior.codigo]
        if len(nuevos) != 1:
            cuenta["sin_equivalente"] += 1
            continue
        _nueva(ctx, proyecto, unidades[c.unidad_id], vg.version.id, nuevos[0].id, c.estado, "actualizacion", c.confianza,
               f"misma {nuevos[0].nivel} {anterior.codigo} en la v{vg.version.version}", motivo, c)
        cuenta["actualizadas"] += 1
    ctx.auditar(accion="ACTUALIZAR_CLASIFICACION", objeto="Proyecto", objeto_id=proyecto.id, motivo=motivo,
                detalle=f"{proyecto.codigo} · {cuenta['actualizadas']} a la versión vigente, {cuenta['sin_equivalente']} sin equivalente")
    ctx.db.commit()
    return cuenta


def _mas_anios(d: date, anios: int) -> date:
    try:
        return d.replace(year=d.year + anios)
    except ValueError:  # 29 de febrero
        return d.replace(year=d.year + anios, day=28)


SIN_RETIRO = object()  # historia laboral de una persona aún vinculada: la retención todavía no empieza a contar


def calendario(u: UnidadDocumental, e: ElementoInstrumento, hoy: date | None = None, desde: date | object | None = None) -> dict[str, Any]:
    """Cuándo termina cada fase según la retención, contada desde la fecha final de la unidad.

    `desde` cambia la fecha desde la que se cuenta: en una historia laboral, la fecha de retiro del titular (Acuerdo AGN
    001 de 2024, artículo 9.5.5: la retención en gestión se cuenta desde la desvinculación). `SIN_RETIRO` = la persona
    sigue vinculada y la historia está abierta.
    """
    hoy = hoy or date.today()
    disposicion = DISPOSICION.get(e.disposicion or "", e.disposicion)
    if desde is SIN_RETIRO:
        return {"fin_gestion": None, "fin_central": None, "fase": "gestion", "disposicion": disposicion, "base": "retiro",
                "nota": "Historia laboral abierta: la persona sigue vinculada (sin fecha de retiro), la retención aún no cuenta"}
    base = desde if isinstance(desde, date) else u.fecha_final
    if not base or e.retencion_gestion is None:
        return {"fin_gestion": None, "fin_central": None, "fase": None, "disposicion": disposicion,
                "nota": "Sin fecha final o sin tiempo de retención: no se puede calcular el calendario"}
    fin_g = _mas_anios(base, e.retencion_gestion)
    fin_c = _mas_anios(fin_g, e.retencion_central or 0)
    fase = "gestion" if hoy < fin_g else ("central" if hoy < fin_c else "cumplida")
    nota = {"gestion": f"En archivo de gestión hasta {fin_g.isoformat()}", "central": f"En archivo central hasta {fin_c.isoformat()}",
            "cumplida": f"Cumplió la retención: aplicar {disposicion}"}[fase]
    if isinstance(desde, date):
        nota += f" (contado desde el retiro, {desde.isoformat()})"
    return {"fin_gestion": fin_g, "fin_central": fin_c, "fase": fase, "disposicion": disposicion, "nota": nota, "base": "retiro" if isinstance(desde, date) else "fecha_final"}


def estado(ctx, proyecto: Proyecto) -> list[dict[str, Any]]:
    """Una fila por unidad con su clasificación activa, la versión usada, el calendario y las alertas."""
    vigentes_ids = {vg.version.id for vg in vigentes(ctx, proyecto)}
    activas = _activas(ctx, proyecto)
    versiones = {v.id: v for v in ctx.db.scalars(select(VersionInstrumento).where(VersionInstrumento.id.in_({c.version_id for c in activas.values()})))} if activas else {}
    insts = {i.id: i for i in instrumentos.listar(ctx, proyecto)}
    elementos = {e.id: e for e in ctx.db.scalars(select(ElementoInstrumento).where(ElementoInstrumento.id.in_({c.elemento_id for c in activas.values()})))} if activas else {}
    from arca.modulos.historias.servicios import bases_de_retencion  # noqa: PLC0415

    bases = bases_de_retencion(ctx, proyecto)
    filas = []
    for u in sorted(ctx.db.scalars(select(UnidadDocumental).where(UnidadDocumental.proyecto_id == proyecto.id)), key=lambda x: (x.numero_orden or "", x.identificador)):
        c = activas.get(u.id)
        fila: dict[str, Any] = {"unidad": u, "clasificacion": None, "situacion": "pendiente", "alertas": []}
        if c:
            e, v = elementos[c.elemento_id], versiones[c.version_id]
            i = insts[v.instrumento_id]
            fila["clasificacion"] = {"id": c.id, "estado": c.estado, "origen": c.origen, "confianza": c.confianza, "porque": c.porque, "elemento_id": e.id,
                                     "codigo": e.codigo, "nombre": e.nombre, "nivel": e.nivel, "serie": e.padre, "dependencia": e.codigo_dependencia,
                                     "instrumento": f"{i.tipo} · {i.nombre}", "version": v.version, "version_vigente": v.id in vigentes_ids,
                                     "calendario": calendario(u, e, desde=bases.get(u.id)), "creado_en": c.creado_en, "decidido_en": c.decidido_en}
            fila["situacion"] = c.estado if v.id in vigentes_ids else "version_anterior"
            if u.codigo_serie and normalizar_texto(u.codigo_serie) not in (normalizar_texto(e.codigo), normalizar_texto(e.padre or "")):
                fila["alertas"].append(f"el FUID dice «{u.codigo_serie}» y la unidad quedó en {e.codigo}")
            if v.id not in vigentes_ids:
                fila["alertas"].append(f"clasificada con la v{v.version}, que ya no está vigente")
        filas.append(fila)
    return filas


def opciones(ctx, proyecto: Proyecto) -> list[dict[str, Any]]:
    return [{"instrumento_id": vg.instrumento.id, "instrumento": f"{vg.instrumento.tipo} · {vg.instrumento.nombre}", "version": vg.version.version,
             "elementos": [{"id": e.id, "codigo": e.codigo, "nombre": e.nombre, "nivel": e.nivel, "serie": e.padre, "dependencia": e.codigo_dependencia,
                            "serie_nombre": vg.padres[e.padre].nombre if e.padre in vg.padres else None, "disposicion": e.disposicion} for e in vg.clasificables]}
            for vg in vigentes(ctx, proyecto)]
