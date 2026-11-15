"""Informe de avance para la interventoría (D-47): lo arma ARCA con lo que ya sabe, para un periodo, en Excel o PDF.

Secciones: el proyecto y el periodo; el avance por frente (tablero de productividad a la fecha de corte); la
digitalización (imágenes recibidas, aprobadas y rechazadas; páginas leídas con OCR); el alistamiento físico y el
diagnóstico de conservación; las hojas de control verificadas; la inspección de calidad por lote; las historias
laborales (si el proyecto lo es); las entregas (paquetes y PDF/A); las novedades abiertas; y la evidencia (la
verificación de la cadena de auditoría y cuántos eventos hubo en el periodo).

Todo sale de los datos, no se escribe a mano: el mismo informe para el mismo periodo da los mismos números.
"""

import io
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from arca.modelos import (
    DiagnosticoExpediente,
    EventoAuditoria,
    HojaControl,
    InspeccionLote,
    IntervencionExpediente,
    Novedad,
    PaqueteEntrega,
    PlanAlistamiento,
    Proyecto,
    RecursoDigital,
    TextoPagina,
    UnidadDocumental,
)
from arca.nucleo.errores import DatosInvalidos


def _rango(ctx, desde: date, hasta: date) -> tuple[datetime, datetime]:
    zona = ZoneInfo(ctx.organizacion.zona_horaria)
    return datetime.combine(desde, time.min, zona), datetime.combine(hasta + timedelta(days=1), time.min, zona)


def _cuenta(ctx, modelo, *condiciones) -> int:
    return int(ctx.db.scalar(select(func.count()).select_from(modelo).where(*condiciones)) or 0)


def datos(ctx, proyecto: Proyecto, desde: date, hasta: date) -> dict[str, Any]:
    if hasta < desde:
        raise DatosInvalidos("La fecha final del periodo es anterior a la inicial")
    if (hasta - desde).days > 400:
        raise DatosInvalidos("El periodo del informe es de máximo 400 días")
    a, b = _rango(ctx, desde, hasta)
    pid = proyecto.id
    secciones: list[dict[str, Any]] = []
    total_unidades = _cuenta(ctx, UnidadDocumental, UnidadDocumental.proyecto_id == pid)
    secciones.append({"titulo": "Proyecto y periodo", "tabla": [
        ["Dato", "Valor"], ["Proyecto", f"{proyecto.codigo} · {proyecto.nombre}"], ["Entidad", proyecto.entidad_cliente], ["Contrato", proyecto.numero_contrato or "—"],
        ["Periodo", f"{desde.isoformat()} a {hasta.isoformat()}"], ["Plazo del contrato", f"{proyecto.fecha_inicio or '—'} a {proyecto.fecha_fin or '—'}"],
        ["Expedientes en el inventario", total_unidades]]})

    from arca.modulos.m24_productividad import servicios as productividad  # noqa: PLC0415

    t = productividad.tablero(ctx, proyecto, hasta)
    if t["frentes"]:
        secciones.append({"titulo": f"Avance por frente al {hasta.isoformat()}", "anchos": [0.08, 0.26, 0.11, 0.11, 0.1, 0.12, 0.12, 0.1], "tabla": [
            ["Frente", "Nombre", "Volumen", "Acumulado", "% avance", "Meta diaria", "Ritmo requerido", "Estado"]] + [
            [f["Frente"], f["Nombre"], f"{f['Volumen_Total']:,.0f} {f['Unidad']}", f"{f['Acumulado']:,.0f}", f"{f['Pct_Avance']:.1%}", f"{f['Meta_Diaria']:,.0f}",
             f"{f['Ritmo_Requerido_Dia']:,.1f}", f["Estado"]] for f in t["frentes"]]})

    recibidas = ctx.db.execute(select(RecursoDigital.estado, func.coalesce(func.sum(RecursoDigital.paginas), func.count())).where(
        RecursoDigital.proyecto_id == pid, RecursoDigital.creado_en >= a, RecursoDigital.creado_en < b).group_by(RecursoDigital.estado)).all()
    por_estado = {e: int(n or 0) for e, n in recibidas}
    ocr = _cuenta(ctx, TextoPagina, TextoPagina.proyecto_id == pid, TextoPagina.creado_en >= a, TextoPagina.creado_en < b, TextoPagina.estado == "leida")
    conf = ctx.db.scalar(select(func.avg(TextoPagina.confianza)).where(TextoPagina.proyecto_id == pid, TextoPagina.creado_en >= a, TextoPagina.creado_en < b,
                                                                        TextoPagina.estado == "leida"))
    secciones.append({"titulo": "Digitalización y OCR en el periodo", "tabla": [["Indicador", "Cantidad"],
        ["Páginas recibidas", sum(por_estado.values())], ["Aprobadas por calidad", por_estado.get("aprobado", 0)],
        ["En revisión o recaptura", por_estado.get("en_revision", 0) + por_estado.get("recaptura", 0)], ["Rechazadas", por_estado.get("rechazado", 0)],
        ["Páginas leídas con OCR", ocr], ["Confianza media del OCR", f"{conf:.1f} %" if conf is not None else "—"]]})

    plan = ctx.db.scalar(select(PlanAlistamiento).where(PlanAlistamiento.proyecto_id == pid))
    if plan:
        hechas = dict(ctx.db.execute(select(IntervencionExpediente.actividad, func.count()).where(IntervencionExpediente.proyecto_id == pid,
            IntervencionExpediente.hecho_en >= a, IntervencionExpediente.hecho_en < b).group_by(IntervencionExpediente.actividad)).all())
        acumuladas = dict(ctx.db.execute(select(IntervencionExpediente.actividad, func.count()).where(IntervencionExpediente.proyecto_id == pid)
                                         .group_by(IntervencionExpediente.actividad)).all())
        secciones.append({"titulo": "Alistamiento físico", "tabla": [["Actividad", "En el periodo", "Acumulado", "% del inventario"]] + [
            [x["nombre"], hechas.get(x["codigo"], 0), acumuladas.get(x["codigo"], 0), f"{(acumuladas.get(x['codigo'], 0) / total_unidades):.1%}" if total_unidades else "—"]
            for x in plan.actividades]})
    diagnosticos = list(ctx.db.scalars(select(DiagnosticoExpediente).where(DiagnosticoExpediente.proyecto_id == pid)))
    if diagnosticos:
        from arca.modulos.alistamiento.servicios import HALLAZGOS  # noqa: PLC0415

        secciones.append({"titulo": "Diagnóstico de conservación (acumulado)", "tabla": [["Estado", "Expedientes"]] + [
            [e.capitalize(), sum(1 for d in diagnosticos if d.estado == e)] for e in ("bueno", "regular", "malo")] + [
            ["Por aislar (deterioro biológico)", sum(1 for d in diagnosticos if any(HALLAZGOS[h][1] for h in d.hallazgos))]]})

    verificadas = _cuenta(ctx, HojaControl, HojaControl.proyecto_id == pid, HojaControl.estado == "verificada", HojaControl.verificada_en >= a, HojaControl.verificada_en < b)
    verificadas_total = _cuenta(ctx, HojaControl, HojaControl.proyecto_id == pid, HojaControl.estado == "verificada")
    secciones.append({"titulo": "Hojas de control", "tabla": [["Indicador", "Cantidad"], ["Verificadas en el periodo", verificadas],
                                                                ["Verificadas en total", verificadas_total], ["Expedientes del inventario", total_unidades]]})

    inspecciones = list(ctx.db.scalars(select(InspeccionLote).where(InspeccionLote.proyecto_id == pid, InspeccionLote.cerrada_en >= a, InspeccionLote.cerrada_en < b,
                                                                   InspeccionLote.estado.in_(("aceptada", "rechazada"))).order_by(InspeccionLote.numero)))
    if inspecciones:
        secciones.append({"titulo": "Inspección de calidad por lote", "tabla": [["N.º", "Lote", "Muestra", "Críticos", "Mayores", "Menores", "Resultado"]] + [
            [i.numero, i.lote or "Sin lote", f"{i.muestra} de {i.tamano}", i.criticos, i.mayores, i.menores, "Aceptado" if i.estado == "aceptada" else "Rechazado"]
            for i in inspecciones]})

    from arca.modulos.historias import servicios as historias  # noqa: PLC0415

    conf_hl = historias.config_de(ctx, proyecto)
    if conf_hl and conf_hl.activo:
        r = historias.expedientes(ctx, proyecto, limite=1)["resumen"]
        nombres = {"otra_persona": "Con documentos de otra persona", "duplicado": "Titular repetido", "faltan_tipos": "Faltan tipos mínimos",
                   "sin_titular": "El número del titular no aparece", "sin_numero": "Sin número de documento"}
        secciones.append({"titulo": "Historias laborales", "tabla": [["Indicador", "Cantidad"], ["Historias laborales", r["expedientes"]],
            ["Con titular confirmado", r["confirmados"]], ["Con alertas", r["con_alertas"]]] + [[nombres.get(k, k), v] for k, v in sorted(r["por_clase"].items())]})

    paquetes = list(ctx.db.scalars(select(PaqueteEntrega).where(PaqueteEntrega.proyecto_id == pid, PaqueteEntrega.terminado_en >= a, PaqueteEntrega.terminado_en < b,
                                                                PaqueteEntrega.estado == "listo").order_by(PaqueteEntrega.numero)))
    if paquetes:
        secciones.append({"titulo": "Entregas digitales", "tabla": [["Paquete", "Expedientes", "En PDF/A-2b", "Pendientes"]] + [
            [f"n.º {x.numero}", x.unidades, (x.resumen or {}).get("pdfa", {}).get("conformes", "—"), len(x.pendientes)] for x in paquetes]})

    novedades = list(ctx.db.scalars(select(Novedad).where(Novedad.proyecto_id == pid, Novedad.estado == "Abierta")))
    if novedades:
        secciones.append({"titulo": "Novedades abiertas", "tabla": [["Fecha", "Frente", "Caja", "Tipo", "Descripción", "Responsable"]] + [
            [n.fecha, n.frente, n.caja, n.tipo, n.descripcion, n.responsable] for n in sorted(novedades, key=lambda x: x.fecha)[:100]]})

    from arca.modulos.m25_auditoria.servicios import verificar_integridad  # noqa: PLC0415

    v = verificar_integridad(ctx.db, ctx.tenant_id)
    eventos = _cuenta(ctx, EventoAuditoria, EventoAuditoria.tenant_id == ctx.tenant_id, EventoAuditoria.fecha >= a, EventoAuditoria.fecha < b)
    secciones.append({"titulo": "Evidencia", "parrafos": [
        f"Cadena de auditoría de la organización: {'íntegra' if v.get('integra') else 'CON ALTERACIONES: revisar de inmediato'} ({v.get('revisados', 0)} eventos revisados).",
        f"Eventos registrados en el periodo: {eventos}. Cada archivo recibido y cada entregable tiene su huella SHA-256 en ARCA."]})
    return {"titulo": f"Informe de avance · {proyecto.codigo}", "subtitulo": f"{proyecto.entidad_cliente} · periodo {desde.isoformat()} a {hasta.isoformat()}",
            "secciones": secciones}


def excel(d: dict[str, Any]) -> bytes:
    import openpyxl  # noqa: PLC0415
    from openpyxl.styles import Font  # noqa: PLC0415

    libro = openpyxl.Workbook()
    h = libro.active
    h.title = "Informe"
    h.append([d["titulo"]])
    h["A1"].font = Font(bold=True, size=14)
    h.append([d["subtitulo"]])
    for s in d["secciones"]:
        h.append([])
        h.append([s["titulo"]])
        h.cell(h.max_row, 1).font = Font(bold=True, size=12)
        for p in s.get("parrafos") or []:
            h.append([p])
        for i, fila in enumerate(s.get("tabla") or []):
            h.append([c.isoformat() if hasattr(c, "isoformat") else c for c in fila])
            if i == 0:
                for celda in h[h.max_row]:
                    celda.font = Font(bold=True)
    for col in "ABCDEFGH":
        h.column_dimensions[col].width = 22
    h.column_dimensions["A"].width = 38
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def pdf_informe(d: dict[str, Any], logo: bytes | None, autor: str) -> tuple[bytes, bool]:
    from arca.nucleo import pdf  # noqa: PLC0415

    contenido, conforme, _ = pdf.a_pdfa(pdf.documento(d["titulo"], d["subtitulo"], d["secciones"], logo=logo, autor=autor), d["titulo"], autor)
    return contenido, conforme
