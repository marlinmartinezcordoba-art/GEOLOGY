"""El diseño del reporte de productividad para Power BI: tablas, columnas y tipos. Sin datos de nadie.

Una sola definición sirve para todo: importar el libro de Excel con ese diseño, descargar la plantilla
vacía, exportar el libro lleno y entregar cada tabla a Power BI (JSON o CSV). Los nombres de tabla y de
columna son los del modelo de Power BI, para que el reporte se conecte sin transformar nada.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from arca.modelos.productividad import Actividad, DiaCalendario, Entrega, Frente, MetaTurno, Novedad, PlanPersonal, RegistroCalidad, RegistroProduccion, Turno

TEXTO, ENTERO, NUMERO, FECHA, SINO = "texto", "entero", "numero", "fecha", "sino"
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# Listas cerradas del diseño (hoja «Listas»).
RESULTADOS_CALIDAD = ["Aprobado", "Aprobado tras ampliar muestra", "Rechazado", "En revisión"]
ESTADOS_NOVEDAD = ["Abierta", "Cerrada"]
ESTADOS_ENTREGA = ["Entregado", "Aceptado", "Devuelto con observaciones"]
TIPOS_NOVEDAD = [
    "Caja faltante", "Caja sobrante", "Rótulo distinto al inventario", "Deterioro físico", "Biológico (hongos)",
    "Material de otro ítem", "Documento sin expediente",
]
UNIDADES = ["imágenes", "m lineales", "folios", "cajas", "expedientes", "unidades documentales", "hojas", "documentos"]
FUENTES_AUTOMATICAS = {
    "imagenes_recibidas": "Imágenes recibidas en ARCA (todas las que entran a la bandeja de calidad)",
    "imagenes_aprobadas": "Imágenes aprobadas por el control de calidad de ARCA",
    "expedientes_inventariados": "Unidades documentales integradas desde el FUID",
    "paginas_ocr": "Páginas leídas con OCR por ARCA",
    "hojas_verificadas": "Hojas de control verificadas (expedientes)",
    "folios_verificados": "Folios de las hojas de control verificadas",
    "documentos_hoja": "Documentos (trámites) registrados en hojas de control verificadas",
    "descripciones_aprobadas": "Descripciones ISAD(G) aprobadas (expedientes)",
}


@dataclass(frozen=True)
class Columna:
    nombre: str  # como en Power BI y en el libro de Excel
    atributo: str | None  # campo del modelo; None = columna calculada al exportar
    tipo: str = TEXTO
    obligatoria: bool = False


@dataclass(frozen=True)
class Tabla:
    nombre: str  # nombre de la tabla en Power BI
    hoja: str  # nombre de la hoja en el libro de Excel
    modelo: type
    columnas: tuple[Columna, ...]
    es_registro: bool = False  # hecho diario (se agrega) o configuración (se reemplaza)


TABLAS: tuple[Tabla, ...] = (
    Tabla("dFrentes", "dFrentes", Frente, (
        Columna("Cod_Frente", "codigo", obligatoria=True), Columna("Frente", "nombre", obligatoria=True), Columna("Sede", "sede"),
        Columna("Unidad_Avance", "unidad", obligatoria=True), Columna("Volumen_Total", "volumen_total", NUMERO),
        Columna("Actividad_Avance", "actividad_avance"), Columna("Fecha_Inicio", "fecha_inicio", FECHA), Columna("Fecha_Fin", "fecha_fin", FECHA),
    )),
    Tabla("dActividades", "dActividades", Actividad, (
        Columna("Actividad_Clave", "clave", obligatoria=True), Columna("Cod_Frente", "frente", obligatoria=True), Columna("Orden", "orden", ENTERO),
        Columna("Actividad", "nombre", obligatoria=True), Columna("Unidad", "unidad", obligatoria=True), Columna("Rol", "rol"),
        Columna("Cuenta_Avance", "cuenta_avance", SINO), Columna("Fuente_Automatica", "fuente_automatica"),
    )),
    Tabla("dMetas", "dMetas", MetaTurno, (
        Columna("Clave", None), Columna("Actividad_Clave", "actividad", obligatoria=True), Columna("Turno", "turno", obligatoria=True),
        Columna("Personas_Plan", "personas_plan", NUMERO), Columna("Meta_Turno", "meta_turno", NUMERO), Columna("Meta_Persona", None, NUMERO),
    )),
    Tabla("dPersonal", "dPersonal", PlanPersonal, (
        Columna("Frente", "frente", obligatoria=True), Columna("Rol", "rol", obligatoria=True), Columna("Turno_A", "turno_a", NUMERO),
        Columna("Turno_B", "turno_b", NUMERO), Columna("Turno_C", "turno_c", NUMERO), Columna("Presentes_Dia", None, NUMERO),
        Columna("Nomina_con_Relevos", "nomina_con_relevos", NUMERO), Columna("Meta_Persona_Turno", "meta_persona_turno", NUMERO),
        Columna("Unidad", "unidad"), Columna("Que_Hace", "que_hace"),
    )),
    Tabla("dTurnos", "dTurnos", Turno, (Columna("Turno", "codigo", obligatoria=True), Columna("Horario", "horario"), Columna("Jornada", "jornada"))),
    Tabla("dCalendario", "dCalendario", DiaCalendario, (
        Columna("Fecha", "fecha", FECHA, True), Columna("Anio", None, ENTERO), Columna("Mes", None, ENTERO), Columna("Nombre_Mes", None),
        Columna("Semana_ISO", None, ENTERO), Columna("Dia_Semana", None), Columna("Operativo", "operativo", SINO), Columna("Fase", "fase"),
        Columna("Fecha_Entrega_Corte", "fecha_entrega_corte", FECHA), Columna("Es_Dia_Entrega", "es_dia_entrega", SINO),
    )),
    Tabla("fProduccion", "Registro_Produccion", RegistroProduccion, (
        Columna("Fecha", "fecha", FECHA, True), Columna("Turno", "turno", obligatoria=True), Columna("Actividad", "actividad", obligatoria=True),
        Columna("Lote", "lote"), Columna("Caja_Desde", "caja_desde"), Columna("Caja_Hasta", "caja_hasta"), Columna("Cantidad", "cantidad", NUMERO, True),
        Columna("Personas_Presentes", "personas_presentes", NUMERO), Columna("Horas_Efectivas", "horas_efectivas", NUMERO),
        Columna("Supervisor", "supervisor"), Columna("Observaciones", "observaciones"), Columna("Origen", "origen"),
    ), es_registro=True),
    Tabla("fCalidad", "Registro_Calidad", RegistroCalidad, (
        Columna("Fecha", "fecha", FECHA, True), Columna("Cod_Frente", "frente", obligatoria=True), Columna("Lote", "lote"),
        Columna("Unidad_Inspeccion", "unidad_inspeccion"), Columna("Tamano_Lote", "tamano_lote", NUMERO), Columna("Muestra", "muestra", NUMERO),
        Columna("Criticos", "criticos", ENTERO), Columna("Mayores", "mayores", ENTERO), Columna("Menores", "menores", ENTERO),
        Columna("Limitaciones_Original", "limitaciones_original", ENTERO), Columna("Resultado", "resultado", obligatoria=True),
        Columna("Analista", "analista"), Columna("Observaciones", "observaciones"),
    ), es_registro=True),
    Tabla("fNovedades", "Registro_Novedades", Novedad, (
        Columna("Fecha", "fecha", FECHA, True), Columna("Turno", "turno"), Columna("Cod_Frente", "frente", obligatoria=True), Columna("Lote", "lote"),
        Columna("Caja", "caja"), Columna("Tipo_Novedad", "tipo", obligatoria=True), Columna("Descripcion", "descripcion"),
        Columna("Accion_Tomada", "accion_tomada"), Columna("Responsable", "responsable"), Columna("Estado", "estado"), Columna("Fecha_Cierre", "fecha_cierre", FECHA),
    ), es_registro=True),
    Tabla("fEntregas", "Registro_Entregas", Entrega, (
        Columna("Fecha_Entrega", "fecha_entrega", FECHA, True), Columna("Cod_Frente", "frente", obligatoria=True), Columna("Lote", "lote"),
        Columna("Cantidad", "cantidad", NUMERO, True), Columna("Unidad", "unidad"), Columna("Numero_Acta", "numero_acta"),
        Columna("Estado_Entrega", "estado"), Columna("Fecha_Aceptacion", "fecha_aceptacion", FECHA), Columna("Observaciones", "observaciones"),
    ), es_registro=True),
)
POR_NOMBRE = {t.nombre: t for t in TABLAS}
POR_HOJA = {t.hoja: t for t in TABLAS}


def calculadas(tabla: Tabla, fila: Any) -> dict[str, Any]:
    """Columnas que el diseño calcula (en Excel eran fórmulas)."""
    if tabla.nombre == "dMetas":
        return {"Clave": f"{fila.actividad}|{fila.turno}", "Meta_Persona": (fila.meta_turno / fila.personas_plan) if fila.personas_plan else 0}
    if tabla.nombre == "dPersonal":
        return {"Presentes_Dia": (fila.turno_a or 0) + (fila.turno_b or 0) + (fila.turno_c or 0)}
    if tabla.nombre == "dCalendario":
        f: date = fila.fecha
        return {"Anio": f.year, "Mes": f.month, "Nombre_Mes": MESES[f.month - 1], "Semana_ISO": f.isocalendar().week, "Dia_Semana": DIAS[f.weekday()]}
    return {}


def a_salida(valor: Any, tipo: str) -> Any:
    if valor is None:
        return None
    if tipo == SINO:
        return "Sí" if valor else "No"
    if tipo == FECHA and isinstance(valor, datetime):
        return valor.date().isoformat()
    if tipo == FECHA and isinstance(valor, date):
        return valor.isoformat()
    return valor


def fila_a_dict(tabla: Tabla, fila: Any) -> dict[str, Any]:
    extra = calculadas(tabla, fila)
    return {c.nombre: (extra.get(c.nombre) if c.atributo is None else a_salida(getattr(fila, c.atributo), c.tipo)) for c in tabla.columnas}
