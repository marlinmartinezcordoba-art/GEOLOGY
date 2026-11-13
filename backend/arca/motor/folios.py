"""
Foliación y continuidad.  Reglas R10 a R15.

Transcripción de validarYAjustarContinuidad_ y del bloque de completado de folios de
verificarHomogeneidad_ del motor anterior.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from arca.motor.fechas import FechaNormalizada, normalizar_fecha

NO_APLICA = "N/A"   # R20


@dataclass
class Tramite:
    """Un renglón de la hoja de control."""
    no_item: int = 0
    fecha: FechaNormalizada | None = None
    tipo_documental: str = ""
    folio_desde: int | None = None
    folio_hasta: int | None = None
    no_radicado: str = ""
    sistema_informacion: str = ""
    expediente_sgdea: str = ""
    enlace_acceso: str = ""
    observaciones: str = ""
    fila: int | None = None                 # fila del Excel, para poder señalarla al usuario
    folio_desde_leido: str = ""             # lo que venía escrito, antes de completar
    folio_hasta_leido: str = ""
    no_item_leido: str = ""

    @property
    def extension(self) -> int:
        if self.folio_desde is None or self.folio_hasta is None:
            return 1
        return max(1, self.folio_hasta - self.folio_desde + 1)


@dataclass
class ErrorEnTramite:
    """
    Un error localizado. Sirve para que la pantalla pueda sombrear el renglón exacto y poner
    el mensaje al lado del campo que hay que corregir, en lugar de dar una lista suelta.
    """
    no_item: int
    fila: int | None
    campo: str            # 'fecha', 'tipo_documental', 'folio_desde', 'folio_hasta'
    mensaje: str

    @property
    def texto(self) -> str:
        donde = f" (fila {self.fila})" if self.fila else ""
        return f"Trámite {self.no_item}{donde}: {self.mensaje}"


@dataclass
class ResultadoFolios:
    errores: list[str] = field(default_factory=list)
    errores_localizados: list[ErrorEnTramite] = field(default_factory=list)
    observaciones: list[str] = field(default_factory=list)
    total_folios: int = 0
    # Queda escrito aparte, no mezclado con las observaciones de conservación: cuando los
    # folios de la hoja no son los que declara el inventario de origen, eso tiene que salir
    # en la hoja de control y también en el inventario de salida.
    diferencia_folios: str = ""

    def anotar(self, no_item: int, fila: int | None, campo: str, mensaje: str) -> None:
        e = ErrorEnTramite(no_item, fila, campo, mensaje)
        self.errores_localizados.append(e)
        self.errores.append(e.texto)


_RANGO = re.compile(r"(\d+)\s*(?:-|a|al|–|—)\s*(\d+)", re.IGNORECASE)


def _entero(texto) -> int | None:
    """
    Primer número entero de la celda.

    HALLAZGO. El motor anterior quitaba todos los caracteres que no fueran dígitos, de modo
    que una celda con el rango "21-24" se convertía en el folio 2124 y disparaba un error de
    continuidad imposible de entender para quien diligencia. Por eso su rama de separación de
    rangos nunca llegaba a ejecutarse. Aquí se lee el primer entero y el rango se separa antes,
    en completar_folios.
    """
    if texto is None:
        return None
    encontrado = re.search(r"\d+", str(texto))
    return int(encontrado.group(0)) if encontrado else None


def completar_folios(tramites: list[Tramite], folios_inventario: int | None = None) -> list[str]:
    """
    R12. Completa lo que la hoja manual dejó a medias, antes de verificar.
    Si un trámite trae solo el folio inicial, el final se deduce del inicial del siguiente;
    el del último trámite se toma del total que declara el inventario. Si el rango vino en
    una sola celda, como "12-15" o "12 a 15", se separa.
    Devuelve la lista de observaciones de corrección.
    """
    completados = 0
    for i, t in enumerate(tramites):
        # El rango escrito en una sola celda se separa primero (ver HALLAZGO en _entero).
        if not str(t.folio_hasta_leido or "").strip():
            rango = _RANGO.search(str(t.folio_desde_leido))
            if rango:
                t.folio_desde_leido, t.folio_hasta_leido = rango.group(1), rango.group(2)
                completados += 1

        desde = _entero(t.folio_desde_leido)
        hasta = _entero(t.folio_hasta_leido)

        if desde is not None and hasta is None:
            siguiente = tramites[i + 1] if i + 1 < len(tramites) else None
            desde_siguiente = _entero(siguiente.folio_desde_leido) if siguiente else None
            if desde_siguiente is not None and desde_siguiente > desde:
                t.folio_hasta_leido = str(desde_siguiente - 1)
                completados += 1
            elif siguiente is None:
                total = folios_inventario
                t.folio_hasta_leido = str(total if total is not None and total >= desde else desde)
                completados += 1

    if completados:
        cuerpo = "trámite traía" if completados == 1 else "trámites traían"
        return [f"CORREGIDO. {completados} {cuerpo} solo el folio inicial o el rango en una celda; "
                "se completó el rango."]
    return []


def verificar_folios(tramites: list[Tramite], folios_inventario: int | None = None) -> ResultadoFolios:
    """
    R13, R14, R15, R19 y R20. Recorre los trámites, valida la continuidad y normaliza.
    Un folio ilegible es error. Un folio final menor que el inicial es error. Un folio
    inicial distinto del esperado es error, distinguiendo si hay folios sin asignar o
    repetidos. La renumeración de trámites y la fecha ilegible son correcciones, no errores.
    """
    r = ResultadoFolios()
    r.observaciones.extend(completar_folios(tramites, folios_inventario))

    esperado = 1
    renumerados = 0
    fechas_sf = 0

    for i, t in enumerate(tramites):
        n = i + 1
        if _entero(t.no_item_leido) != n:
            renumerados += 1
        t.no_item = n

        desde, hasta = _entero(t.folio_desde_leido), _entero(t.folio_hasta_leido)
        if desde is None or hasta is None:
            campo = "folio_desde" if desde is None else "folio_hasta"
            r.anotar(n, t.fila, campo,
                     f'folios ilegibles "{t.folio_desde_leido}" a "{t.folio_hasta_leido}".')
            continue

        if hasta < desde:
            r.anotar(n, t.fila, "folio_hasta",
                     f"el folio final {hasta} es menor que el inicial {desde}.")
        if desde != esperado:
            detalle = "hay folios sin asignar" if desde > esperado else "folios repetidos"
            r.anotar(n, t.fila, "folio_desde",
                     f"debía empezar en el folio {esperado} y empieza en {desde} ({detalle}).")
        esperado = hasta + 1
        t.folio_desde, t.folio_hasta = desde, hasta

        if not (t.tipo_documental or "").strip():                      # R18
            r.anotar(n, t.fila, "tipo_documental", "el tipo documental está vacío.")

        if t.fecha is None or t.fecha.sin_fecha:                       # R19
            if t.fecha is None:
                t.fecha = normalizar_fecha(None)
            fechas_sf += 1

        for campo in ("no_radicado", "sistema_informacion", "expediente_sgdea", "enlace_acceso"):
            if not (getattr(t, campo) or "").strip():                  # R20
                setattr(t, campo, NO_APLICA)

    if renumerados:
        cuerpo = "trámite traía" if renumerados == 1 else "trámites traían"
        r.observaciones.append(f"CORREGIDO. {renumerados} {cuerpo} numeración distinta a la "
                               "consecutiva; se renumeraron.")
    if fechas_sf:
        cuerpo = ("trámite con fecha ilegible quedó" if fechas_sf == 1
                  else "trámites con fecha ilegible quedaron")
        r.observaciones.append(f"CORREGIDO. {fechas_sf} {cuerpo} en SF.")

    r.total_folios = esperado - 1
    if folios_inventario is not None and r.total_folios and folios_inventario != r.total_folios:
        # R15. La diferencia de folios es un hecho del expediente y se deja escrita como tal:
        # sale en la hoja de control y en el inventario de salida (FUID). Manda lo que se
        # contó en el papel; el número del inventario se conserva solo como contraste.
        r.diferencia_folios = (
            f"LOS FOLIOS NO COINCIDEN. La hoja de control suma {r.total_folios} folio(s) y el "
            f"inventario de origen declara {folios_inventario}. Manda lo contado en el "
            "expediente; queda la constancia de la diferencia.")
        r.observaciones.append(r.diferencia_folios)
    return r


def encadenar_continuidad(tramites: list[Tramite], ultimo_item: int = 0,
                          ultimo_folio: int = 0) -> tuple[int, int]:
    """
    R10 y R11. Renumera trámites y recalcula folios de forma corrida dentro del expediente,
    conservando la extensión de cada trámite. Se usa en el camino del documento digitalizado
    y al continuar la numeración de un expediente fraccionado (R2).
    Devuelve el último ítem y el último folio, para pasarlos a la parte siguiente.
    """
    item = ultimo_item + 1
    cursor = ultimo_folio + 1
    for t in tramites:
        extension = t.extension
        t.no_item = item
        t.folio_desde = cursor
        t.folio_hasta = cursor + extension - 1
        cursor = t.folio_hasta + 1
        item += 1
    return item - 1, cursor - 1

# ---------------------------------------------------------------------------
# La columna de observaciones es de estado de conservación, no de contabilidad
# ---------------------------------------------------------------------------
# La dirección del proyecto lo pidió expresamente: en observaciones no se escribe cuántos
# folios tiene el trámite ni si la foliación es original o se hizo ahora. Eso ya está en las
# casillas de folio desde y folio hasta, y repetirlo llena la hoja de ruido.
#
# Lo que sí se conserva son las anomalías de foliación —falta un folio, hay uno repetido, hay
# un salto—, porque eso no es contabilidad sino estado del expediente, y es justo lo que un
# investigador necesita saber.
_CONTABILIDAD = re.compile(
    r"""^(?:
        (?:la\s+)?foliaci[oó]n\s+(?:es\s+)?(?:original|propia|de\s+origen|continua|corrida|consecutiva)
      | (?:documento|trámite|tramite|expediente)?\s*sin\s+foliar
      | (?:se\s+)?(?:foli[oó]|folia|numer[oó]|numeraron?)\b[^;]*
      | (?:consta|compuesto|conformado|integrado)\s+de\s+\d+\s+folios?[^;]*
      | \d+\s+folios?(?:\s+en\s+total)?
      | total\s+de\s+folios?[^;]*
      | folios?\s+\d+\s*(?:-|a|al)\s*\d+
      | foliado[^;]*
    )\.?$""",
    re.IGNORECASE | re.VERBOSE)

# Nada que hable de una anomalía se toca, aunque encaje en lo de arriba.
_ANOMALIA = re.compile(r"falta|faltan|repetid|salto|duplicad|ilegible|roto|rasgad|manch|humedad",
                       re.IGNORECASE)


def limpiar_observacion(texto: str) -> str:
    """
    Quita de una observación las frases que solo cuentan folios, y deja el resto intacto.

    Se trabaja frase por frase —separadas por punto y coma o por punto— para no perder el
    estado de conservación que venga en la misma celda. Si al final no queda nada, la casilla
    se deja vacía, que es lo correcto cuando no había nada que observar.

    >>> limpiar_observacion("Foliación original; manchas de humedad en el margen")
    'Manchas de humedad en el margen'
    >>> limpiar_observacion("Falta el folio 12")
    'Falta el folio 12'
    """
    bruto = " ".join(str(texto or "").split())
    if not bruto:
        return ""
    frases = [f.strip() for f in re.split(r"[;.]\s*", bruto) if f.strip()]
    quedan = [f for f in frases if _ANOMALIA.search(f) or not _CONTABILIDAD.match(f)]
    if not quedan:
        return ""
    salida = "; ".join(quedan)
    return salida[:1].upper() + salida[1:]
