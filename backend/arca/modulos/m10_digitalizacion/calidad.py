"""M11 Control de calidad de lo digitalizado: medir sin tocar y señalar. Funciones puras sobre los bytes.

Reciclado de GEOLOGY (dominio/recepcion_tecnica.py):
- La resolución NO se «sube»: es un parámetro de captura. Se mide (píxeles de la imagen sobre el tamaño de la
  página) y, si está por debajo del mínimo del perfil, se señala para recapturar.
- El archivo del repositorio no se modifica: aquí solo se lee.

Agregado en ARCA: detección de páginas en blanco en las imágenes y la decisión automática según el perfil
del proyecto (aprobar, enviar a revisión humana o rechazar).
"""

import io
from typing import Any

from arca.modulos.m10_digitalizacion.perfil import HALLAZGOS

_COLOR_RANGO = {"cualquiera": 0, "grises": 1, "color": 2}


def _modo_a_rango(modo: str | None, bits: int | None = None) -> int:
    if modo in ("RGB", "RGBA", "CMYK", "YCbCr", "P", "/DeviceRGB", "/DeviceCMYK", "/ICCBased", "/Indexed"):
        return 2
    if modo in ("L", "LA", "I;16", "/DeviceGray") and (bits is None or bits > 1):
        return 1
    return 0  # bitonal (1 bit) o desconocido


def ficha_pdf(contenido: bytes) -> dict[str, Any]:
    import pikepdf

    ficha: dict[str, Any] = {"paginas": 0, "dpi_minimo": None, "dpi_medio": None, "paginas_sin_imagen": 0, "capa_de_texto": False, "color": 0}
    try:
        with pikepdf.open(io.BytesIO(contenido)) as pdf:
            ficha["paginas"] = len(pdf.pages)
            resoluciones: list[int] = []
            for pagina in pdf.pages:
                caja = pagina.get("/MediaBox") or [0, 0, 612, 792]
                ancho = abs(float(caja[2]) - float(caja[0])) / 72.0
                alto = abs(float(caja[3]) - float(caja[1])) / 72.0
                recursos = pagina.get("/Resources") or {}
                if "/Font" in recursos:
                    ficha["capa_de_texto"] = True
                imagenes = [o for o in (recursos.get("/XObject") or {}).values() if o.get("/Subtype") == "/Image"]
                if not imagenes:
                    ficha["paginas_sin_imagen"] += 1
                    continue
                for img in imagenes:
                    w, h = int(img.get("/Width", 0)), int(img.get("/Height", 0))
                    bits = int(img.get("/BitsPerComponent", 8) or 8)
                    espacio = img.get("/ColorSpace")
                    nombre_espacio = str(espacio[0] if isinstance(espacio, pikepdf.Array) else espacio) if espacio is not None else None
                    ficha["color"] = max(ficha["color"], _modo_a_rango(nombre_espacio, bits))
                    if w and ancho > 0:
                        resoluciones.append(round(w / ancho))
                    if h and alto > 0:
                        resoluciones.append(round(h / alto))
            if resoluciones:
                ficha["dpi_minimo"] = min(resoluciones)
                ficha["dpi_medio"] = round(sum(resoluciones) / len(resoluciones))
    except Exception as e:  # noqa: BLE001 — cualquier falla de lectura es un hallazgo, no una caída
        ficha["error"] = f"{type(e).__name__}: {e}"[:300]
    return ficha


def ficha_imagen(contenido: bytes, umbral_blanco: float) -> dict[str, Any]:
    from PIL import Image

    ficha: dict[str, Any] = {"paginas": 1, "dpi_minimo": None, "dpi_medio": None, "color": 0, "ancho": None, "alto": None, "proporcion_blanco": None}
    try:
        with Image.open(io.BytesIO(contenido)) as img:
            img.load()
            ficha["ancho"], ficha["alto"] = img.size
            ficha["modo"] = img.mode
            ficha["color"] = _modo_a_rango(img.mode, 1 if img.mode == "1" else 8)
            if dpi := img.info.get("dpi"):
                valores = [round(float(x)) for x in dpi if x]
                if valores:
                    ficha["dpi_minimo"], ficha["dpi_medio"] = min(valores), round(sum(valores) / len(valores))
            gris = img.convert("L")
            gris.thumbnail((600, 600))
            histograma = gris.histogram()
            total = sum(histograma) or 1
            ficha["proporcion_blanco"] = round(sum(histograma[235:]) / total, 4)
            if getattr(img, "n_frames", 1) > 1:
                ficha["paginas"] = img.n_frames
    except Exception as e:  # noqa: BLE001
        ficha["error"] = f"{type(e).__name__}: {e}"[:300]
    return ficha


def hallazgo(codigo: str, gravedad: str, detalle: str = "", pagina: int | None = None) -> dict[str, Any]:
    return {"codigo": codigo, "gravedad": gravedad, "mensaje": HALLAZGOS[codigo] + (f": {detalle}" if detalle else ""), "pagina": pagina}


def evaluar(ficha: dict[str, Any], formato: str, perfil: dict[str, Any]) -> list[dict[str, Any]]:
    """Hallazgos del archivo según el perfil. No decide: eso lo hace `decidir`."""
    h: list[dict[str, Any]] = []
    if ficha.get("error"):
        return [hallazgo("ilegible", "error", ficha["error"])]
    if formato not in perfil["formatos"]:
        h.append(hallazgo("formato_no_admitido", "error", formato))
    minimo = perfil["dpi_minimo"]
    if minimo and ficha.get("dpi_minimo") is not None and ficha["dpi_minimo"] < minimo:
        h.append(hallazgo("resolucion_baja", "error", f"{ficha['dpi_minimo']} ppp, mínimo {minimo}"))
    elif minimo and ficha.get("dpi_minimo") is None and formato != "PDF":
        h.append(hallazgo("resolucion_baja", "revisar", "la imagen no declara su resolución"))
    if ficha.get("color", 0) < _COLOR_RANGO[perfil["color_minimo"]]:
        h.append(hallazgo("color_insuficiente", "error", f"se exige {perfil['color_minimo']}"))
    if formato == "PDF" and ficha.get("paginas") and ficha.get("paginas_sin_imagen") == ficha.get("paginas"):
        h.append(hallazgo("sin_imagenes", "revisar"))
    if perfil["detectar_blancos"] and ficha.get("proporcion_blanco") is not None and ficha["proporcion_blanco"] >= float(perfil["umbral_blanco"]):
        h.append(hallazgo("pagina_en_blanco", "revisar", f"{ficha['proporcion_blanco']:.1%} de la imagen es blanco"))
    return h


def decidir(hallazgos: list[dict[str, Any]], perfil: dict[str, Any]) -> str:
    """aprobado (sin hallazgos) · rechazado (alguno está en el rechazo automático) · en_revision (lo demás)."""
    if not hallazgos:
        return "aprobado"
    if any(x["codigo"] in perfil["rechazo_automatico"] for x in hallazgos):
        return "rechazado"
    return "en_revision"
