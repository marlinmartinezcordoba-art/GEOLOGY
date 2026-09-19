"""
Producción del día y avance del contrato.

Responde tres preguntas que la dirección del proyecto tiene que poder contestar cualquier
día sin abrir un expediente: qué se hizo hoy, quién lo hizo y a qué ritmo vamos.

Todo sale de la bitácora, que registra cada movimiento con su responsable y su fecha. No se
lleva un contador aparte, porque un contador se desincroniza y la bitácora no: si un
expediente se devolvió y se volvió a trabajar, ahí están las dos cosas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import func

from app.services.estados import Estado

# Cada acción de la bitácora, con el nombre que el equipo usa para ella.
LABORES = {
    "levantar_hoja": "Hojas levantadas con el modelo",
    "verificar": "Hojas de control verificadas",
    "guardar_avance": "Hojas guardadas en avance",
    "revisar_hoja": "Hojas revisadas",
    "generar_isadg": "Descripciones generadas",
    "validar_isadg": "Descripciones validadas",
    "aprobar": "Descripciones aprobadas",
    "reubicar": "Carpetas reubicadas en caja definitiva",
    "retirar": "Expedientes retirados",
}

# Las que cuentan como producción para el ritmo del contrato. Guardar un avance no es
# producir: es dejar el trabajo a medias para seguir mañana.
PRODUCTIVAS = ("verificar", "generar_isadg", "validar_isadg", "aprobar", "reubicar")

DIAS_DE_HISTORIA = 30


@dataclass
class Produccion:
    fecha: date
    universo: int = 0
    embudo: dict = field(default_factory=dict)
    hoy: dict = field(default_factory=dict)
    hoy_por_persona: list = field(default_factory=list)
    por_dia: list = field(default_factory=list)
    acumulado_por_persona: list = field(default_factory=list)
    ritmo: dict = field(default_factory=dict)

    def como_dict(self) -> dict:
        return {"fecha": self.fecha.isoformat(), "universo": self.universo,
                "embudo": self.embudo, "hoy": self.hoy,
                "hoy_por_persona": self.hoy_por_persona, "por_dia": self.por_dia,
                "acumulado_por_persona": self.acumulado_por_persona, "ritmo": self.ritmo}


def _embudo(db) -> tuple[int, dict]:
    """Cuántas carpetas hay en cada etapa del proceso, de la más cruda a la terminada."""
    from app.models import Expediente, UnidadInventario

    universo = db.query(func.count(UnidadInventario.id)).scalar() or 0
    conteo = dict(db.query(Expediente.estado, func.count(Expediente.id))
                    .group_by(Expediente.estado).all())

    def suma(*estados) -> int:
        return sum(conteo.get(e.value, 0) for e in estados)

    con_hoja = suma(Estado.HOJA_POR_REVISAR, Estado.HOJA_REVISADA,
                    Estado.DESCRIPCION_POR_VALIDAR, Estado.DESCRIPCION_VALIDADA,
                    Estado.ARCHIVADO, Estado.EN_INVENTARIO)
    descritas = suma(Estado.DESCRIPCION_POR_VALIDAR, Estado.DESCRIPCION_VALIDADA,
                     Estado.ARCHIVADO, Estado.EN_INVENTARIO)
    validadas = suma(Estado.DESCRIPCION_VALIDADA, Estado.ARCHIVADO, Estado.EN_INVENTARIO)

    from app.models import Expediente as E
    en_caja = (db.query(func.count(E.id))
                 .filter(E.caja_definitiva.isnot(None), E.caja_definitiva != "").scalar() or 0)
    folios = (db.query(func.coalesce(func.sum(E.volumen_folios), 0))
                .filter(E.estado != Estado.RETIRADO.value).scalar() or 0)

    # Metros lineales intervenidos. Es la unidad en la que se mide y se factura el contrato,
    # así que la dirección tiene que poder verla sin sacar una calculadora. Se deriva de los
    # folios con la equivalencia del proyecto, cien folios por centímetro, de modo que está
    # disponible desde que la hoja de control existe y no espera a la descripción.
    def metros(*estados) -> float:
        consulta = db.query(func.coalesce(func.sum(E.volumen_folios), 0))
        consulta = (consulta.filter(E.estado.in_([e.value for e in estados])) if estados
                    else consulta.filter(E.estado != Estado.RETIRADO.value))
        return round((consulta.scalar() or 0) / 10000.0, 4)

    metros_en_caja = round(
        (db.query(func.coalesce(func.sum(E.volumen_folios), 0))
           .filter(E.caja_definitiva.isnot(None), E.caja_definitiva != "").scalar() or 0)
        / 10000.0, 4)

    cargadas = sum(c for e, c in conteo.items() if e != Estado.RETIRADO.value)
    return universo, {
        "inventariadas": universo,
        "cargadas": cargadas,
        "en_cola": suma(Estado.EN_COLA, Estado.EN_PROCESAMIENTO),
        "hoja_en_elaboracion": suma(Estado.HOJA_EN_ELABORACION),
        "con_hoja_de_control": con_hoja,
        "descritas": descritas,
        "validadas": validadas,
        "archivadas": suma(Estado.ARCHIVADO, Estado.EN_INVENTARIO),
        "en_caja_definitiva": en_caja,
        "devueltas": suma(Estado.DEVUELTO),
        "retiradas": conteo.get(Estado.RETIRADO.value, 0),
        "folios_registrados": int(folios),
        "metros_lineales_cargados": metros(),
        "metros_lineales_con_hoja": metros(
            Estado.HOJA_POR_REVISAR, Estado.HOJA_REVISADA, Estado.DESCRIPCION_POR_VALIDAR,
            Estado.DESCRIPCION_VALIDADA, Estado.ARCHIVADO, Estado.EN_INVENTARIO),
        "metros_lineales_descritos": metros(
            Estado.DESCRIPCION_POR_VALIDAR, Estado.DESCRIPCION_VALIDADA,
            Estado.ARCHIVADO, Estado.EN_INVENTARIO),
        "metros_lineales_aprobados": metros(Estado.ARCHIVADO, Estado.EN_INVENTARIO),
        "metros_lineales_en_caja": metros_en_caja,
    }


def _del_dia(db, dia: date) -> tuple[dict, list]:
    """Qué se hizo en un día, en total y por persona."""
    from app.models import Trazabilidad

    desde = datetime.combine(dia, datetime.min.time())
    hasta = desde + timedelta(days=1)
    filas = (db.query(Trazabilidad.accion, Trazabilidad.usuario,
                      func.count(func.distinct(Trazabilidad.expediente_id)))
               .filter(Trazabilidad.fecha >= desde, Trazabilidad.fecha < hasta)
               .group_by(Trazabilidad.accion, Trazabilidad.usuario).all())

    total: dict[str, int] = {}
    por_persona: dict[str, dict] = {}
    for accion, usuario, cuantas in filas:
        if accion not in LABORES:
            continue
        total[accion] = total.get(accion, 0) + cuantas
        nombre = usuario or "sin registrar"
        ficha = por_persona.setdefault(nombre, {"persona": nombre, "total": 0, "labores": {}})
        ficha["labores"][LABORES[accion]] = ficha["labores"].get(LABORES[accion], 0) + cuantas
        if accion in PRODUCTIVAS:
            ficha["total"] += cuantas

    resumen = {LABORES[a]: c for a, c in sorted(total.items(), key=lambda x: -x[1])}
    resumen["Total productivo del día"] = sum(c for a, c in total.items() if a in PRODUCTIVAS)
    gente = sorted(por_persona.values(), key=lambda f: -f["total"])
    return resumen, gente


def _por_dia(db, dias: int = DIAS_DE_HISTORIA) -> list:
    """Los últimos días con actividad, para ver el ritmo y no una foto suelta."""
    from app.models import Trazabilidad

    desde = datetime.combine(date.today() - timedelta(days=dias), datetime.min.time())
    filas = (db.query(func.date(Trazabilidad.fecha), Trazabilidad.accion,
                      func.count(func.distinct(Trazabilidad.expediente_id)))
               .filter(Trazabilidad.fecha >= desde)
               .group_by(func.date(Trazabilidad.fecha), Trazabilidad.accion).all())

    dias_map: dict[str, dict] = {}
    for d, accion, cuantas in filas:
        if accion not in LABORES:
            continue
        clave = d.isoformat() if hasattr(d, "isoformat") else str(d)
        fila = dias_map.setdefault(clave, {"dia": clave, "hojas": 0, "descritas": 0,
                                           "validadas": 0, "reubicadas": 0, "total": 0})
        if accion == "verificar":
            fila["hojas"] += cuantas
        elif accion == "generar_isadg":
            fila["descritas"] += cuantas
        elif accion == "validar_isadg":
            fila["validadas"] += cuantas
        elif accion == "reubicar":
            fila["reubicadas"] += cuantas
        if accion in PRODUCTIVAS:
            fila["total"] += cuantas
    return sorted(dias_map.values(), key=lambda f: f["dia"], reverse=True)


def _acumulado_por_persona(db) -> list:
    from app.models import Trazabilidad
    filas = (db.query(Trazabilidad.usuario, Trazabilidad.accion,
                      func.count(func.distinct(Trazabilidad.expediente_id)))
               .filter(Trazabilidad.usuario.isnot(None))
               .group_by(Trazabilidad.usuario, Trazabilidad.accion).all())
    gente: dict[str, dict] = {}
    for usuario, accion, cuantas in filas:
        if accion not in LABORES:
            continue
        f = gente.setdefault(usuario, {"persona": usuario, "hojas": 0, "descritas": 0,
                                       "validadas": 0, "total": 0})
        if accion == "verificar":
            f["hojas"] += cuantas
        elif accion == "generar_isadg":
            f["descritas"] += cuantas
        elif accion == "validar_isadg":
            f["validadas"] += cuantas
        if accion in PRODUCTIVAS:
            f["total"] += cuantas
    return sorted(gente.values(), key=lambda f: -f["total"])


def _ritmo(universo: int, embudo: dict, por_dia: list) -> dict:
    """
    Promedio por día trabajado y proyección.

    Se promedia sobre los días en que hubo actividad, no sobre los días del calendario: un
    fin de semana sin producción no debe bajar el promedio del equipo ni estirar la
    proyección de forma engañosa.
    """
    con_actividad = [d for d in por_dia if d["descritas"]]
    if not con_actividad:
        return {"dias_trabajados": 0, "promedio_descritas_por_dia": 0,
                "faltan": max(0, universo - embudo.get("descritas", 0)),
                "dias_estimados": None, "fecha_estimada": None,
                "nota": "La proyección aparece cuando haya al menos un día con descripciones."}

    promedio = sum(d["descritas"] for d in con_actividad) / len(con_actividad)
    faltan = max(0, universo - embudo.get("descritas", 0))
    dias = int(faltan / promedio) + 1 if promedio else None
    estimada = (date.today() + timedelta(days=dias)).isoformat() if dias else None
    return {"dias_trabajados": len(con_actividad),
            "promedio_descritas_por_dia": round(promedio, 1),
            "faltan": faltan, "dias_estimados": dias, "fecha_estimada": estimada,
            "nota": (f"A {round(promedio, 1)} descripciones por día trabajado faltan {dias} "
                     f"días de producción para las {faltan} carpetas que quedan.")}


def ahora(db, minutos: int = 30) -> dict:
    """
    Qué se está moviendo en este momento y quién lo está moviendo.

    Sirve para el tablero en vivo: cuántos expedientes tiene el modelo entre manos, cuántas
    hojas están esperando revisión humana, y quién del equipo ha registrado movimientos en la
    última media hora. Sale de la bitácora, así que refleja trabajo real y no presencia.
    """
    from datetime import datetime as _dt

    from app.models import Expediente, Trazabilidad

    conteo = dict(db.query(Expediente.estado, func.count(Expediente.id))
                    .group_by(Expediente.estado).all())

    en_vuelo = {
        "leyendo_el_modelo": conteo.get(Estado.EN_PROCESAMIENTO.value, 0),
        "esperando_lectura": conteo.get(Estado.EN_COLA.value, 0),
        "hojas_por_revisar": (conteo.get(Estado.HOJA_EN_ELABORACION.value, 0)
                              + conteo.get(Estado.HOJA_POR_REVISAR.value, 0)),
        "listas_para_describir": conteo.get(Estado.HOJA_REVISADA.value, 0),
        "descripciones_por_validar": conteo.get(Estado.DESCRIPCION_POR_VALIDAR.value, 0),
        "validadas_por_aprobar": conteo.get(Estado.DESCRIPCION_VALIDADA.value, 0),
        "devueltas": conteo.get(Estado.DEVUELTO.value, 0),
    }

    desde = _dt.now() - timedelta(minutes=minutos)
    filas = (db.query(Trazabilidad.usuario, Trazabilidad.accion,
                      func.count(func.distinct(Trazabilidad.expediente_id)),
                      func.max(Trazabilidad.fecha))
               .filter(Trazabilidad.fecha >= desde, Trazabilidad.usuario.isnot(None))
               .group_by(Trazabilidad.usuario, Trazabilidad.accion).all())

    gente: dict[str, dict] = {}
    for usuario, accion, cuantas, ultima in filas:
        if accion not in LABORES:
            continue
        f = gente.setdefault(usuario, {"persona": usuario, "total": 0, "labores": {},
                                       "ultimo": None})
        f["labores"][LABORES[accion]] = f["labores"].get(LABORES[accion], 0) + cuantas
        f["total"] += cuantas
        if ultima and (f["ultimo"] is None or ultima.isoformat() > f["ultimo"]):
            f["ultimo"] = ultima.isoformat(timespec="minutes")

    return {"minutos": minutos, "en_vuelo": en_vuelo,
            "trabajando": sorted(gente.values(), key=lambda x: -x["total"])}


def produccion(db, dia: date | None = None) -> Produccion:
    """El tablero completo de producción. Es lo que alimenta la pestaña de Avance."""
    hoy = dia or date.today()
    universo, embudo = _embudo(db)
    resumen_hoy, gente_hoy = _del_dia(db, hoy)
    por_dia = _por_dia(db)
    return Produccion(fecha=hoy, universo=universo, embudo=embudo, hoy=resumen_hoy,
                      hoy_por_persona=gente_hoy, por_dia=por_dia,
                      acumulado_por_persona=_acumulado_por_persona(db),
                      ritmo=_ritmo(universo, embudo, por_dia))
