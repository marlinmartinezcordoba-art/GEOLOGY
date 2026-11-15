"""PDF/A-2b (ISO 19005-2, nivel B): el formato de preservación del expediente digitalizado.

ARCA arma el PDF del expediente (las páginas derechas con el texto del OCR debajo) y lo convierte a PDF/A-2b:
perfil de color sRGB como intención de salida, metadatos XMP con la declaración PDF/A y sincronizados con la
información del documento, identificador del archivo y las demás reglas de la norma.

La conversión y la validación las hace `pikepdf.pdfa`, un validador por **lista permitida**: aprueba un archivo
solo si cada construcción que encuentra es conocida y conforme, así que puede rechazar de más, pero no aprobar
de más. Después de escribir el archivo lo vuelve a abrir y lo valida: lo que se aprueba son los bytes escritos.

Si un archivo no se puede aprobar, ARCA no lo entrega como PDF/A: lo entrega como PDF y dice por qué.
No reemplaza una validación externa con veraPDF (la herramienta de referencia), que se puede correr aparte.
"""

import io
from dataclasses import dataclass, field
from typing import Any

import pikepdf

NIVEL = "2b"
NOMBRE = "PDF/A-2b"


def disponible() -> bool:
    try:
        from pikepdf import pdfa  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def motor() -> str:
    return f"pikepdf {pikepdf.__version__} · validador PDF/A por lista permitida"


@dataclass
class Resultado:
    contenido: bytes
    conforme: bool
    nivel: str = NOMBRE
    hallazgos: list[dict[str, str]] = field(default_factory=list)
    motor: str = ""

    def como_dict(self) -> dict[str, Any]:
        return {"formato": self.nivel if self.conforme else "PDF (no es PDF/A)", "conforme": self.conforme, "validado_con": self.motor, "hallazgos": self.hallazgos}


# Áreas de la norma ISO 19005-2 (cláusula 6), para explicar en español qué parte del archivo incumple.
AREAS = (("6.2.11", "Fuentes: no están incrustadas o están incompletas"), ("6.2", "Gráficos: color, imágenes o transparencias"),
         ("6.1", "Estructura del archivo"), ("6.3", "Anotaciones"), ("6.4", "Formularios"), ("6.5", "Acciones o JavaScript"),
         ("6.6", "Metadatos del documento (XMP)"), ("6.8", "Archivos incrustados"), ("6.9", "Contenido opcional (capas)"))
EXPLICACIONES = {"6.1.3-1": "Al archivo le falta su identificador (/ID).", "6.6.2.1-1": "Al documento le faltan los metadatos XMP."}


def _area(regla: str) -> str:
    clausula = regla.rsplit(":", 1)[-1]
    return next((nombre for prefijo, nombre in AREAS if clausula == prefijo or clausula.startswith(prefijo + ".") or clausula.startswith(prefijo + "-")), "")


def _hallazgos(reporte) -> list[dict[str, str]]:
    salida = []
    for f in reporte.findings[:50]:
        clausula = f.rule.rsplit(":", 1)[-1]
        salida.append({"regla": f.rule, "area": _area(f.rule), "explicacion": EXPLICACIONES.get(clausula, ""), "donde": str(f.where)[:200],
                       "mensaje": str(f.message)[:500], "tipo": "incumple" if f.kind == "violation" else "no verificado"})
    return salida


def _datos(pdf: pikepdf.Pdf, titulo: str, asunto: str, autor: str, palabras: str) -> None:
    pdf.docinfo["/Title"] = titulo[:500]
    pdf.docinfo["/Creator"] = "ARCA"
    if asunto:
        pdf.docinfo["/Subject"] = asunto[:1000]
    if autor:
        pdf.docinfo["/Author"] = autor[:300]
    if palabras:
        pdf.docinfo["/Keywords"] = palabras[:500]


def convertir(pdf: pikepdf.Pdf, titulo: str, asunto: str = "", autor: str = "", palabras: str = "") -> Resultado:
    """Convierte a PDF/A-2b y valida lo escrito. Si no se puede aprobar, devuelve el PDF común con los hallazgos."""
    _datos(pdf, titulo, asunto, autor, palabras)
    if not disponible():
        salida = io.BytesIO()
        pdf.save(salida)
        return Resultado(salida.getvalue(), False, hallazgos=[{"regla": "arca", "donde": "servidor", "mensaje": "Falta instalar pikepdf[pdfa] en el servidor", "tipo": "no verificado"}])
    from pikepdf import pdfa  # noqa: PLC0415

    salida = io.BytesIO()
    try:
        pdfa.save(pdf, salida, NIVEL)
        return Resultado(salida.getvalue(), True, motor=motor())
    except pdfa.PdfaError as e:
        comun = io.BytesIO()
        pdf.save(comun)
        return Resultado(comun.getvalue(), False, hallazgos=_hallazgos(e.report), motor=motor())


def validar(contenido: bytes, nivel: str = NIVEL) -> dict[str, Any]:
    """Valida un PDF ya escrito contra PDF/A-1b, 2b o 3b. No lo modifica."""
    if nivel not in ("1b", "2b", "3b"):
        raise ValueError("Nivel PDF/A no admitido: use 1b, 2b o 3b")
    if not disponible():
        return {"nivel": f"PDF/A-{nivel}", "conforme": False, "veredicto": "no_verificado", "hallazgos": [], "validado_con": "", "aviso": "Falta instalar pikepdf[pdfa] en el servidor"}
    from pikepdf import pdfa  # noqa: PLC0415

    r = pdfa.validate_written(io.BytesIO(contenido), nivel)
    veredicto = {"pass": "conforme", "fail": "no_conforme", "not_checked": "no_verificado"}[r.verdict]
    return {"nivel": f"PDF/A-{nivel}", "conforme": r.passed, "veredicto": veredicto, "hallazgos": _hallazgos(r), "validado_con": motor()}
