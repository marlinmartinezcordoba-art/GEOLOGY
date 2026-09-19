"""
Cajas definitivas, inventario de salida y rótulos oficiales.

Reglas de la dirección del proyecto, 9 de septiembre de 2026:

  · Solo entran al inventario de salida las descripciones aprobadas.
  · Una caja definitiva pertenece a UN SOLO PERIODO. Mezclar periodos NO se permite: la
    carpeta 0001 del periodo II y la 0023 del periodo V no pueden quedar en la misma caja.
    Esto se bloquea, no se advierte.
  · Dentro del periodo, las carpetas se agrupan por serie. Mezclar series sí se permite,
    pero se advierte, porque el cierre de la caja a veces lo obliga y esa decisión es del
    archivero.
  · El número de carpeta dentro de la caja lo genera el sistema, de forma consecutiva.
  · La persona decide cuántas carpetas entran: una, o las que quepan.
  · Con la relación de carpetas ya asignadas se producen el rótulo de carpeta F-GDM-006 y
    el rótulo de caja F-GDM-008.
  · Una vez la caja se cierra, su inventario queda en firme y no se modifica.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from geology.dominio.estados import Estado


class MezclaDePeriodos(Exception):
    """Se intentó meter en una caja una carpeta de un periodo distinto al de la caja."""


class CajaCerrada(Exception):
    """La caja ya se cerró y su inventario está en firme."""


@dataclass
class CarpetaParaInventario:
    codigo_carpeta: str
    periodo: str
    serie: str
    subserie: str
    fecha_inicial: date | None
    fecha_final: date | None
    estado: Estado
    folios: int | None = None
    titulo: str | None = None
    codigo_dependencia: str | None = None
    dependencia: str | None = None
    consecutivo_en_caja: int | None = None
    # Los códigos de serie y de subserie de la tabla de valoración. Van en los rótulos
    # oficiales, que traen casilla propia para cada uno.
    codigo_serie: str | None = None
    codigo_subserie: str | None = None


@dataclass
class ResultadoAsignacion:
    asignadas: list[CarpetaParaInventario] = field(default_factory=list)
    rechazadas: list[tuple[str, str]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    periodo_de_la_caja: str = ""


def puede_ir_al_inventario(carpeta: CarpetaParaInventario) -> tuple[bool, str]:
    """Solo entran las descripciones aprobadas, es decir cuando el trámite terminó."""
    if carpeta.estado == Estado.EN_INVENTARIO:
        return False, f"{carpeta.codigo_carpeta} ya está en el inventario de salida."
    if carpeta.estado != Estado.ARCHIVADO:
        return False, (f"{carpeta.codigo_carpeta} está en «{carpeta.estado.value}». Solo entran "
                       "al inventario las descripciones aprobadas.")
    return True, ""


def verificar_periodo(carpeta: CarpetaParaInventario, periodo_de_la_caja: str) -> None:
    """
    Bloqueo duro. Una caja definitiva es de un solo periodo institucional.
    Lanza MezclaDePeriodos con el detalle, para que el mensaje sirva a quien está en bodega.
    """
    mio = (carpeta.periodo or "").strip().upper()
    caja = (periodo_de_la_caja or "").strip().upper()
    if not mio:
        raise MezclaDePeriodos(
            f"{carpeta.codigo_carpeta} no tiene periodo asignado y no puede entrar a una caja "
            "definitiva. Asígnele el periodo antes de reubicarla.")
    if caja and mio != caja:
        raise MezclaDePeriodos(
            f"MEZCLA DE PERIODOS. La caja es del periodo {caja} y {carpeta.codigo_carpeta} es del "
            f"periodo {mio}. Una caja definitiva pertenece a un solo periodo: use otra caja.")


def asignar_a_caja(carpetas: list[CarpetaParaInventario], caja: str,
                   periodo_de_la_caja: str = "", series_ya_en_la_caja: list[str] | None = None,
                   consecutivo_inicial: int = 1, cerrada: bool = False) -> ResultadoAsignacion:
    """
    Asigna a la caja las carpetas que se le pasen, en el orden que corresponde, y le pone a
    cada una su número de carpeta consecutivo.
    """
    if cerrada:
        raise CajaCerrada(f"La caja {caja} está cerrada y su inventario quedó en firme. "
                          "Para modificarla hay que reabrirla de manera explícita.")

    r = ResultadoAsignacion(periodo_de_la_caja=(periodo_de_la_caja or "").strip().upper())
    series = list(series_ya_en_la_caja or [])
    consecutivo = consecutivo_inicial

    # Si la caja está vacía, su periodo lo define lo que entra. Pero si en el mismo envío
    # vienen carpetas de periodos distintos, el sistema no elige por su cuenta cuál manda:
    # devuelve el envío completo y pide que se separe, que es lo que evita una caja mal armada.
    if not r.periodo_de_la_caja:
        periodos = sorted({(c.periodo or "").strip().upper() for c in carpetas
                           if (c.periodo or "").strip()})
        if len(periodos) > 1:
            detalle = "; ".join(
                f"periodo {p}: " + ", ".join(c.codigo_carpeta for c in carpetas
                                             if (c.periodo or "").strip().upper() == p)
                for p in periodos)
            raise MezclaDePeriodos(
                f"MEZCLA DE PERIODOS. Está intentando meter en la caja {caja} carpetas de "
                f"{len(periodos)} periodos distintos ({detalle}). Una caja definitiva pertenece "
                "a un solo periodo: separe el envío y use una caja por periodo.")

    for carpeta in ordenar_para_inventario(carpetas):
        permitido, razon = puede_ir_al_inventario(carpeta)
        if not permitido:
            r.rechazadas.append((carpeta.codigo_carpeta, razon))
            continue

        # Si la caja está vacía, el periodo de la primera carpeta define el de la caja.
        if not r.periodo_de_la_caja:
            r.periodo_de_la_caja = (carpeta.periodo or "").strip().upper()
        try:
            verificar_periodo(carpeta, r.periodo_de_la_caja)
        except MezclaDePeriodos as e:
            r.rechazadas.append((carpeta.codigo_carpeta, str(e)))
            continue

        if series and carpeta.serie not in series:
            r.avisos.append(f"Mezcla de series. La caja {caja} ya trae "
                            f"{'; '.join(sorted(set(series)))} y esta carpeta es de "
                            f"{carpeta.serie}. Se permite, pero revise si conviene.")
        if carpeta.serie not in series:
            series.append(carpeta.serie)

        carpeta.consecutivo_en_caja = consecutivo
        consecutivo += 1
        r.asignadas.append(carpeta)
    return r


def ordenar_para_inventario(carpetas: list[CarpetaParaInventario]) -> list[CarpetaParaInventario]:
    """
    El orden lo resuelve el sistema: serie, subserie y dentro de ellas la fecha inicial, de
    modo que el inventario quede agrupado por series y en orden cronológico, como lo indica
    el Archivo General de la Nación.
    """
    def clave(c: CarpetaParaInventario):
        return (c.serie or "", c.subserie or "",
                c.fecha_inicial or date.min, c.fecha_final or date.min, c.codigo_carpeta)
    return sorted(carpetas, key=clave)


# ---------------------------------------------------------------------------
# Rótulos oficiales
# ---------------------------------------------------------------------------
def _fechas(inicial: date | None, final: date | None) -> dict:
    partir = lambda f: ({"dd": f"{f.day:02d}", "mm": f"{f.month:02d}", "aaaa": str(f.year)}
                        if f else {"dd": "", "mm": "", "aaaa": ""})
    return {"inicial": partir(inicial), "final": partir(final)}


def rotulo_de_carpeta(carpeta: CarpetaParaInventario, caja: str, tomo: str = "1 de 1") -> dict:
    """Rótulo F-GDM-006 versión 5, con los campos del formato oficial."""
    return {
        "formato": "F-GDM-006", "version": "5", "clasificacion": "PÚBLICA",
        "codigo_dependencia_productora": carpeta.codigo_dependencia or "",
        "dependencia_productora": carpeta.dependencia or "",
        "codigo_serie": carpeta.codigo_serie or "", "serie": carpeta.serie or "",
        "codigo_subserie": carpeta.codigo_subserie or "", "subserie": carpeta.subserie or "",
        "descripcion_expediente": carpeta.titulo or "",
        "nombre_expediente": carpeta.titulo or "",
        "no_carpeta": carpeta.consecutivo_en_caja,
        "tomo": tomo,
        "no_folios": carpeta.folios,
        "no_caja": caja,
        "fechas_extremas": _fechas(carpeta.fecha_inicial, carpeta.fecha_final),
        "codigo_carpeta_origen": carpeta.codigo_carpeta,
    }


def rotulo_de_caja(caja: str, carpetas: list[CarpetaParaInventario], periodo: str) -> dict:
    """
    Rótulo F-GDM-008 versión 5. El contenido se arma con la relación de carpetas que
    quedaron efectivamente en la caja, con su número consecutivo.
    """
    asignadas = [c for c in carpetas if c.consecutivo_en_caja]
    series = sorted({c.serie for c in asignadas if c.serie})
    subseries = sorted({c.subserie for c in asignadas if c.subserie})
    iniciales = [c.fecha_inicial for c in asignadas if c.fecha_inicial]
    finales = [c.fecha_final for c in asignadas if c.fecha_final]
    numeros = [c.consecutivo_en_caja for c in asignadas]

    contenido = "; ".join(
        f"Carpeta {c.consecutivo_en_caja}: {c.titulo or c.codigo_carpeta} "
        f"({c.folios or '?'} folios)" for c in asignadas)

    return {
        "formato": "F-GDM-008", "version": "5", "clasificacion": "PÚBLICA",
        "codigo_dependencia": next((c.codigo_dependencia for c in asignadas if c.codigo_dependencia), ""),
        "dependencia": next((c.dependencia for c in asignadas if c.dependencia), ""),
        "codigo_serie": next((c.codigo_serie for c in asignadas if c.codigo_serie), ""),
        "codigo_subserie": next((c.codigo_subserie for c in asignadas if c.codigo_subserie), ""),
        "serie": "; ".join(series), "subserie": "; ".join(subseries),
        "no_caja": caja, "periodo": periodo,
        "contenido": contenido,
        "total_carpetas": len(asignadas),
        "rango_carpetas": (f"{min(numeros)} a {max(numeros)}" if numeros else ""),
        "total_folios": sum(c.folios or 0 for c in asignadas),
        "fechas_extremas": _fechas(min(iniciales) if iniciales else None,
                                   max(finales) if finales else None),
    }
