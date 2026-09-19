"""
Libros empastados y carpetas sueltas.  Cómo se leen sus fechas extremas.

La diferencia no es de forma, es de principio. Un libro encuadernado no se puede reordenar
sin romper el orden original: los trámites quedaron cosidos en la secuencia en que se
asentaron, y esa secuencia es evidencia. Por eso sus fechas extremas se leen por los folios
—la del primer asiento y la del último—, aunque en la mitad del libro aparezca una fecha
posterior a la del final, que en un libro de contabilidad pasa a cada rato.

Una carpeta suelta sí se ordena cronológicamente durante la intervención, así que sus fechas
extremas son sencillamente la más antigua y la más reciente.

Cómo se sabe cuál es cuál. El inventario de origen lo dice: cuatrocientas sesenta y cuatro
unidades del contrato traen las palabras LIBRO, TOMO o EMPASTADO en el asunto, la serie o la
subserie. Eso da una detección automática, que queda como PROPUESTA. La confirma o la niega
una persona, y esa decisión manda. Además, unas fechas en desorden dentro de la hoja de
control son señal de libro y levantan una alerta para que alguien lo mire.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

DETECTADO = "detectado en el inventario de origen"
CONFIRMADO = "confirmado por una persona"
NEGADO = "descartado por una persona"
SUELTA = "carpeta suelta"

_PALABRAS = re.compile(r"\b(LIBRO|LIBROS|TOMO|TOMOS|EMPASTAD\w*|ENCUADERNAD\w*|"
                       r"VOLUMEN|VOLUMENES|COPIADOR\w*)\b")


def _sin_tildes(valor: str) -> str:
    t = unicodedata.normalize("NFD", str(valor or "").upper())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class Encuadernacion:
    """Si la unidad es un libro empastado, y de dónde salió esa afirmación."""
    es_libro: bool
    origen: str
    evidencia: str = ""
    confirmada: bool = False        # una persona ya se pronunció

    @property
    def aviso(self) -> str:
        if self.confirmada:
            return ""
        if self.es_libro:
            return (f"Se tomó como libro empastado porque el inventario de origen dice "
                    f"«{self.evidencia}». Las fechas extremas se leen por el orden de los "
                    "folios, no por la fecha más antigua y la más reciente. Confírmelo.")
        return ""


def detectar(asunto: str = "", serie: str = "", subserie: str = "") -> tuple[bool, str]:
    """Busca las palabras que delatan un libro en lo que dice el inventario de origen."""
    for campo in (asunto, subserie, serie):
        texto = _sin_tildes(campo)
        encontrado = _PALABRAS.search(texto)
        if encontrado:
            return True, str(campo).strip()
    return False, ""


def encuadernacion(unidad, decision_manual: bool | None = None) -> Encuadernacion:
    """
    Resuelve si la unidad es un libro. Lo que diga una persona manda sobre la detección,
    igual que con el periodo: lo automático propone, la persona dispone.
    """
    detectado, evidencia = detectar(
        getattr(unidad, "asunto", "") or "",
        getattr(unidad, "serie", "") or "",
        getattr(unidad, "subserie", "") or "") if unidad else (False, "")

    if decision_manual is True:
        return Encuadernacion(True, CONFIRMADO, evidencia, confirmada=True)
    if decision_manual is False:
        return Encuadernacion(False, NEGADO, evidencia, confirmada=True)
    if detectado:
        return Encuadernacion(True, DETECTADO, evidencia)
    return Encuadernacion(False, SUELTA)


def fechas_desordenadas(tramites) -> list:
    """
    Los trámites cuya fecha es anterior a la del trámite anterior.

    En una carpeta suelta que se organizó cronológicamente esto no debería ocurrir, así que
    es señal de dos cosas: o la hoja se diligenció sin ordenar, o la unidad es un libro y no
    se puede ordenar. Cualquiera de las dos hay que mirarla.
    """
    con_fecha = [t for t in sorted(tramites, key=lambda x: x.no_item or 0) if t.fecha]
    desordenados = []
    for anterior, actual in zip(con_fecha, con_fecha[1:]):
        if actual.fecha < anterior.fecha:
            desordenados.append(actual)
    return desordenados


def fechas_extremas_de_libro(tramites, admitidas: set[date] | None = None
                             ) -> tuple[date | None, date | None]:
    """
    Fechas extremas de un libro: la del primer asiento y la del último, por folio.

    `admitidas` es el conjunto de fechas que pasaron el filtro del periodo. Se respeta ese
    filtro para no dejar entrar un año mal transcrito, pero dentro de lo admitido manda el
    orden de los folios y no cuál sea la más antigua.
    """
    ordenados = [t for t in sorted(tramites, key=lambda x: x.no_item or 0)
                 if t.fecha and (admitidas is None or t.fecha in admitidas)]
    if not ordenados:
        return None, None
    return ordenados[0].fecha, ordenados[-1].fecha


def resolver_fechas(tramites, unidad, decision_manual: bool | None = None,
                    periodo_inicio: date | None = None, periodo_fin: date | None = None):
    """
    Las fechas extremas de la unidad, leídas según lo que la unidad sea.

    Devuelve la fecha inicial, la final, el texto para el elemento 3.1.3, la encuadernación
    resuelta y los avisos que deban quedar en la bitácora.

    En los dos casos se aplica primero el filtro del periodo con la regla acordada —una
    fecha que se sale se descarta solo si el expediente tiene otras que sirven—, y después
    se decide de dónde salen los extremos: por folio si es libro, por antigüedad si no.
    """
    from geology.dominio.fechas import fechas_extremas_detalle

    enc = encuadernacion(unidad, decision_manual)
    fechas = [t.fecha for t in tramites if t.fecha]
    detalle = fechas_extremas_detalle(
        [t.fecha_texto or (t.fecha.isoformat() if t.fecha else None) for t in tramites
         if t.fecha or t.fecha_texto],
        periodo_inicio, periodo_fin)

    avisos = [x for x in (detalle.aviso(), enc.aviso) if x]

    if enc.es_libro and fechas:
        # Se admiten las fechas que sobrevivieron al filtro del periodo.
        admitidas = None
        if detalle.descartadas:
            admitidas = {f for f in fechas if f not in set(detalle.descartadas)}
        inicial, final = fechas_extremas_de_libro(tramites, admitidas)
        if inicial and final:
            texto = f"{inicial.isoformat()} / {final.isoformat()}"
            if (inicial, final) != (detalle.inicial, detalle.final):
                avisos.append(
                    "Por ser libro empastado las fechas extremas se tomaron del primer y del "
                    "último folio, no de la más antigua y la más reciente, para no alterar el "
                    "orden original.")
            return inicial, final, texto, enc, avisos

    desordenados = fechas_desordenadas(tramites)
    if desordenados and not enc.es_libro:
        cuales = ", ".join(str(t.no_item) for t in desordenados[:6])
        avisos.append(
            f"Las fechas de la hoja de control no van en orden: los trámites {cuales} traen "
            "una fecha anterior a la del trámite que los precede. O la hoja se diligenció sin "
            "ordenar, o la unidad es un libro empastado que no se puede reordenar. Verifíquelo.")

    return detalle.inicial, detalle.final, detalle.texto, enc, avisos
