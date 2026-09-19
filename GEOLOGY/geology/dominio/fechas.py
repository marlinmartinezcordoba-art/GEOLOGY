"""
Normalización de fechas.  Reglas R27 a R31.

Transcripción de normalizarFechaIso_ y de fechasExtremasValidadas_ del motor anterior.
El criterio de fondo es que el día va primero, por el uso colombiano, y que una fecha
parcial vale más que una fecha inventada.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

ANIO_MINIMO_DILIGENCIAMIENTO = 2025   # R31
HOLGURA_ANIOS_PERIODO = 5             # R30

_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_SIN_FECHA = re.compile(r"^S\s*[/.\-]?\s*F\.?$", re.IGNORECASE)


@dataclass(frozen=True)
class FechaNormalizada:
    """
    completa   la fecha cuando se conoce día, mes y año; None cuando es parcial o ilegible
    texto      'aaaa-mm-dd', 'aaaa-mm' o 'aaaa' según lo que se pudo leer; None si es ilegible
    """
    completa: date | None
    texto: str | None

    @property
    def es_parcial(self) -> bool:
        return self.completa is None and self.texto is not None

    @property
    def sin_fecha(self) -> bool:
        return self.texto is None


def _sin_tildes(valor: str) -> str:
    texto = unicodedata.normalize("NFD", str(valor or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def _mes(nombre: str) -> int | None:
    n = _sin_tildes(nombre).rstrip(".")
    for i, abrev in enumerate(_MESES, start=1):
        if n.startswith(abrev) or (abrev == "sep" and n.startswith("set")):
            return i
    return None


def _armar(anio: int, mes: int, dia: int) -> FechaNormalizada:
    try:
        f = date(anio, mes, dia)
        return FechaNormalizada(f, f.isoformat())
    except ValueError:
        return FechaNormalizada(None, None)


def normalizar_fecha(valor) -> FechaNormalizada:
    """
    R27 y R28. Lleva cualquier escritura de fecha al formato año, mes y día.

    >>> normalizar_fecha("11 de julio de 1931").texto
    '1931-07-11'
    >>> normalizar_fecha("3/3/1932").texto
    '1932-03-03'
    >>> normalizar_fecha("julio de 1931").texto
    '1931-07'
    >>> normalizar_fecha("1931").texto
    '1931'
    >>> normalizar_fecha("S/F").texto is None
    True
    """
    if valor is None:
        return FechaNormalizada(None, None)
    if isinstance(valor, date):
        return FechaNormalizada(valor, valor.isoformat())

    t = str(valor).strip()
    if not t or _SIN_FECHA.match(t):
        return FechaNormalizada(None, None)

    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return _armar(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", t)          # día primero, uso colombiano
    if m:
        return _armar(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r"^(\d{4})[/.](\d{1,2})[/.](\d{1,2})", t)
    if m:
        return _armar(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.fullmatch(r"(\d{1,2})\s*(?:de\s+|/|-)?\s*([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\.?\s*(?:de\s+|/|-)?\s*(\d{4})", t)
    if m and _mes(m.group(2)):
        return _armar(int(m.group(3)), _mes(m.group(2)), int(m.group(1)))
    m = re.fullmatch(r"([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\.?\s+(\d{1,2}),?\s+(?:de\s+)?(\d{4})", t)
    if m and _mes(m.group(1)):
        return _armar(int(m.group(3)), _mes(m.group(1)), int(m.group(2)))

    m = re.fullmatch(r"([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\.?\s*(?:de\s+|/|-)?\s*(\d{4})", t)   # fecha parcial aaaa-mm
    if m and _mes(m.group(1)):
        return FechaNormalizada(None, f"{int(m.group(2)):04d}-{_mes(m.group(1)):02d}")
    m = re.fullmatch(r"(\d{4})-(\d{2})", t)
    if m:
        return FechaNormalizada(None, t)
    m = re.fullmatch(r"1[6-9]\d{2}|20\d{2}", t)                                     # solo el año
    if m:
        return FechaNormalizada(None, t)
    return FechaNormalizada(None, None)


def fecha_mas_reciente(valores: list) -> FechaNormalizada:
    """
    R29. Cuando un documento trae varias fechas, la que se consigna es la más reciente.
    Si ninguna es completa se toma la parcial mayor; si no hay ninguna legible, sin fecha.
    """
    normalizadas = [normalizar_fecha(v) for v in valores]
    completas = [f for f in normalizadas if f.completa]
    if completas:
        return max(completas, key=lambda f: f.completa)
    parciales = [f for f in normalizadas if f.texto]
    return max(parciales, key=lambda f: f.texto) if parciales else FechaNormalizada(None, None)


def fecha_diligenciamiento_valida(valor) -> FechaNormalizada:
    """
    R31. Descarta una fecha de diligenciamiento anterior a 2025, porque corresponde a una
    fecha del documento mal ubicada en el campo dieciséis del formato.
    """
    f = normalizar_fecha(valor)
    if f.completa and f.completa.year < ANIO_MINIMO_DILIGENCIAMIENTO:
        return FechaNormalizada(None, None)
    if f.texto and not f.completa and int(f.texto[:4]) < ANIO_MINIMO_DILIGENCIAMIENTO:
        return FechaNormalizada(None, None)
    return f


def fechas_extremas(fechas: list, periodo_inicio: date | None = None,
                    periodo_fin: date | None = None) -> tuple[date | None, date | None, str]:
    """
    R30. Fecha inicial y final de la unidad. Envoltura de fechas_extremas_detalle para el
    código que solo necesita las tres cosas y no el aviso de lo descartado.
    """
    r = fechas_extremas_detalle(fechas, periodo_inicio, periodo_fin)
    return r.inicial, r.final, r.texto


# ---------------------------------------------------------------------------
# Fechas en prosa y detalle de lo descartado
# ---------------------------------------------------------------------------

_MESES_LARGOS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                 "septiembre", "octubre", "noviembre", "diciembre")


def fecha_en_letras(valor) -> str:
    """
    La fecha escrita como se escribe en una descripción, no como la guarda una máquina.

    >>> fecha_en_letras("1947-03-04")
    '4 de marzo de 1947'
    >>> fecha_en_letras("1947-03")
    'marzo de 1947'
    >>> fecha_en_letras("1947")
    '1947'
    """
    if isinstance(valor, date):
        return f"{valor.day} de {_MESES_LARGOS[valor.month - 1]} de {valor.year}"
    texto = str(valor or "").strip()
    completa = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", texto)
    if completa:
        return (f"{int(completa.group(3))} de {_MESES_LARGOS[int(completa.group(2)) - 1]} "
                f"de {completa.group(1)}")
    parcial = re.fullmatch(r"(\d{4})-(\d{2})", texto)
    if parcial:
        return f"{_MESES_LARGOS[int(parcial.group(2)) - 1]} de {parcial.group(1)}"
    return texto


def rango_en_letras(inicial, final) -> str:
    """El rango de fechas extremas, en prosa. Una sola fecha no se repite dos veces."""
    a, b = fecha_en_letras(inicial), fecha_en_letras(final)
    if a and b:
        return a if a == b else f"{a} a {b}"
    return a or b


@dataclass(frozen=True)
class FechasExtremas:
    """
    Fechas extremas con constancia de lo que se dejó por fuera.

    Regla acordada el 9 de septiembre de 2026: una fecha que se sale del rango del periodo
    se descarta SOLO si el expediente tiene otras que sí sirven. Si ninguna cae dentro, se
    conservan todas, porque entonces el problema no son las fechas sino el periodo asignado,
    y eso tiene que verse. Nunca se devuelve un elemento 3.1.3 en blanco por descarte.
    """
    inicial: date | None
    final: date | None
    texto: str
    descartadas: tuple[date, ...] = ()
    todas_fuera: bool = False

    @property
    def hubo_descarte(self) -> bool:
        return bool(self.descartadas)

    def aviso(self) -> str:
        if self.todas_fuera:
            return ("Ninguna fecha del expediente cae dentro del periodo asignado. Se conservan "
                    "todas: revise el periodo, no las fechas.")
        if self.descartadas:
            cuales = ", ".join(f.isoformat() for f in self.descartadas[:5])
            mas = "…" if len(self.descartadas) > 5 else ""
            return (f"Se dejaron fuera de las fechas extremas {len(self.descartadas)} fecha(s) "
                    f"que se salen del periodo ({cuales}{mas}). Compruebe que estén bien "
                    "transcritas.")
        return ""


def fechas_extremas_detalle(fechas: list, periodo_inicio: date | None = None,
                            periodo_fin: date | None = None) -> FechasExtremas:
    """R30 con constancia. Es la que debe usarse cuando el aviso importa."""
    normalizadas = [f if isinstance(f, FechaNormalizada) else normalizar_fecha(f) for f in fechas]
    completas = [f.completa for f in normalizadas if f.completa]
    descartadas: list[date] = []
    todas_fuera = False

    if completas and periodo_inicio and periodo_fin:
        desde = periodo_inicio.replace(year=periodo_inicio.year - HOLGURA_ANIOS_PERIODO)
        hasta = periodo_fin.replace(year=periodo_fin.year + HOLGURA_ANIOS_PERIODO)
        dentro = [f for f in completas if desde <= f <= hasta]
        fuera = [f for f in completas if not (desde <= f <= hasta)]
        if dentro:
            descartadas = sorted(set(fuera))
            completas = dentro
        elif fuera:
            todas_fuera = True          # se conservan todas; el problema es el periodo

    if completas:
        return FechasExtremas(min(completas), max(completas),
                              f"{min(completas).isoformat()} / {max(completas).isoformat()}",
                              tuple(descartadas), todas_fuera)
    parciales = sorted({f.texto for f in normalizadas if f.texto})
    if parciales:
        texto = parciales[0] if len(parciales) == 1 else f"{parciales[0]} / {parciales[-1]}"
        return FechasExtremas(None, None, texto)
    return FechasExtremas(None, None, "S/F")
