"""
Qué carpetas NO hay que digitalizar, según la disposición final de la tabla convalidada.

EL PUNTO. La tabla de valoración no dice lo mismo de todas las subseries. Unas van a
conservación total, y de esas las marcadas con medio técnico son las que se digitalizan.
Otras van a ELIMINACIÓN, y esas no se digitalizan ni se describen: se inventarían aparte y
se sustentan ante el Comité. Y otras van a SELECCIÓN, donde solo se conserva y se describe
la muestra, y el resto se elimina.

Digitalizar una carpeta de eliminación es trabajo que nadie pidió, que nadie paga y que
además contamina el acervo digital con documentos que no deberían estar ahí.

POR QUÉ NO BASTA CON MIRAR EL INVENTARIO. La columna de subserie del inventario de origen no
es de fiar en este fondo: hay más de mil carpetas rotuladas «ACTA COMITE DE PUBLICACION»
cuyo asunto dice, con todas sus letras, «INFORMES DE ANALISIS DE LABORATORIO QUIMICO DE
MUESTRAS». Quien decidiera qué eliminar leyendo esa columna se equivocaría más de mil veces.
El asunto, en cambio, sí describe lo que hay dentro, y es sobre el asunto que se compara.

LO QUE ESTE MÓDULO HACE Y LO QUE NO HACE. Propone. Señala qué carpetas SE PARECEN a una
subserie de eliminación o de selección, con su puntaje y con qué palabras coincidieron, para
que una persona las verifique con la carpeta en la mano. No decide, no marca, no excluye
nada del flujo por su cuenta.

Y eso no es prudencia de más. Eliminar un documento de archivo es IRREVERSIBLE, la
eliminación tiene que ir avalada por el Comité, y responder por una eliminación indebida no
lo hace un programa: lo hace la archivista que firma. Por eso aquí nunca hay una decisión
automática, solo una lista ordenada de candidatas y el porqué de cada una.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Los cuatro valores de disposición final que trae la tabla convalidada de este fondo.
CONSERVACION_TOTAL = "CT"
CON_MEDIO_TECNICO = "CT+M"
ELIMINACION = "E"
SELECCION = "S"

QUE_SIGNIFICA = {
    CON_MEDIO_TECNICO: "Conservación total con medio técnico. Se conserva, se describe y SÍ "
                       "se digitaliza.",
    CONSERVACION_TOTAL: "Conservación total. Se conserva y se describe; la digitalización va "
                        "según lo pactado con la supervisión.",
    SELECCION: "Selección. Solo se conserva y se describe la muestra; el resto se elimina. "
               "NO se digitaliza completa.",
    ELIMINACION: "Eliminación. NO se digitaliza ni se describe con ISAD(G). Va al inventario "
                 "de propuesta de eliminación y se sustenta ante el Comité.",
}

NO_SE_DIGITALIZA = (ELIMINACION,)
SE_DIGITALIZA_PARCIAL = (SELECCION,)

# Desde qué puntaje se considera que vale la pena que una persona la mire. Por debajo hay
# demasiado ruido; por encima de siete la coincidencia suele ser inequívoca.
UMBRAL = 4
FUERTE = 7


@dataclass
class Candidata:
    """Una carpeta que se parece a una subserie de eliminación o de selección."""
    codigo_carpeta: str
    periodo: str
    asunto: str
    folios: int
    disposicion: str
    subserie_tvd: str
    serie_tvd: str
    oficina: str
    puntaje: int
    coincidencias: list = field(default_factory=list)

    @property
    def confianza(self) -> str:
        return "fuerte" if self.puntaje >= FUERTE else "probable"

    @property
    def que_hacer(self) -> str:
        if self.disposicion == ELIMINACION:
            return ("NO la digitalice. Verifíquela con la carpeta en la mano y, si confirma, "
                    "pásela al inventario de propuesta de eliminación para el Comité.")
        return ("NO la digitalice completa. Verifíquela y aplique el criterio de muestreo "
                "que se haya pactado para esa subserie.")


def _raices_de(texto: str) -> set[str]:
    from app.services.clasificacion import _raices
    return _raices(texto)


def opciones_a_evitar(db, romano: str) -> list:
    """Las subseries de eliminación y de selección del periodo, con su contexto."""
    from app.models import Periodo, Seccion, Serie, Subserie

    periodo = (db.query(Periodo).filter(Periodo.numero_romano == romano).first()
               if romano else None)
    if not periodo:
        return []
    salida = []
    for seccion in db.query(Seccion).filter(Seccion.periodo_id == periodo.id).all():
        for serie in db.query(Serie).filter(Serie.seccion_id == seccion.id).all():
            for sub in db.query(Subserie).filter(Subserie.serie_id == serie.id).all():
                if sub.disposicion_final in (ELIMINACION, SELECCION):
                    salida.append({"disposicion": sub.disposicion_final,
                                   "serie": serie.nombre, "subserie": sub.nombre,
                                   "oficina": seccion.oficina_productora})
    return salida


def revisar_unidad(unidad, opciones: list) -> Candidata | None:
    """
    Compara el asunto de una carpeta contra las subseries de eliminación y selección.

    Se comparan el asunto y, con menos peso, lo que el inventario declare como serie y
    subserie, porque esa declaración a veces acierta. El nombre de la subserie de la tabla
    pesa el doble que el de la serie, por la misma razón de siempre: la serie es una familia
    ancha y la subserie es la que distingue.
    """
    if not opciones:
        return None
    del_asunto = _raices_de(unidad.asunto or "")
    declarado = _raices_de(f"{unidad.serie or ''} {unidad.subserie or ''}")
    if not del_asunto and not declarado:
        return None

    mejor, puntaje_mejor, coincidio = None, 0, []
    for o in opciones:
        r_sub = _raices_de(o["subserie"])
        r_ser = _raices_de(o["serie"])
        en_sub = del_asunto & r_sub
        en_ser = del_asunto & r_ser
        # Lo declarado en el inventario cuenta, pero la mitad: no es de fiar en este fondo.
        eco_sub = declarado & r_sub
        eco_ser = declarado & r_ser
        puntaje = len(en_sub) * 3 + len(en_ser) * 2 + len(eco_sub) + len(eco_ser) // 2
        if puntaje > puntaje_mejor:
            mejor, puntaje_mejor = o, puntaje
            coincidio = sorted(en_sub | en_ser | eco_sub | eco_ser)

    if not mejor or puntaje_mejor < UMBRAL:
        return None
    return Candidata(
        codigo_carpeta=unidad.codigo_carpeta, periodo=unidad.periodo or "",
        asunto=(unidad.asunto or "")[:220], folios=unidad.folios or 0,
        disposicion=mejor["disposicion"], subserie_tvd=mejor["subserie"],
        serie_tvd=mejor["serie"], oficina=mejor["oficina"],
        puntaje=puntaje_mejor, coincidencias=coincidio)


def revisar_todo(db, solo_periodo: str = "") -> tuple[list, dict]:
    """
    Recorre el inventario de origen y devuelve las candidatas, con su resumen.

    El resumen es lo que responde la pregunta que importa: cuántas carpetas y cuántos folios
    podrían quedar fuera de la digitalización, y por lo tanto cuánto trabajo se ahorra si la
    verificación las confirma.
    """
    from app.models import UnidadInventario

    consulta = db.query(UnidadInventario)
    if solo_periodo:
        consulta = consulta.filter(UnidadInventario.periodo == solo_periodo.upper())

    por_periodo: dict[str, list] = {}
    candidatas: list[Candidata] = []
    revisadas = sin_periodo = 0

    for u in consulta.all():
        revisadas += 1
        romano = (u.periodo or "").strip().upper()
        if not romano:
            sin_periodo += 1
            continue
        if romano not in por_periodo:
            por_periodo[romano] = opciones_a_evitar(db, romano)
        c = revisar_unidad(u, por_periodo[romano])
        if c:
            candidatas.append(c)

    candidatas.sort(key=lambda c: (-c.puntaje, c.codigo_carpeta))
    eliminar = [c for c in candidatas if c.disposicion == ELIMINACION]
    seleccion = [c for c in candidatas if c.disposicion == SELECCION]
    resumen = {
        "revisadas": revisadas,
        "sin_periodo": sin_periodo,
        "candidatas": len(candidatas),
        "eliminacion": len(eliminar),
        "eliminacion_fuerte": sum(1 for c in eliminar if c.confianza == "fuerte"),
        "eliminacion_folios": sum(c.folios for c in eliminar),
        "seleccion": len(seleccion),
        "seleccion_fuerte": sum(1 for c in seleccion if c.confianza == "fuerte"),
        "seleccion_folios": sum(c.folios for c in seleccion),
    }
    resumen["folios_que_no_se_digitalizarian"] = (resumen["eliminacion_folios"]
                                                  + resumen["seleccion_folios"])
    return candidatas, resumen
