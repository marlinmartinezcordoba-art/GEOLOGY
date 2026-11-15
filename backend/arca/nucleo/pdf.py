"""Documentos PDF de ARCA (D-47): informes y entregables con el logo de la entidad, en PDF/A-2b validado.

- La fuente va incrustada (DejaVu Sans; si el servidor no la tiene, la Vera que trae reportlab), así el PDF se puede
  convertir a PDF/A y se ve igual en cualquier equipo.
- `documento` arma un informe por secciones (títulos, párrafos y tablas) con el logo en el encabezado y el número
  de página al pie.
- `desde_excel` pasa a PDF un entregable ya expedido en Excel (la hoja como tabla), con el logo.
- Todo sale por `pdfa.convertir`: si no se puede aprobar como PDF/A, va como PDF común (y se dice en la respuesta).
"""

import io
from datetime import datetime
from pathlib import Path
from typing import Any

FUENTES = [("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]


def _fuentes() -> tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics  # noqa: PLC0415
    from reportlab.pdfbase.ttfonts import TTFont  # noqa: PLC0415

    if "ArcaSans" in pdfmetrics.getRegisteredFontNames():
        return "ArcaSans", "ArcaSans-Bold"
    import reportlab  # noqa: PLC0415

    vera = Path(reportlab.__file__).parent / "fonts"
    for normal, negrita in [*FUENTES, (str(vera / "Vera.ttf"), str(vera / "VeraBd.ttf"))]:
        if Path(normal).is_file() and Path(negrita).is_file():
            pdfmetrics.registerFont(TTFont("ArcaSans", normal))
            pdfmetrics.registerFont(TTFont("ArcaSans-Bold", negrita))
            return "ArcaSans", "ArcaSans-Bold"
    raise RuntimeError("No hay una fuente TrueType para incrustar en el PDF")


def documento(titulo: str, subtitulo: str, secciones: list[dict[str, Any]], logo: bytes | None = None, horizontal: bool = False, autor: str = "") -> bytes:
    """`secciones`: [{titulo, parrafos?: [str], tabla?: [[celda…]…] (la primera fila es el encabezado), anchos?: [float]}]."""
    from reportlab.lib import colors  # noqa: PLC0415
    from reportlab.lib.pagesizes import A4, landscape  # noqa: PLC0415
    from reportlab.lib.styles import ParagraphStyle  # noqa: PLC0415
    from reportlab.lib.units import cm  # noqa: PLC0415
    from reportlab.lib.utils import ImageReader  # noqa: PLC0415
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: PLC0415

    normal, negrita = _fuentes()
    from reportlab import rl_config  # noqa: PLC0415

    rl_config.canvas_basefontname = normal  # sin esto el lienzo arranca con Helvetica, que no va incrustada (PDF/A la rechaza)
    tamano = landscape(A4) if horizontal else A4
    estilo = ParagraphStyle("n", fontName=normal, fontSize=9, leading=12)
    celda = ParagraphStyle("c", fontName=normal, fontSize=7.5, leading=9.5)
    celda_n = ParagraphStyle("cn", fontName=negrita, fontSize=7.5, leading=9.5)
    h1 = ParagraphStyle("h1", fontName=negrita, fontSize=15, leading=19, spaceAfter=2)
    h2 = ParagraphStyle("h2", fontName=negrita, fontSize=11, leading=14, spaceBefore=10, spaceAfter=4)
    gris = ParagraphStyle("g", fontName=normal, fontSize=8.5, leading=11, textColor=colors.HexColor("#555555"))
    imagen = ImageReader(io.BytesIO(logo)) if logo else None

    def pagina(lienzo, doc) -> None:
        lienzo.saveState()
        ancho, alto = tamano
        if imagen:
            iw, ih = imagen.getSize()
            h = 1.4 * cm
            lienzo.drawImage(imagen, ancho - 1.5 * cm - h * iw / ih, alto - 1.0 * cm - h, width=h * iw / ih, height=h, mask="auto")
        lienzo.setFont(normal, 7.5)
        lienzo.setFillColor(colors.HexColor("#666666"))
        lienzo.drawString(1.5 * cm, 0.9 * cm, f"{titulo} · generado por ARCA el {datetime.now():%Y-%m-%d %H:%M}")
        lienzo.drawRightString(ancho - 1.5 * cm, 0.9 * cm, f"Página {doc.page}")
        lienzo.restoreState()

    def texto(v: Any, n: bool = False) -> Paragraph:
        s = "" if v is None else (v.isoformat() if hasattr(v, "isoformat") else str(v))
        return Paragraph(s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>"), celda_n if n else celda)

    salida = io.BytesIO()
    doc = SimpleDocTemplate(salida, pagesize=tamano, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=2.8 * cm, bottomMargin=1.6 * cm,
                            title=titulo, author=autor, creator="ARCA")
    flujo: list[Any] = [Paragraph(titulo, h1), Paragraph(subtitulo, gris), Spacer(1, 6)]
    util = tamano[0] - 3 * cm
    for s in secciones:
        if s.get("titulo"):
            flujo.append(Paragraph(s["titulo"], h2))
        for p in s.get("parrafos") or []:
            flujo.append(Paragraph(str(p), estilo))
        filas = s.get("tabla")
        if filas:
            columnas = max(len(f) for f in filas)
            anchos = [util * a for a in s["anchos"]] if s.get("anchos") else [util / columnas] * columnas
            datos = [[texto(c, i == 0) for c in f] + [texto("")] * (columnas - len(f)) for i, f in enumerate(filas)]
            t = Table(datos, colWidths=anchos, repeatRows=1)
            t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), normal), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            flujo.append(t)
    doc.build(flujo, onFirstPage=pagina, onLaterPages=pagina)
    return salida.getvalue()


def desde_excel(contenido: bytes, titulo: str, logo: bytes | None = None, autor: str = "") -> bytes:
    """Un entregable expedido en Excel, como PDF: cada hoja es una sección y sus celdas con datos, una tabla."""
    import openpyxl  # noqa: PLC0415

    libro = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True)
    secciones = []
    for hoja in libro.worksheets:
        filas = [list(f) for f in hoja.iter_rows(values_only=True)]
        filas = [f for f in filas if any(v not in (None, "") for v in f)]
        if not filas:
            continue
        ultima = max(max((i for i, v in enumerate(f) if v not in (None, "")), default=0) for f in filas) + 1
        secciones.append({"titulo": hoja.title if len(libro.worksheets) > 1 else "", "tabla": [[v for v in f[:ultima]] for f in filas]})
    return documento(titulo, "Entregable expedido en el formato de la entidad", secciones, logo=logo, horizontal=True, autor=autor)


def a_pdfa(pdf: bytes, titulo: str, autor: str = "") -> tuple[bytes, bool, list[dict[str, str]]]:
    """(contenido, es PDF/A-2b, hallazgos) con la conversión validada de `pdfa`."""
    import pikepdf  # noqa: PLC0415

    from arca.modulos.entrega import pdfa  # noqa: PLC0415

    documento = pikepdf.open(io.BytesIO(pdf))
    for pagina in documento.pages:  # reportlab agrega transiciones de presentación: en un documento de archivo sobran
        if "/Trans" in pagina.obj:
            del pagina.obj["/Trans"]
    r = pdfa.convertir(documento, titulo, autor=autor)
    return r.contenido, r.conforme, r.hallazgos
