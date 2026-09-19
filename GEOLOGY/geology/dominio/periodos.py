"""
Resolución del periodo institucional.  Reglas R6, R7 y R9.

CAMBIO DE REGLA, 9 de septiembre de 2026.  Manda la fecha, no el inventario.

Antes el periodo lo mandaba el inventario de origen y las fechas solo servían de respaldo.
Se invierte el orden: el periodo lo determinan las fechas extremas del expediente y el
inventario pasa a ser una referencia que se contrasta.  Si el inventario dice periodo X y
las fechas del documento caen en el periodo Y, el expediente queda en Y y la diferencia se
deja anotada para que quien revisa la vea.

Por qué, en términos archivísticos.  Las tablas de valoración documental del contrato están
armadas por periodos de la estructura del productor, de modo que el periodo no es un dato
administrativo sino la identificación del productor que generó el trámite.  El principio de
procedencia y el de orden original, recogidos en el Acuerdo 027 de 2006 y desarrollados para
fondos acumulados en los Acuerdos 004 y 005 de 2013 y en el 002 de 2014, obligan a clasificar
según la estructura vigente en el momento de producción del documento, y lo que prueba ese
momento es la fecha del documento, no la casilla que alguien diligenció después en un
inventario. El inventario de origen del Servicio Geológico Colombiano se levantó con la
información disponible en su momento y puede traer el periodo equivocado; el papel no.

El orden queda así:

  1. Lo que una persona haya fijado a mano, que siempre manda sobre lo automático.
  2. Las fechas extremas del expediente.  Manda la fecha inicial, porque es la que dice
     cuándo se abrió el trámite.  Si la final cae en otro periodo se conserva el de la
     inicial y se deja constancia, que es como se trata un libro empastado que cruza
     periodos (R7): se registra, no se rechaza.
  3. Si hay fecha pero no cae dentro de ningún periodo de las tablas del contrato, no se tapa
     con el inventario: lo mira una persona, porque o la fecha se leyó mal o el documento no
     pertenece al fondo.
  4. Solo cuando no hay ninguna fecha legible (S/F) entra el periodo del inventario, y queda
     marcado como no verificado por fechas.
  5. Si tampoco hay inventario, lo asigna una persona con la sugerencia de las carpetas
     compañeras de su caja de trabajo (R9).

Resuelto el periodo, la tabla de valoración documental de ese periodo es la lista cerrada
de la que sale la clasificación.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

ORIGEN_INVENTARIO = "inventario"
ORIGEN_FECHAS = "fechas extremas"
ORIGEN_MANUAL = "asignado por una persona"
ORIGEN_CAJA = "caja de trabajo"


@dataclass(frozen=True)
class RangoPeriodo:
    """Un periodo institucional con su rango, tal como está en la tabla convalidada."""
    romano: str
    inicio: date | None
    fin: date | None

    def contiene(self, f: date) -> bool:
        if not f:
            return False
        if self.inicio and f < self.inicio:
            return False
        if self.fin and f > self.fin:
            return False
        return True


@dataclass(frozen=True)
class PeriodoResuelto:
    romano: str | None
    origen: str
    aviso: str = ""
    requiere_persona: bool = False
    discrepancia: str = ""          # el inventario decía otra cosa; queda para control de calidad

    @property
    def resuelto(self) -> bool:
        return bool(self.romano)


def resolver_por_fechas(fecha_inicial: date | None, fecha_final: date | None,
                        rangos: list[RangoPeriodo]) -> PeriodoResuelto:
    """
    Deduce el periodo a partir de las fechas extremas. Manda la fecha inicial, porque es la
    que dice cuándo se abrió el trámite. Si la fecha final cae en otro periodo se conserva el
    de la fecha inicial y se deja constancia (R7).
    """
    if not fecha_inicial and not fecha_final:
        return PeriodoResuelto(None, ORIGEN_FECHAS, requiere_persona=True,
                               aviso="El expediente no tiene ninguna fecha legible.")

    referencia = fecha_inicial or fecha_final
    contienen = [r for r in rangos if r.contiene(referencia)]
    if not contienen:
        cercano = _mas_cercano(referencia, rangos)
        return PeriodoResuelto(
            None, ORIGEN_FECHAS, requiere_persona=True,
            aviso=(f"La fecha {referencia.isoformat()} no cae dentro de ningún periodo de las "
                   f"tablas de valoración del contrato" +
                   (f"; el más cercano es el {cercano}." if cercano else ".")))

    elegido = contienen[0]
    aviso = ""
    if fecha_final and not elegido.contiene(fecha_final):
        otros = [r.romano for r in rangos if r.contiene(fecha_final)]
        if otros:
            aviso = (f"Las fechas extremas cruzan periodos: la inicial corresponde al "
                     f"{elegido.romano} y la final al {otros[0]}. Se conserva el de la fecha "
                     "inicial; verifique con el archivero si se trata de un libro empastado.")
    return PeriodoResuelto(elegido.romano, ORIGEN_FECHAS, aviso)


def _mas_cercano(f: date, rangos: list[RangoPeriodo]) -> str | None:
    def distancia(r: RangoPeriodo) -> int:
        if r.inicio and f < r.inicio:
            return (r.inicio - f).days
        if r.fin and f > r.fin:
            return (f - r.fin).days
        return 0
    candidatos = [r for r in rangos if r.inicio or r.fin]
    return min(candidatos, key=distancia).romano if candidatos else None


def resolver_periodo(periodo_inventario: str, fecha_inicial: date | None, fecha_final: date | None,
                     rangos: list[RangoPeriodo], periodo_manual: str = "",
                     sugerencia_caja: tuple[str, str] | None = None) -> PeriodoResuelto:
    """
    Aplica el orden completo y devuelve el periodo, de dónde salió y, si el inventario decía
    otra cosa, la diferencia. No es lo mismo un periodo probado por las fechas del documento
    que uno heredado de una casilla del inventario, y quien revisa tiene que poder verlo.
    """
    from geology.dominio.verificar_hoja import periodo_sin_definir

    inventario = str(periodo_inventario or "").strip().upper()
    tiene_inventario = not periodo_sin_definir(inventario)

    # 1. Lo que fijó una persona manda sobre todo lo demás.
    if periodo_manual:
        fijado = periodo_manual.strip().upper()
        discrepancia = ""
        if tiene_inventario and fijado != inventario:
            discrepancia = (f"Fijado a mano en el periodo {fijado}; el inventario de origen "
                            f"decía {inventario}.")
        return PeriodoResuelto(fijado, ORIGEN_MANUAL, discrepancia=discrepancia)

    # 2. Manda la fecha.
    por_fechas = resolver_por_fechas(fecha_inicial, fecha_final, rangos)
    if por_fechas.resuelto:
        discrepancia = ""
        aviso = por_fechas.aviso
        if tiene_inventario and por_fechas.romano != inventario:
            discrepancia = (
                f"DIFERENCIA CON EL INVENTARIO. El inventario de origen ubica esta carpeta en "
                f"el periodo {inventario}, pero las fechas extremas del documento "
                f"({_texto_fechas(fecha_inicial, fecha_final)}) corresponden al periodo "
                f"{por_fechas.romano}. Se deja en el {por_fechas.romano}, porque el periodo lo "
                f"prueba la fecha del documento y no la casilla del inventario. Revíselo y, si "
                f"el inventario tiene razón, fíjelo a mano en el editor.")
            aviso = (aviso + " " + discrepancia).strip()
        return PeriodoResuelto(por_fechas.romano, ORIGEN_FECHAS, aviso, discrepancia=discrepancia)

    # 3. Hay fecha pero no cae en ningún periodo de las tablas del contrato. Esto no se tapa
    #    con el inventario: o la fecha se leyó mal, o esa fecha no pertenece al fondo. Lo mira
    #    una persona, con lo que dice el inventario como referencia.
    if fecha_inicial or fecha_final:
        referencia = (f" El inventario de origen dice periodo {inventario}; si es el correcto, "
                      "fíjelo a mano." if tiene_inventario else "")
        return PeriodoResuelto(
            None, ORIGEN_FECHAS, requiere_persona=True,
            aviso=(por_fechas.aviso + " Revise que la fecha del documento se haya leído bien." +
                   referencia))

    # 4. Sin ninguna fecha legible: entra el inventario, marcado como no verificado.
    if tiene_inventario:
        return PeriodoResuelto(
            inventario, ORIGEN_INVENTARIO,
            aviso=(f"{por_fechas.aviso} Se toma el periodo {inventario} del inventario de origen "
                   "porque no hay fechas con qué comprobarlo. Confírmelo antes de aprobar.").strip())

    # 5. Ni fecha ni inventario: lo pone una persona.
    if sugerencia_caja and sugerencia_caja[0]:
        return PeriodoResuelto(
            None, ORIGEN_CAJA, requiere_persona=True,
            aviso=(f"{por_fechas.aviso} Se sugiere el periodo {sugerencia_caja[0]} por su "
                   f"{sugerencia_caja[1]}; confírmelo en el editor.").strip())
    return PeriodoResuelto(None, por_fechas.origen, por_fechas.aviso, requiere_persona=True)


def _texto_fechas(fi: date | None, ff: date | None) -> str:
    if fi and ff and fi != ff:
        return f"{fi.isoformat()} a {ff.isoformat()}"
    return (fi or ff).isoformat() if (fi or ff) else "sin fecha"
