"""
Verificación de la hoja de control F-GDM-007.  Reglas R3, R6 a R9, R16 a R21.

Transcripción de verificarHojaParaDescribir_ y verificarHomogeneidad_ del motor anterior.
Esta es la puerta del flujo de dos pasos: aquí nada se describe, solo se verifica.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from geology.dominio.clasificacion import (Clasificacion, Encabezado, OpcionTvd,
                                        asimilar_con_equivalencia, error_de_clasificacion)
from geology.dominio.estados import Estado
from geology.dominio.folios import Tramite, verificar_folios

PERIODOS_EN_ALCANCE = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII",
                       "IX", "X", "XI", "XII", "XIII", "XIV", "XV")          # R8


@dataclass(frozen=True)
class UnidadInventario:
    """Lo que el inventario de origen del contrato dice de la carpeta."""
    codigo_carpeta: str
    periodo: str = ""              # numeral romano; vacío o S/F cuando el inventario no lo trae
    folios: int | None = None
    asunto: str = ""
    caja_origen: str = ""


@dataclass
class Lectura:
    """Lo que se leyó del archivo de la hoja de control."""
    encabezado: Encabezado
    tramites: list[Tramite]
    responsable: str = ""              # campo 15
    fecha_diligenciamiento: str = ""   # campo 16


@dataclass
class ResultadoVerificacion:
    carpeta: str
    errores: list[str] = field(default_factory=list)
    errores_localizados: list = field(default_factory=list)   # ErrorEnTramite, para sombrear la fila
    observaciones: list[str] = field(default_factory=list)
    periodo: str = ""
    clasificacion: Clasificacion | None = None
    tramites: int = 0
    folios: int = 0
    diferencia_folios: str = ""      # cuando la hoja y el inventario no dan el mismo total

    @property
    def alineada(self) -> bool:
        return bool(self.clasificacion and self.clasificacion.alineada)

    @property
    def estado_resultante(self) -> Estado:
        """R21. Con errores queda devuelta; sin errores, verificada y pendiente de describir."""
        return Estado.DEVUELTO if self.errores else Estado.HOJA_VERIFICADA

    def detalle(self, quien: str = "") -> str:
        """El texto que queda en la bitácora, con el mismo tono del sistema anterior."""
        if self.errores:
            firma = f" (verificó {quien})" if quien else ""
            return f"Hoja de control con errores{firma}: " + " | ".join(self.errores)
        firma = f" por {quien}" if quien else ""
        partes = [f"Hoja de control verificada{firma}",
                  f"{self.tramites} trámite{'s' if self.tramites != 1 else ''}",
                  f"{self.folios} folio{'s' if self.folios != 1 else ''}"]
        texto = ", ".join(partes)
        if self.alineada:
            texto += f". Subserie {self.clasificacion.opcion}"
        if self.observaciones:
            texto += ". " + " ".join(self.observaciones)
        return texto + ". Lista para Generar ISAD(G)."


def periodo_sin_definir(periodo: str) -> bool:
    """R9. El inventario trae la carpeta sin periodo."""
    p = str(periodo or "").strip().upper()
    return p in ("", "S/F", "SF", "SIN FECHA", "N/A", "SP")


def periodo_en_alcance(periodo: str) -> bool:
    """R8. El contrato cubre los periodos I a XV."""
    return str(periodo or "").strip().upper() in PERIODOS_EN_ALCANCE


def verificar_hoja(lectura: Lectura, unidad: UnidadInventario | None,
                   opciones_del_periodo: list[OpcionTvd],
                   todas_las_opciones: list[OpcionTvd] | None = None,
                   periodo_sugerido: tuple[str, str] | None = None) -> ResultadoVerificacion:
    """
    Verificación completa de una hoja de control diligenciada a mano.

    unidad              lo que dice el inventario de origen; None significa que la carpeta
                        no está inventariada y la carga se rechaza (R3)
    periodo_sugerido    par de periodo y fuente para las unidades sin fecha (R9), por ejemplo
                        ('II', 'caja de trabajo 733-CJ-00003')
    """
    carpeta = unidad.codigo_carpeta if unidad else ""
    r = ResultadoVerificacion(carpeta=carpeta)

    if unidad is None:                                                          # R3
        r.errores.append("La carpeta no está en el inventario de origen del contrato, "
                         "es decir no pertenece a la selección inventariada.")
        return r

    e = lectura.encabezado
    if not lectura.tramites:                                                    # R16
        r.errores.append("La hoja no tiene ningún trámite registrado.")
    if not (e.codigo_serie or e.serie):                                         # R17
        r.errores.append("El encabezado no trae serie.")
    if not (e.codigo_subserie or e.subserie):
        r.observaciones.append("El encabezado no trae subserie.")
    if not e.nombre_expediente:
        r.observaciones.append("El campo 7, nombre del expediente, está vacío. "
                               "Se usa el asunto del inventario.")
    if not lectura.responsable:
        r.observaciones.append("El campo 15, responsable, está vacío.")
    if not lectura.fecha_diligenciamiento:
        r.observaciones.append("El campo 16, fecha de diligenciamiento, está vacío.")

    folios = verificar_folios(lectura.tramites, unidad.folios)                  # R12 a R15, R18 a R20
    r.errores.extend(folios.errores)
    r.errores_localizados.extend(folios.errores_localizados)
    r.observaciones.extend(folios.observaciones)
    r.tramites = len(lectura.tramites)
    r.folios = folios.total_folios
    r.diferencia_folios = folios.diferencia_folios

    periodo = str(unidad.periodo or "").strip().upper()
    r.periodo = periodo

    if periodo_sin_definir(periodo) or not opciones_del_periodo:                # R9
        sugerencia = ""
        if periodo_sugerido and periodo_sugerido[0]:
            sugerencia = f" (se sugiere el {periodo_sugerido[0]} por su {periodo_sugerido[1]})"
        r.errores.append("No fue posible determinar el periodo: el expediente no tiene fechas "
                         "legibles y el inventario de origen tampoco lo trae. "
                         f"Asígnelo en el editor{sugerencia}.")
        return r

    if not periodo_en_alcance(periodo):                                         # R8
        r.errores.append(f"FUERA DE ALCANCE. El periodo {periodo} no hace parte de las tablas "
                         "de valoración documental del contrato, que van del I al XV.")
        return r

    clasificacion = asimilar_con_equivalencia(e, opciones_del_periodo,
                                              todas_las_opciones or opciones_del_periodo)
    r.clasificacion = clasificacion
    if clasificacion.alineada:                                                  # R23, R24
        if clasificacion.observacion:
            r.observaciones.append(clasificacion.observacion)
    else:
        r.errores.append(error_de_clasificacion(periodo))                       # R25
    return r
