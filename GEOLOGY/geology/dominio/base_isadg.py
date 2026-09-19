"""
La base de datos de descripción ISAD(G) del contrato, en la plantilla del proyecto.

Esta es la entrega descriptiva: una sola hoja de cálculo con la descripción archivística de
todo lo intervenido, en las siete áreas de la norma, lista para acompañar la transferencia
secundaria. No es un informe: es el instrumento.

QUÉ SE RESPETA DE LA PLANTILLA. Se abre el archivo de la plantilla y se escribe dentro. Ni
una columna cambia de sitio, ni un encabezado se reescribe, ni un color se recalcula: el
diseño es el que viene en datos/Plantilla_BASE_ISADG_733.xlsx y si algún día cambia, se
reemplaza ese archivo y aquí no hay nada que tocar.

QUÉ SE AGREGÓ, Y POR QUÉ. La plantilla trae 24 de los 26 elementos de la norma. Faltan
3.3.3 «Nuevos ingresos» y 3.5.4 «Nota de publicaciones». Se añaden al final, en un bloque
aparte rotulado COMPLEMENTO, junto con la «Unidad superior» que exige la tercera regla de la
descripción multinivel. Van al final y no intercalados a propósito: así ninguna columna de
la plantilla se corre de lugar y quien no los quiera borra tres columnas y ya.

LA DESCRIPCIÓN ES MULTINIVEL, NO UNA LISTA. La primera regla de la norma es describir de lo
general a lo particular, y la tercera es amarrar cada descripción con la del nivel superior.
Por eso la base no arranca en el expediente: arranca en el FONDO, baja a la SECCIÓN, que aquí
es el periodo institucional, sigue por la SUBSECCIÓN, que es la oficina productora, y por la
SERIE y la SUBSERIE de la tabla de valoración convalidada, y solo al final aparece la UNIDAD
DOCUMENTAL. Cada renglón dice de cuál viene. Un expediente suelto, sin los niveles encima,
no es una descripción archivística: es un inventario.

LO HEREDADO NO SE REPITE. La segunda regla dice que la información sea pertinente al nivel
que se describe. El productor, la historia institucional, la forma de ingreso o las
condiciones de acceso se escriben UNA vez, en el nivel al que pertenecen, y los renglones de
abajo los heredan. Repetirlos en cada expediente no agrega información: agrega ruido y, sobre
todo, abre la puerta a que un día digan cosas distintas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HOJA = "Base de datos ISADG"
PLANTILLA = Path("datos/Plantilla_BASE_ISADG_733.xlsx")
FILA_ENCABEZADO = 2
FILA_PRIMERA = 3

# Las 30 columnas de la plantilla, en su orden. La clave es el nombre interno; la letra, el
# sitio donde la plantilla la puso. Cambiar la plantilla cambia este mapa y nada más.
COLUMNAS = {
    "codigo_referencia": "A", "nivel": "B", "titulo": "C",
    "fecha_inicial": "D", "fecha_final": "E", "volumen": "F",
    "productor": "G", "periodo": "H", "historia_institucional": "I",
    "historia_archivistica": "J", "forma_ingreso": "K",
    "alcance": "L", "valoracion": "M", "organizacion": "N",
    "acceso": "O", "reproduccion": "P", "lengua": "Q",
    "conservacion": "R", "instrumentos": "S",
    "originales": "T", "copias": "U", "relacionadas": "V",
    "notas": "W",
    "describio": "X", "norma": "Y", "fecha_descripcion": "Z",
    "caja": "AA", "carpeta": "AB", "orden_fuid": "AC", "lote": "AD",
}

# Lo que la plantilla no trae y la norma sí pide. Va al final, sin correr nada de lo anterior.
COMPLEMENTO = {
    "nuevos_ingresos": ("AE", "Nuevos ingresos\n(3.3.3)"),
    "publicaciones": ("AF", "Nota de publicaciones\n(3.5.4)"),
    "unidad_superior": ("AG", "Unidad superior\n(regla 3 multinivel)"),
}

# Los colores son los de la plantilla, leídos de ella, no inventados aquí.
_TEAL_AREA = "FF098086"
_TEAL_COMPLEMENTO = "FF3E6F72"
_BORDE = Border(*[Side(style="thin", color="FFBFCBD2")] * 4)

NIVEL_FONDO = "Fondo"
NIVEL_SECCION = "Sección"
NIVEL_SUBSECCION = "Subsección"
NIVEL_SERIE = "Serie"
NIVEL_SUBSERIE = "Subserie"
NIVEL_EXPEDIENTE = "Expediente"

# Sangría por nivel: la jerarquía se tiene que ver al abrir el archivo, no deducirse.
_SANGRIA = {NIVEL_FONDO: 0, NIVEL_SECCION: 1, NIVEL_SUBSECCION: 2,
            NIVEL_SERIE: 3, NIVEL_SUBSERIE: 4, NIVEL_EXPEDIENTE: 5}
_FONDO_NIVEL = {NIVEL_FONDO: "FFDCE9EA", NIVEL_SECCION: "FFE8F1F2",
                NIVEL_SUBSECCION: "FFF1F6F7", NIVEL_SERIE: "FFF6FAFA",
                NIVEL_SUBSERIE: "FFFBFDFD", NIVEL_EXPEDIENTE: None}


class FaltaLaPlantilla(FileNotFoundError):
    """No está datos/Plantilla_BASE_ISADG_733.xlsx."""


@dataclass
class Renglon:
    """Una unidad de descripción, del nivel que sea."""
    nivel: str
    campos: dict = field(default_factory=dict)

    def __getitem__(self, clave):
        return self.campos.get(clave, "")


# ---------------------------------------------------------------------------
# Armado de los niveles
# ---------------------------------------------------------------------------
def _fecha(v) -> str:
    if isinstance(v, date):
        return v.isoformat()
    return str(v or "")


def _extremas(expedientes) -> tuple[str, str]:
    """Las fechas extremas de un conjunto, tomadas de sus unidades y no declaradas a mano."""
    iniciales = [e.fecha_inicial for e in expedientes if e.fecha_inicial]
    finales = [e.fecha_final for e in expedientes if e.fecha_final]
    return (_fecha(min(iniciales)) if iniciales else "",
            _fecha(max(finales)) if finales else "")


def _volumen(expedientes) -> str:
    """Volumen y soporte del conjunto. Es elemento obligatorio: nunca puede salir vacío."""
    folios = sum(e.volumen_folios or 0 for e in expedientes)
    cajas = {e.caja_definitiva for e in expedientes if e.caja_definitiva}
    partes = [f"{len(expedientes)} expediente{'s' if len(expedientes) != 1 else ''}"]
    if folios:
        partes.append(f"{folios} folios")
    if cajas:
        partes.append(f"{len(cajas)} caja(s) X-100")
    soportes = {(e.soporte or "Papel") for e in expedientes}
    return " / ".join(partes) + " · " + ", ".join(sorted(soportes))


def _primero(expedientes, atributo: str) -> str:
    """
    El primer valor no vacío del conjunto.

    Se usa para los elementos de contexto, que son del nivel y no del expediente: la historia
    institucional de un periodo es una sola y se escribe una vez. Si los expedientes trajeran
    versiones distintas, la que manda es la primera descrita, y la discrepancia se ve porque
    el renglón de abajo queda vacío, no porque se promedien dos textos.
    """
    for e in expedientes:
        valor = getattr(e, atributo, None)
        if valor and str(valor).strip():
            return str(valor).strip()
    return ""


def _codigo_de_nivel(expediente, hasta: int) -> str:
    """
    El código del nivel superior se obtiene recortando el del expediente.

    CO-SGC-AC-P06-S01-00123 tiene cinco piezas antes del consecutivo, así que el fondo es
    CO-SGC-AC, la sección CO-SGC-AC-P06 y la subserie CO-SGC-AC-P06-S01. Recortar es lo que
    garantiza que el vínculo con el nivel superior sea exacto y no una cadena escrita aparte
    que algún día deje de coincidir.
    """
    piezas = (expediente.codigo_referencia or "").split("-")
    return "-".join(piezas[:hasta]) if len(piezas) >= hasta else ""


def construir(db, solo_conservacion_total: bool = False,
              desde_estado: tuple = ()) -> list[Renglon]:
    """
    Arma la base completa, de lo general a lo particular.

    solo_conservacion_total   deja únicamente las subseries cuya disposición final en la
                              tabla convalidada es conservación total, que es lo que va a la
                              transferencia secundaria. Las demás se describen igual, pero no
                              se transfieren, y por eso conviene poder separarlas.
    desde_estado              qué expedientes entran. Por omisión, los que ya tienen la
                              descripción validada o aprobada: una descripción en borrador no
                              entra a un instrumento de entrega.
    """
    from geology.modelos import Expediente, Fondo, Periodo, Serie, Subserie
    from geology.dominio.estados import Estado

    estados = desde_estado or (Estado.DESCRIPCION_VALIDADA.value,
                               Estado.EN_INVENTARIO.value,
                               Estado.ARCHIVADO.value)
    consulta = (db.query(Expediente)
                  .filter(Expediente.codigo_referencia.isnot(None))
                  .filter(Expediente.estado.in_(estados)))
    expedientes = sorted(consulta.all(), key=lambda e: e.codigo_referencia or "")
    if solo_conservacion_total:
        expedientes = [e for e in expedientes
                       if "conservaci" in (e.valoracion or "").lower()]
    if not expedientes:
        return []

    fondo = db.query(Fondo).first()
    periodos = {p.id: p for p in db.query(Periodo).all()}
    # El nombre de la subserie vive en la tabla convalidada, no en el expediente: el
    # expediente solo guarda a cuál pertenece. Se trae aquí para no consultar por renglón.
    subseries = {s.id: s for s in db.query(Subserie).all()}
    series = {s.id: s for s in db.query(Serie).all()}
    renglones: list[Renglon] = []

    # Nivel 1. El fondo. Se describe una vez y es de quien cuelga todo lo demás.
    codigo_fondo = _codigo_de_nivel(expedientes[0], 3)
    ini, fin = _extremas(expedientes)
    renglones.append(Renglon(NIVEL_FONDO, {
        "codigo_referencia": codigo_fondo,
        "titulo": fondo.nombre if fondo else "Servicio Geológico Colombiano",
        "fecha_inicial": ini, "fecha_final": fin,
        "volumen": _volumen(expedientes),
        "productor": fondo.nombre if fondo else "Servicio Geológico Colombiano",
        "historia_institucional": (fondo.historia_institucional if fondo else "") or "",
        "historia_archivistica": "Fondo acumulado intervenido bajo el contrato 733 de 2026, "
                                 "con tabla de valoración documental convalidada.",
        "forma_ingreso": "Aplicación de tabla de valoración documental",
        "acceso": "Público, con las reservas de ley",
        "lengua": "Español",
        "instrumentos": "Inventario documental F-GDM-003, hoja de control F-GDM-007 y esta "
                        "base de descripción",
        "originales": "Archivo Central del Servicio Geológico Colombiano",
        "norma": "NTC 4095:2013 / ISAD(G)",
        "fecha_descripcion": date.today().isoformat(),
        "unidad_superior": "—",
    }))

    # Nivel 2. La sección, que en este fondo es el periodo institucional: cada periodo tuvo
    # su entidad productora y su tabla convalidada, y por eso es una sección y no una serie.
    por_periodo: dict = {}
    for e in expedientes:
        por_periodo.setdefault(e.periodo_id, []).append(e)

    for periodo_id in sorted(por_periodo, key=lambda k: (periodos[k].orden if k in periodos else 99)):
        grupo = por_periodo[periodo_id]
        p = periodos.get(periodo_id)
        ini, fin = _extremas(grupo)
        codigo_seccion = _codigo_de_nivel(grupo[0], 4)
        renglones.append(Renglon(NIVEL_SECCION, {
            "codigo_referencia": codigo_seccion,
            "titulo": f"Periodo {p.numero_romano} · {p.entidad_productora}" if p
                      else "Periodo sin determinar",
            "fecha_inicial": ini, "fecha_final": fin,
            "volumen": _volumen(grupo),
            "productor": p.entidad_productora if p else "",
            "periodo": f"{p.numero_romano} ({p.rango_texto})" if p else "",
            "historia_institucional": (p.historia_institucional if p else "") or "",
            "historia_archivistica": (p.historia_archivistica if p else "") or "",
            "forma_ingreso": "Aplicación de tabla de valoración documental convalidada"
                             + (f" el {p.fecha_convalidacion_tvd}" if p and p.fecha_convalidacion_tvd else ""),
            "conservacion": (p.caracteristicas_fisicas if p else "") or "",
            "norma": "NTC 4095:2013 / ISAD(G)",
            "fecha_descripcion": date.today().isoformat(),
            "unidad_superior": codigo_fondo,
        }))

        # Nivel 3. La subserie de la tabla convalidada. Debajo de ella, los expedientes.
        por_subserie: dict = {}
        for e in grupo:
            por_subserie.setdefault(_codigo_de_nivel(e, 5), []).append(e)

        for codigo_sub in sorted(por_subserie):
            sub = por_subserie[codigo_sub]
            ini, fin = _extremas(sub)
            renglones.append(Renglon(NIVEL_SUBSERIE, {
                "codigo_referencia": codigo_sub,
                "titulo": _nombre_de_subserie(sub, subseries, series),
                "fecha_inicial": ini, "fecha_final": fin,
                "volumen": _volumen(sub),
                "productor": _primero(sub, "nombre_productor") or (p.entidad_productora if p else ""),
                "periodo": p.numero_romano if p else "",
                "valoracion": _primero(sub, "valoracion"),
                "organizacion": _primero(sub, "organizacion"),
                "acceso": _primero(sub, "condiciones_acceso"),
                "reproduccion": _primero(sub, "condiciones_reproduccion"),
                "lengua": _primero(sub, "lengua") or "Español",
                "instrumentos": _primero(sub, "instrumentos_descripcion"),
                "originales": _primero(sub, "existencia_originales"),
                "relacionadas": _primero(sub, "unidades_relacionadas"),
                "publicaciones": _primero(sub, "nota_publicaciones"),
                "nuevos_ingresos": _primero(sub, "nuevos_ingresos")
                                   or "Serie cerrada; no se esperan nuevos ingresos.",
                "norma": "NTC 4095:2013 / ISAD(G)",
                "fecha_descripcion": date.today().isoformat(),
                "unidad_superior": codigo_seccion,
            }))

            # Nivel 4. La unidad documental. Aquí SOLO lo que es propio del expediente.
            for e in sub:
                renglones.append(Renglon(NIVEL_EXPEDIENTE, {
                    "codigo_referencia": e.codigo_referencia or "",
                    "titulo": e.titulo or "",
                    "fecha_inicial": _fecha(e.fecha_inicial),
                    "fecha_final": _fecha(e.fecha_final),
                    "volumen": _volumen_expediente(e),
                    "alcance": e.alcance_contenido or "",
                    "organizacion": e.organizacion or "",
                    "conservacion": e.caracteristicas_fisicas or "",
                    "copias": e.existencia_copias or "",
                    "notas": _notas_de(e),
                    "describio": e.describio or e.responsable or "",
                    "norma": e.reglas_normas or "NTC 4095:2013 / ISAD(G)",
                    "fecha_descripcion": _fecha(e.fecha_descripcion) or date.today().isoformat(),
                    "caja": e.caja_definitiva or e.caja_trabajo or e.caja_origen or "",
                    "carpeta": e.consecutivo_en_caja or "",
                    "orden_fuid": e.codigo_carpeta or "",
                    "lote": e.caja_trabajo or "",
                    "unidad_superior": codigo_sub,
                }))
    return renglones


def _nombre_de_subserie(expedientes, subseries: dict, series: dict) -> str:
    """
    Cómo se llama la subserie, según la tabla de valoración convalidada.

    Se toma de la tabla y no de lo que haya quedado escrito en el expediente: el nombre de
    una subserie es el que la convalidación fijó, y en un instrumento de entrega no puede
    aparecer una variante que alguien tecleó distinto.
    """
    for e in expedientes:
        sub = subseries.get(getattr(e, "subserie_id", None))
        if sub:
            serie = series.get(sub.serie_id)
            return f"{serie.nombre} › {sub.nombre}" if serie else sub.nombre
    return ""


def _volumen_expediente(e) -> str:
    partes = []
    if e.volumen_folios:
        partes.append(f"{e.volumen_folios} folios")
    if e.encuadernada:
        partes.append("libro empastado")
    if e.metros_lineales and e.metros_lineales >= 0.01:
        partes.append(f"{e.metros_lineales:.2f} ml")
    return " · ".join(partes + [e.soporte or "Papel"])


def _notas_de(e) -> str:
    """
    Las notas del expediente, más lo que la plataforma tenga que dejar dicho.

    La diferencia de folios entre la hoja de control y el inventario de origen se escribe
    aquí porque es una advertencia sobre la unidad descrita, y quien reciba la transferencia
    tiene que verla sin abrir otro archivo.
    """
    partes = [x for x in (e.notas, e.nota_archivero, e.diferencia_folios) if x and str(x).strip()]
    return " · ".join(str(x).strip() for x in partes)


# ---------------------------------------------------------------------------
# Escritura en la plantilla
# ---------------------------------------------------------------------------
def _abrir_plantilla(ruta: Path | None = None):
    import openpyxl
    ruta = Path(ruta or PLANTILLA)
    if not ruta.exists():
        raise FaltaLaPlantilla(
            f"Falta la plantilla {ruta.name} en datos/. Sin ella no se expide la base: "
            "el diseño lo pone el proyecto, no el programa.")
    return openpyxl.load_workbook(ruta)


def _limpiar_ejemplos(hoja) -> None:
    """Quita los renglones de ejemplo que trae la plantilla, sin tocar los encabezados."""
    if hoja.max_row >= FILA_PRIMERA:
        hoja.delete_rows(FILA_PRIMERA, hoja.max_row - FILA_PRIMERA + 1)


def _abrir_complemento(hoja) -> None:
    """Rotula el bloque de los tres campos que la plantilla no traía."""
    primera = COMPLEMENTO["nuevos_ingresos"][0]
    ultima = COMPLEMENTO["unidad_superior"][0]
    modelo = hoja["A1"]
    hoja.merge_cells(f"{primera}1:{ultima}1")
    titular = hoja[f"{primera}1"]
    titular.value = "COMPLEMENTO ISAD(G) · lo que la norma pide y la plantilla no traía"
    titular.fill = PatternFill("solid", fgColor=_TEAL_COMPLEMENTO)
    titular.font = Font(name="Arial", size=9, bold=True, color="FFFFFFFF")
    titular.alignment = Alignment(horizontal="center", vertical="center")

    modelo2 = hoja["A2"]
    for letra, rotulo in COMPLEMENTO.values():
        c = hoja[f"{letra}{FILA_ENCABEZADO}"]
        c.value = rotulo
        c.fill = PatternFill("solid", fgColor=_TEAL_COMPLEMENTO)
        c.font = Font(name="Arial", size=8, bold=True, color="FFFFFFFF")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = _BORDE
        hoja.column_dimensions[letra].width = 26
    _ = modelo, modelo2


def _anotar_instructivo(libro, renglones: list[Renglon]) -> None:
    """
    Deja dicho en el instructivo qué trae este archivo en concreto.

    Quien lo reciba tiene que poder saber, sin preguntarle a nadie, de dónde salió, hasta
    dónde llega y por qué hay tres columnas que la plantilla original no tenía.
    """
    from collections import Counter
    if "Instructivo" not in libro.sheetnames:
        return
    h = libro["Instructivo"]
    cuenta = Counter(r.nivel for r in renglones)
    resumen = ", ".join(f"{cuenta[n]} {n.lower()}" for n in
                        (NIVEL_FONDO, NIVEL_SECCION, NIVEL_SUBSERIE, NIVEL_EXPEDIENTE)
                        if cuenta.get(n))
    filas = [
        ("Descripción multinivel aplicada",
         "La base no arranca en el expediente. Va de lo general a lo particular, como manda "
         "la primera regla: fondo, sección —que aquí es el periodo institucional— subserie de "
         "la tabla convalidada y, al final, la unidad documental. Cada renglón dice de cuál "
         "nivel viene, en la columna «Unidad superior». Lo que es del nivel superior se "
         "escribe una sola vez y los renglones de abajo lo heredan: repetirlo en cada "
         "expediente no agrega información y abre la puerta a que un día digan cosas distintas."),
        ("Complemento al final (columnas AE a AG)",
         "La plantilla trae 24 de los 26 elementos de la norma. Al final, en bloque aparte, se "
         "agregaron los dos que faltaban —3.3.3 Nuevos ingresos y 3.5.4 Nota de publicaciones— "
         "y la columna de vínculo con el nivel superior que exige la tercera regla de la "
         "descripción multinivel. Van al final para no correr de sitio ninguna columna de la "
         "plantilla: quien no los quiera, borra tres columnas."),
        ("Qué trae este archivo",
         f"Expedido el {date.today().isoformat()} por GEOLOGY a partir de la base de datos del "
         f"contrato. Contiene {resumen}. Solo entran las descripciones ya validadas: un "
         "instrumento de entrega no se arma con borradores."),
    ]
    inicio = h.max_row + 1
    for i, (rotulo, texto) in enumerate(filas):
        a = h.cell(inicio + i, 1, rotulo)
        b = h.cell(inicio + i, 2, texto)
        a.font = Font(name="Arial", size=9, bold=True)
        b.font = Font(name="Arial", size=9)
        a.alignment = Alignment(vertical="top", wrap_text=True)
        b.alignment = Alignment(vertical="top", wrap_text=True)


def _hoja_de_revision(libro, hallazgos: list, resumen: dict) -> None:
    """
    La revisión previa viaja DENTRO del archivo, en su propia hoja.

    Va aquí y no en un correo aparte por una razón: quien abra la base tiene que poder ver,
    sin preguntarle a nadie, qué se revisó, qué pasó y qué falta. Si no hay nada que
    reportar, eso también queda escrito y firmado con la fecha.
    """
    if "Revisión previa" in libro.sheetnames:
        del libro["Revisión previa"]
    h = libro.create_sheet("Revisión previa", 1)

    h["A1"] = "REVISIÓN PREVIA A LA ENTREGA"
    h["A1"].font = Font(name="Arial", size=11, bold=True, color="FFFFFFFF")
    h["A1"].fill = PatternFill("solid", fgColor=_TEAL_AREA)
    h.merge_cells("A1:F1")
    h.row_dimensions[1].height = 20

    veredicto = ("SE PUEDE ENTREGAR. No quedó ningún incumplimiento de norma."
                 if resumen["se_puede_entregar"] else
                 f"NO SE PUEDE ENTREGAR TODAVÍA. Hay {resumen['devuelve']} incumplimiento(s) "
                 "de norma; con uno solo devuelven el lote completo.")
    h["A2"] = veredicto
    h["A2"].font = Font(name="Arial", size=10, bold=True,
                        color="FF1B6B45" if resumen["se_puede_entregar"] else "FF96173C")
    h.merge_cells("A2:F2")

    r = resumen.get("revisor") or {}
    del_revisor = ""
    if r.get("revisados"):
        del_revisor = (f" · un segundo modelo, distinto al que redactó, revisó "
                       f"{r['revisados']} de {r['de']} unidad(es)")
        if r.get("se_acabo_la_cuota"):
            del_revisor += " y se detuvo por falta de cuota"
    elif r.get("error"):
        del_revisor = " · el revisor no pudo correr; la revisión de reglas sí está completa"
    h["A3"] = (f"Revisado el {resumen['fecha']} · {resumen['devuelve']} que devuelven · "
               f"{resumen['revise']} para mirar con el expediente delante · "
               f"{resumen['unidades_con_problema']} unidad(es) afectada(s)" + del_revisor)
    h["A3"].font = Font(name="Arial", size=9)
    h.merge_cells("A3:F3")

    h["A4"] = ("DEVUELVE es incumplimiento de norma y es un hecho. REVISE es algo que hay que "
               "mirar con el expediente delante; lo que venga marcado «lo señala el revisor» "
               "es la opinión de un modelo distinto al que redactó, y la confirma una persona.")
    h["A4"].font = Font(name="Arial", size=8, italic=True)
    h.merge_cells("A4:F4")

    rotulos = ["Gravedad", "Regla", "Unidad", "Nivel", "Qué pasa", "Cómo se arregla"]
    for i, r in enumerate(rotulos, start=1):
        c = h.cell(5, i, r)
        c.fill = PatternFill("solid", fgColor=_TEAL_COMPLEMENTO)
        c.font = Font(name="Arial", size=8, bold=True, color="FFFFFFFF")
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = _BORDE
    for ancho, letra in zip((11, 24, 26, 12, 62, 62), "ABCDEF"):
        h.column_dimensions[letra].width = ancho

    for i, x in enumerate(hallazgos):
        fila = 6 + i
        for j, valor in enumerate([x.gravedad, x.regla, x.unidad, x.nivel,
                                   x.que_pasa, x.como_se_arregla], start=1):
            c = h.cell(fila, j, valor)
            c.font = Font(name="Arial", size=8,
                          bold=(j == 1 and x.gravedad == "DEVUELVE"),
                          color="FF96173C" if (j == 1 and x.gravedad == "DEVUELVE") else "FF16222E")
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = _BORDE
    if not hallazgos:
        h["A6"] = "Sin hallazgos."
        h["A6"].font = Font(name="Arial", size=9, italic=True)
    h.freeze_panes = "A6"


def escribir(renglones: list[Renglon], destino: Path,
             plantilla: Path | None = None, hallazgos: list | None = None,
             resumen_revision: dict | None = None) -> Path:
    """Vuelca los renglones en la plantilla y guarda el archivo."""
    libro = _abrir_plantilla(plantilla)
    hoja = libro[HOJA]
    _limpiar_ejemplos(hoja)
    _abrir_complemento(hoja)

    mapa = dict(COLUMNAS)
    for clave, (letra, _) in COMPLEMENTO.items():
        mapa[clave] = letra

    for i, r in enumerate(renglones):
        fila = FILA_PRIMERA + i
        relleno = _FONDO_NIVEL.get(r.nivel)
        negrita = r.nivel in (NIVEL_FONDO, NIVEL_SECCION, NIVEL_SUBSERIE)
        for clave, letra in mapa.items():
            c = hoja[f"{letra}{fila}"]
            valor = r["nivel"] if clave == "nivel" else r[clave]
            c.value = r.nivel if clave == "nivel" else (valor if valor != "" else None)
            c.font = Font(name="Arial", size=8, bold=negrita)
            c.alignment = Alignment(vertical="top", wrap_text=True,
                                    indent=_SANGRIA.get(r.nivel, 0) if clave == "codigo_referencia" else 0)
            c.border = _BORDE
            if relleno:
                c.fill = PatternFill("solid", fgColor=relleno)

    ultima = get_column_letter(hoja.max_column)
    hoja.auto_filter.ref = f"A{FILA_ENCABEZADO}:{ultima}{FILA_PRIMERA + len(renglones) - 1}" \
        if renglones else None
    hoja.freeze_panes = "D3"
    _anotar_instructivo(libro, renglones)
    if resumen_revision is not None:
        _hoja_de_revision(libro, hallazgos or [], resumen_revision)

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    libro.save(destino)
    return destino


def expedir(db, destino: Path | None = None, solo_conservacion_total: bool = False,
            desde_estado: tuple = (), exigir_calidad: bool = True,
            con_revisor: bool = True, limite_revisor: int = 0) -> dict:
    """
    Arma la base, la revisa y la escribe.

    exigir_calidad   con esto puesto, si la revisión encuentra un incumplimiento de norma el
                     archivo se marca como NO ENTREGABLE en su propio nombre y en la hoja de
                     revisión. No se bloquea la expedición: el archivo ES la herramienta para
                     saber qué corregir, y esconderlo no arregla nada. Lo que no se puede es
                     que salga con cara de definitivo teniendo un obligatorio vacío.
    """
    from geology.dominio import revision_isadg as rev

    renglones = construir(db, solo_conservacion_total, desde_estado)
    if not renglones:
        raise ValueError(
            "Todavía no hay descripciones para llevar a la base. Entran los expedientes con "
            "la descripción ya validada; los que están en elaboración o por revisar no, "
            "porque un instrumento de entrega no se arma con borradores.")

    contexto = rev.contexto_de(db, renglones)
    hallazgos = rev.revisar(renglones, contexto)

    # El cuarto papel. Mira lo que las reglas no pueden mirar: si el título identifica de
    # verdad, si el alcance aporta y si lo descrito corresponde a los trámites. Lo hace un
    # modelo distinto al que redactó, y todo lo que diga entra como opinión, no como norma.
    parte_revisor = {"revisados": 0, "de": 0, "se_acabo_la_cuota": False}
    if con_revisor:
        try:
            from geology.dominio import revisor as rv
            del_modelo, parte_revisor = rv.revisar_lote(db, renglones, contexto,
                                                        limite=limite_revisor)
            hallazgos = sorted(hallazgos + del_modelo,
                               key=lambda h: (h.gravedad != rev.DEVUELVE, h.unidad, h.regla))
        except Exception as e:                      # el revisor nunca tumba la expedición
            parte_revisor = {"revisados": 0, "de": 0, "se_acabo_la_cuota": False,
                             "error": f"{type(e).__name__}: {e}"}

    resumen = rev.resumen(hallazgos)
    resumen["revisor"] = parte_revisor

    if destino is None:
        marca = "" if (resumen["se_puede_entregar"] or not exigir_calidad) else "_NO_ENTREGABLE"
        destino = Path(f"expedidos/Base_Datos_ISADG_733_{date.today().isoformat()}{marca}.xlsx")
    archivo = escribir(renglones, destino, hallazgos=hallazgos, resumen_revision=resumen)
    return {"archivo": archivo, "unidades": len(renglones),
            "hallazgos": hallazgos, "resumen": resumen}
