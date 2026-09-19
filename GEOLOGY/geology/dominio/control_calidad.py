"""
Control de calidad de lo que produce la plataforma.

No basta con que el modelo y el equipo llenen las hojas: hay que revisar lo hecho y poder
demostrarle al Servicio Geológico Colombiano que se revisó. Este módulo pasa por encima de
todo lo cargado y devuelve una lista de hallazgos, cada uno con la carpeta, la gravedad, la
prueba que falló y qué hacer. No corrige nada por su cuenta: señala.

Las pruebas salen de las reglas del contrato y de los principios de procedencia y orden
original (Acuerdos 004 y 005 de 2013 y 002 de 2014 del Archivo General de la Nación).

Gravedades:
    error     no debería pasar a la siguiente etapa así
    revisar   hay que mirarlo, puede estar bien
    aviso     queda constancia, no detiene nada
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

ERROR = "error"
REVISAR = "revisar"
AVISO = "aviso"

# Tipos documentales que por sí solos no le dicen nada a quien consulta el archivo histórico.
GENERICOS = {
    "OFICIO", "CARTA", "MEMORANDO", "COMUNICACION", "COMUNICACIÓN", "DOCUMENTO", "INFORME",
    "ACTA", "CIRCULAR", "RESOLUCION", "RESOLUCIÓN", "SOLICITUD", "RESPUESTA", "ANEXO",
    "PLANILLA", "FORMATO", "CONSTANCIA", "CERTIFICADO", "NOTA", "TELEGRAMA", "FACTURA",
}


@dataclass(frozen=True)
class Hallazgo:
    carpeta: str
    gravedad: str
    prueba: str
    mensaje: str
    donde: str = ""

    def como_dict(self) -> dict:
        return {"carpeta": self.carpeta, "gravedad": self.gravedad, "prueba": self.prueba,
                "mensaje": self.mensaje, "donde": self.donde}


@dataclass
class Informe:
    hallazgos: list[Hallazgo] = field(default_factory=list)
    revisados: int = 0

    def anotar(self, carpeta, gravedad, prueba, mensaje, donde=""):
        self.hallazgos.append(Hallazgo(carpeta, gravedad, prueba, mensaje, donde))

    @property
    def errores(self) -> int:
        return sum(1 for h in self.hallazgos if h.gravedad == ERROR)

    @property
    def por_revisar(self) -> int:
        return sum(1 for h in self.hallazgos if h.gravedad == REVISAR)

    def resumen(self) -> dict:
        conteo: dict[str, int] = {}
        for h in self.hallazgos:
            conteo[h.prueba] = conteo.get(h.prueba, 0) + 1
        return {"expedientes_revisados": self.revisados, "hallazgos": len(self.hallazgos),
                "errores": self.errores, "por_revisar": self.por_revisar,
                "por_prueba": dict(sorted(conteo.items(), key=lambda x: -x[1]))}


# ---------------------------------------------------------------------------
# Pruebas sobre un expediente
# ---------------------------------------------------------------------------

def revisar_expediente(db, exp, unidad, periodo, subserie_periodo_romano: str | None,
                       informe: Informe) -> None:
    """Todas las pruebas que se pueden hacer sobre un expediente y sus trámites."""
    from geology.dominio.estados import Estado
    from geology.dominio.folios import Tramite as TramiteCalculo, verificar_folios

    carpeta = exp.codigo_carpeta
    estado = exp.estado or ""
    ya_descrito = estado in (Estado.DESCRIPCION_POR_VALIDAR.value,
                             Estado.DESCRIPCION_VALIDADA.value,
                             Estado.ARCHIVADO.value, Estado.EN_INVENTARIO.value)

    # 1. Periodo
    romano = periodo.numero_romano if periodo else ""
    inv = (unidad.periodo or "").strip().upper() if unidad else ""
    if not romano:
        informe.anotar(carpeta, ERROR, "sin_periodo",
                       "El expediente no tiene periodo asignado.",
                       "Editor del expediente, casilla de periodo.")
    elif inv and inv not in ("S/F", "SF", "N/A", "SP") and inv != romano:
        if exp.periodo_fijado_a_mano:
            informe.anotar(carpeta, AVISO, "periodo_fijado_a_mano",
                           f"Periodo {romano} fijado a mano; el inventario de origen decía {inv}.",
                           "Bitácora del expediente.")
        else:
            informe.anotar(
                carpeta, REVISAR, "periodo_distinto_al_inventario",
                f"Las fechas del documento lo ubican en el periodo {romano} y el inventario de "
                f"origen decía {inv}. Manda la fecha, así que quedó en el {romano}. Confirme "
                "que las fechas leídas son correctas.",
                "Hoja de control, columna de fecha; y casilla de periodo.")

    # 2. Fechas extremas contra el rango del periodo
    if periodo and exp.fecha_inicial:
        if periodo.fecha_inicio and exp.fecha_inicial < periodo.fecha_inicio:
            informe.anotar(
                carpeta, ERROR, "fecha_fuera_del_periodo",
                f"La fecha inicial {exp.fecha_inicial.isoformat()} es anterior al comienzo del "
                f"periodo {romano} ({periodo.rango_texto}).",
                "Hoja de control, primer trámite.")
        if periodo.fecha_fin and exp.fecha_final and exp.fecha_final > periodo.fecha_fin:
            informe.anotar(
                carpeta, REVISAR, "fechas_cruzan_periodo",
                f"La fecha final {exp.fecha_final.isoformat()} sobrepasa el periodo {romano} "
                f"({periodo.rango_texto}). Puede ser un libro empastado que cruza periodos; "
                "verifíquelo y déjelo escrito en las notas.",
                "Hoja de control, último trámite.")

    # Fechas de trámite que se salen del periodo. Cuando el expediente tiene otras fechas
    # buenas, esas quedan fuera de las fechas extremas y el error se volvería invisible: aquí
    # es donde tiene que aparecer para que alguien vaya a mirar el folio.
    if periodo and (periodo.fecha_inicio or periodo.fecha_fin):
        from geology.dominio.fechas import HOLGURA_ANIOS_PERIODO
        desde = (periodo.fecha_inicio.replace(year=periodo.fecha_inicio.year - HOLGURA_ANIOS_PERIODO)
                 if periodo.fecha_inicio else None)
        hasta = (periodo.fecha_fin.replace(year=periodo.fecha_fin.year + HOLGURA_ANIOS_PERIODO)
                 if periodo.fecha_fin else None)
        fuera = [t for t in exp.tramites if t.fecha
                 and ((desde and t.fecha < desde) or (hasta and t.fecha > hasta))]
        if fuera and len(fuera) < len(exp.tramites):
            cuales = ", ".join(f"{t.no_item} ({t.fecha.isoformat()})" for t in fuera[:6])
            informe.anotar(
                carpeta, REVISAR, "tramite_con_fecha_fuera_del_periodo",
                f"{len(fuera)} trámite(s) tienen fecha fuera del periodo {romano} y por eso "
                f"quedaron fuera de las fechas extremas: {cuales}"
                f"{'…' if len(fuera) > 6 else ''}. Suele ser un año mal transcrito.",
                "Hoja de control, columna fecha de esos trámites.")

    # Fechas en desorden dentro de la hoja. En una carpeta suelta que se organizó
    # cronológicamente no debería pasar, así que o la hoja se diligenció sin ordenar o la
    # unidad es un libro empastado. Las dos hay que mirarlas, y la decisión es de una persona.
    from geology.dominio.libros import encuadernacion, fechas_desordenadas
    enc = encuadernacion(unidad, getattr(exp, "encuadernada", None))
    desordenados = fechas_desordenadas(exp.tramites)
    if desordenados and not enc.es_libro:
        cuales = ", ".join(str(t.no_item) for t in desordenados[:6])
        informe.anotar(
            carpeta, REVISAR, "fechas_en_desorden",
            f"{len(desordenados)} trámite(s) traen una fecha anterior a la del trámite que "
            f"los precede ({cuales}{'…' if len(desordenados) > 6 else ''}). O la hoja se "
            "diligenció sin ordenar, o es un libro empastado que no se puede reordenar.",
            "Hoja de control; y el botón de libro empastado en la ficha.")
    if enc.es_libro and not enc.confirmada:
        informe.anotar(
            carpeta, REVISAR, "libro_por_confirmar",
            f"El inventario de origen dice «{enc.evidencia}», así que se tomó como libro "
            "empastado y las fechas extremas se leyeron por el primer y el último folio. "
            "Confírmelo o niéguelo en la ficha del expediente.",
            "Ficha del expediente, botón de libro empastado.")

    hoy = date.today()
    for t in exp.tramites:
        if t.fecha and t.fecha > hoy:
            informe.anotar(carpeta, ERROR, "fecha_futura",
                           f"El trámite {t.no_item} tiene fecha {t.fecha.isoformat()}, posterior "
                           "a hoy. Es un error de transcripción del año.",
                           f"Hoja de control, trámite {t.no_item}, columna fecha.")

    # 3. Subserie
    if not exp.subserie_id and ya_descrito:
        informe.anotar(carpeta, ERROR, "sin_subserie",
                       "El expediente está descrito pero no tiene subserie asignada.",
                       "Editor del expediente, casilla de subserie.")
    if exp.subserie_id and romano and subserie_periodo_romano and subserie_periodo_romano != romano:
        informe.anotar(
            carpeta, ERROR, "subserie_de_otro_periodo",
            f"La subserie asignada pertenece a la tabla de valoración del periodo "
            f"{subserie_periodo_romano} y el expediente quedó en el {romano}. La clasificación "
            "tiene que salir de la tabla del periodo del expediente.",
            "Editor del expediente, casilla de subserie.")

    # 3.b Recepción técnica de lo digitalizado. La resolución es de captura: si entró por
    #     debajo del mínimo hay que volver a escanear, y eso tiene que verse antes de que el
    #     expediente avance, no cuando se entregue.
    from geology.modelos import Archivo
    from geology.dominio.recepcion_tecnica import UMBRAL_DPI
    for a in db.query(Archivo).filter(Archivo.codigo_carpeta == carpeta).all() if db else []:
        # Solo se reclama la resolución cuando se está exigiendo un mínimo. Con UMBRAL_DPI en
        # cero lo cargado es material de trabajo para agilizar la hoja de control, no la
        # digitalización de preservación, y pedirle parámetros de preservación estorba.
        if UMBRAL_DPI > 0 and a.dpi_minimo and a.dpi_minimo < UMBRAL_DPI:
            informe.anotar(
                carpeta, ERROR, "resolucion_insuficiente",
                f"«{a.nombre_original}» está a {a.dpi_minimo} puntos por pulgada y el mínimo "
                f"exigido es {UMBRAL_DPI}. Hay que volver a escanear el expediente: la "
                "resolución no se puede subir después, solo se captura.",
                "Digitalización; vuelva a cargarlo en la pestaña Cargue.")
        if a.error_proceso:
            informe.anotar(carpeta, AVISO, "preservacion_incompleta",
                           f"«{a.nombre_original}»: {a.error_proceso[:180]}",
                           "Preparación de la matriz de preservación.")

    # 4. Folios
    if exp.tramites:
        # verificar_folios lee lo que venía escrito en la celda; aquí los folios ya están
        # guardados como números, así que se le entregan también en su forma de texto.
        calculo = [TramiteCalculo(
            no_item=t.no_item, tipo_documental=t.tipo_documental or "",
            folio_desde=t.folio_desde, folio_hasta=t.folio_hasta,
            folio_desde_leido="" if t.folio_desde is None else str(t.folio_desde),
            folio_hasta_leido="" if t.folio_hasta is None else str(t.folio_hasta))
            for t in exp.tramites]
        r = verificar_folios(calculo, unidad.folios if unidad else None)
        for e in r.errores:
            informe.anotar(carpeta, ERROR, "folios", e, "Hoja de control, columnas de folios.")
        if unidad and unidad.folios and r.total_folios and r.total_folios != unidad.folios:
            informe.anotar(
                carpeta, REVISAR, "folios_vs_inventario",
                f"La hoja suma {r.total_folios} folios y el inventario de origen dice "
                f"{unidad.folios}. Cuente el expediente físico antes de aprobar.",
                "Hoja de control y expediente físico.")

    # 5. Tipos documentales. Esto es archivo histórico: la hoja de control es el instrumento
    #    de consulta, y un tipo documental suelto no le sirve a quien busca.
    genericos = [t.no_item for t in exp.tramites
                 if (t.tipo_documental or "").strip().upper().rstrip(".") in GENERICOS]
    if genericos:
        muestra = ", ".join(str(n) for n in genericos[:8])
        informe.anotar(
            carpeta, REVISAR, "tipo_documental_generico",
            f"{len(genericos)} trámite(s) tienen un tipo documental sin asunto (trámites "
            f"{muestra}{'…' if len(genericos) > 8 else ''}). Debe decir de qué trata el trámite, "
            "no solo qué clase de papel es.",
            "Hoja de control, columna tipo documental.")
    vacios = [t.no_item for t in exp.tramites if not (t.tipo_documental or "").strip()]
    if vacios:
        informe.anotar(carpeta, ERROR, "tipo_documental_vacio",
                       f"{len(vacios)} trámite(s) sin tipo documental.",
                       "Hoja de control, columna tipo documental.")
    sin_fecha = [t.no_item for t in exp.tramites if not t.fecha and not (t.fecha_texto or "").strip()]
    if sin_fecha and len(sin_fecha) == len(exp.tramites) and exp.tramites:
        informe.anotar(carpeta, REVISAR, "expediente_sin_fechas",
                       "Ningún trámite tiene fecha. El periodo no se pudo comprobar con fechas.",
                       "Hoja de control, columna fecha.")
    elif sin_fecha:
        informe.anotar(carpeta, AVISO, "tramites_sin_fecha",
                       f"{len(sin_fecha)} trámite(s) sin fecha.",
                       "Hoja de control, columna fecha.")

    # 6. Descripción
    if ya_descrito:
        faltan = [nombre for nombre, valor in (
            ("código de referencia", exp.codigo_referencia), ("título", exp.titulo),
            ("alcance y contenido", exp.alcance_contenido),
            ("nombre del productor", exp.nombre_productor)) if not (valor or "").strip()]
        if faltan:
            informe.anotar(carpeta, ERROR, "isadg_incompleta",
                           "La descripción está aprobada o por validar y le faltan elementos "
                           "obligatorios: " + ", ".join(faltan) + ".",
                           "Pestaña de descripción ISAD(G).")
        if not exp.volumen_folios:
            informe.anotar(carpeta, ERROR, "isadg_sin_volumen",
                           "La descripción no tiene volumen en folios (elemento 3.1.5).",
                           "Pestaña de descripción ISAD(G).")

    # 7. Aprobación
    if exp.aprobo and exp.describio and exp.aprobo.strip().lower() == exp.describio.strip().lower():
        informe.anotar(carpeta, ERROR, "aprobo_quien_describio",
                       f"{exp.aprobo} describió y aprobó el mismo expediente. Nadie aprueba su "
                       "propio trabajo.",
                       "Bitácora del expediente.")


# ---------------------------------------------------------------------------
# Pruebas sobre el conjunto
# ---------------------------------------------------------------------------

def revisar_conjunto(db, informe: Informe) -> None:
    """Lo que solo se ve mirando todos los expedientes juntos."""
    from sqlalchemy import func
    from geology.modelos import Caja, Expediente, Periodo

    # Códigos de referencia repetidos. Dos expedientes no pueden tener el mismo.
    repetidos = (db.query(Expediente.codigo_referencia, func.count(Expediente.id))
                   .filter(Expediente.codigo_referencia.isnot(None),
                           Expediente.codigo_referencia != "")
                   .group_by(Expediente.codigo_referencia)
                   .having(func.count(Expediente.id) > 1).all())
    for codigo, cuantos in repetidos:
        carpetas = [c for (c,) in db.query(Expediente.codigo_carpeta)
                                     .filter(Expediente.codigo_referencia == codigo).all()]
        informe.anotar(", ".join(carpetas), ERROR, "codigo_referencia_repetido",
                       f"El código de referencia {codigo} está en {cuantos} expedientes.",
                       "Editor del expediente, código de referencia.")

    # Cajas definitivas con carpetas de más de un periodo. El sistema lo bloquea al asignar,
    # pero se comprueba igual por si algo entró antes de la regla.
    filas = (db.query(Expediente.caja_definitiva, Periodo.numero_romano,
                      func.count(Expediente.id))
               .join(Periodo, Expediente.periodo_id == Periodo.id)
               .filter(Expediente.caja_definitiva.isnot(None),
                       Expediente.caja_definitiva != "")
               .group_by(Expediente.caja_definitiva, Periodo.numero_romano).all())
    por_caja: dict[str, list[tuple[str, int]]] = {}
    for caja, romano, cuantos in filas:
        por_caja.setdefault(caja, []).append((romano, cuantos))
    for caja, periodos in por_caja.items():
        if len(periodos) > 1:
            detalle = ", ".join(f"{r} ({c} carpetas)" for r, c in sorted(periodos))
            informe.anotar(caja, ERROR, "caja_con_periodos_mezclados",
                           f"La caja {caja} tiene carpetas de {len(periodos)} periodos: {detalle}. "
                           "Una caja definitiva pertenece a un solo periodo.",
                           "Pestaña de inventario y ubicación.")

    # Cajas cerradas cuyo conteo no coincide con las carpetas realmente asignadas.
    for caja in db.query(Caja).filter(Caja.cerrada.is_(True)).all():
        reales = (db.query(func.count(Expediente.id))
                    .filter(Expediente.caja_definitiva == caja.codigo).scalar() or 0)
        if reales != caja.total_carpetas:
            informe.anotar(caja.codigo, ERROR, "caja_descuadrada",
                           f"La caja {caja.codigo} está cerrada con {caja.total_carpetas} "
                           f"carpetas pero tiene {reales} asignadas.",
                           "Pestaña de inventario y ubicación.")


def revisar_todo(db, estado: str | None = None, limite: int = 2000) -> Informe:
    """Pasa el control de calidad sobre los expedientes cargados."""
    from geology.modelos import Expediente, Periodo, Seccion, Serie, Subserie, UnidadInventario
    from geology.dominio.estados import Estado

    informe = Informe()
    consulta = db.query(Expediente).filter(Expediente.estado != Estado.RETIRADO.value)
    if estado:
        consulta = consulta.filter(Expediente.estado == estado)

    # Se resuelve de antemano a qué periodo pertenece cada subserie, para no consultar por fila.
    periodo_de_subserie = {
        su_id: romano for su_id, romano in
        db.query(Subserie.id, Periodo.numero_romano)
          .join(Serie, Subserie.serie_id == Serie.id)
          .join(Seccion, Serie.seccion_id == Seccion.id)
          .join(Periodo, Seccion.periodo_id == Periodo.id).all()}
    periodos = {p.id: p for p in db.query(Periodo).all()}

    for exp in consulta.order_by(Expediente.codigo_carpeta).limit(limite).all():
        unidad = (db.query(UnidadInventario)
                    .filter(UnidadInventario.codigo_carpeta == exp.codigo_carpeta).first())
        revisar_expediente(db, exp, unidad, periodos.get(exp.periodo_id),
                           periodo_de_subserie.get(exp.subserie_id), informe)
        informe.revisados += 1

    revisar_conjunto(db, informe)
    return informe


# ---------------------------------------------------------------------------
# Salida en Excel, para anexar a un acta o a un informe de avance
# ---------------------------------------------------------------------------

def informe_a_excel(informe: Informe, quien: str = "") -> "Path":
    from datetime import datetime
    from pathlib import Path

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    colores = {ERROR: "FFC7CE", REVISAR: "FFEB9C", AVISO: "DDEBF7"}

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Hallazgos"

    hoja["A1"] = "GEOLOGY · Control de calidad"
    hoja["A1"].font = Font(bold=True, size=14)
    hoja["A2"] = (f"Generado el {datetime.now():%Y-%m-%d %H:%M}"
                  + (f" por {quien}" if quien else ""))
    hoja["A3"] = (f"{informe.revisados} expedientes revisados · {informe.errores} errores · "
                  f"{informe.por_revisar} por revisar · {len(informe.hallazgos)} hallazgos")

    encabezados = ["Carpeta", "Gravedad", "Prueba", "Qué pasa", "Dónde se corrige"]
    for col, texto in enumerate(encabezados, start=1):
        celda = hoja.cell(row=5, column=col, value=texto)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="44546A")

    orden = {ERROR: 0, REVISAR: 1, AVISO: 2}
    for fila, h in enumerate(sorted(informe.hallazgos,
                                    key=lambda x: (orden.get(x.gravedad, 9), x.prueba, x.carpeta)),
                             start=6):
        for col, texto in enumerate([h.carpeta, h.gravedad, h.prueba, h.mensaje, h.donde], start=1):
            celda = hoja.cell(row=fila, column=col, value=texto)
            celda.alignment = Alignment(vertical="top", wrap_text=(col >= 4))
            celda.fill = PatternFill("solid", fgColor=colores.get(h.gravedad, "FFFFFF"))

    for col, ancho in zip("ABCDE", (18, 12, 30, 80, 40)):
        hoja.column_dimensions[col].width = ancho
    hoja.freeze_panes = "A6"

    resumen = libro.create_sheet("Resumen por prueba")
    resumen.append(["Prueba", "Cuántas veces"])
    resumen["A1"].font = resumen["B1"].font = Font(bold=True)
    for prueba, cuantos in informe.resumen()["por_prueba"].items():
        resumen.append([prueba, cuantos])
    resumen.column_dimensions["A"].width = 40
    resumen.column_dimensions["B"].width = 16

    salida = Path("deposito") / "informes"
    salida.mkdir(parents=True, exist_ok=True)
    ruta = salida / f"GEOLOGY_calidad_{datetime.now():%Y%m%d_%H%M}.xlsx"
    libro.save(ruta)
    return ruta
