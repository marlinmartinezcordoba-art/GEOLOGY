"""
Recepción técnica del documento digitalizado.

Lo que entra a GEOLOGY es la reproducción de un documento histórico, y antes de describirlo
hay que saber si esa reproducción sirve. Este módulo hace tres cosas distintas y conviene no
confundirlas:

  1. LEE la ficha técnica del archivo: resolución real, profundidad de color, páginas, peso y
     si ya trae capa de texto. No modifica nada. Es lo que permite avisar, antes de que el
     expediente avance, que algo llegó por debajo del mínimo y hay que volver a escanearlo.

  2. CONSERVA una matriz fiel en formato de preservación. Se convierte a PDF/A y se calcula
     su huella, pero NO se le tocan las imágenes: es la reproducción del original y tiene que
     poder demostrarse que nadie la alteró. Es la que lee el modelo, porque es la que todavía
     muestra las manchas de humedad y la tinta desvanecida.

  3. DERIVA una copia de consulta enderezada, recortada y con capa de texto buscable. Sobre
     esta sí se trabaja la imagen. Nunca sustituye a la matriz.

Advertencia sobre la resolución. Los puntos por pulgada son un parámetro de CAPTURA. Un
archivo escaneado a 150 no se «sube» a 300: interpolar píxeles agranda el archivo sin
recuperar información que nunca se registró, y declarar 300 sobre eso falsearía la calidad
técnica de la reproducción. Por eso aquí solo se mide y se avisa.

Advertencia sobre el reconocimiento óptico. Los motores de reconocimiento leen texto impreso
y mecanografiado; sobre manuscrito antiguo en tinta ferrogálica fallan casi por completo. En
este fondo sirve para buscar palabras en lo mecanografiado, no para levantar la hoja de
control: eso lo hace el modelo, que lee manuscrito mucho mejor.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Mínimo de puntos por pulgada exigido. En CERO no se exige ninguno: la resolución se mide y
# se deja anotada, pero no se marca nada como incumplimiento.
#
# Va en cero a propósito. Lo que se está cargando hoy NO es la digitalización final de
# preservación: es material de trabajo para agilizar el levantamiento de la hoja de control.
# Exigirle parámetros de preservación a una captura de trabajo solo estorba. Cuando llegue el
# momento de la digitalización definitiva, se escribe el mínimo que exija el contrato en la
# variable UMBRAL_DPI del archivo .env y la plataforma vuelve a exigirlo.
UMBRAL_DPI = int(os.getenv("UMBRAL_DPI", "0"))
IDIOMA_OCR = os.getenv("IDIOMA_OCR", "spa")
SEGUNDOS_PROCESO = int(os.getenv("SEGUNDOS_PROCESO_IMAGEN", "1800"))


@dataclass
class FichaTecnica:
    """Lo que la plataforma sabe del archivo sin haberlo modificado."""
    paginas: int = 0
    dpi_minimo: int | None = None
    dpi_medio: int | None = None
    bits_por_color: int | None = None
    paginas_sin_imagen: int = 0
    tiene_capa_de_texto: bool = False
    tamano_bytes: int = 0
    sha256: str = ""
    error: str = ""
    avisos: list[str] = field(default_factory=list)

    @property
    def cumple(self) -> bool:
        """
        Cumple el mínimo de captura, si es que se está exigiendo alguno.

        Con UMBRAL_DPI en cero no se exige nada y todo cumple: lo cargado es material de
        trabajo, no la digitalización de preservación.
        """
        if self.error:
            return False                     # ni siquiera se pudo leer el archivo
        if UMBRAL_DPI <= 0:
            return True
        return bool(self.dpi_minimo and self.dpi_minimo >= UMBRAL_DPI)

    def como_dict(self) -> dict:
        return {"paginas": self.paginas, "dpi_minimo": self.dpi_minimo,
                "dpi_medio": self.dpi_medio, "bits_por_color": self.bits_por_color,
                "paginas_sin_imagen": self.paginas_sin_imagen,
                "tiene_capa_de_texto": self.tiene_capa_de_texto,
                "tamano_bytes": self.tamano_bytes, "sha256": self.sha256,
                "umbral_dpi": UMBRAL_DPI, "cumple": self.cumple,
                "error": self.error, "avisos": self.avisos}


def huella(ruta: Path) -> str:
    """Huella digital del archivo. Sirve para probar que no ha cambiado desde que entró."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def leer_ficha(ruta: Path) -> FichaTecnica:
    """
    Mide el archivo sin tocarlo.

    Los puntos por pulgada no vienen escritos en el documento portátil: se deducen. Cada
    página declara su tamaño en puntos tipográficos, setenta y dos por pulgada, y cada imagen
    incrustada declara su ancho en píxeles. El cociente de los dos es la resolución real con
    la que se capturó esa página.
    """
    ficha = FichaTecnica(tamano_bytes=ruta.stat().st_size if ruta.exists() else 0)
    if not ruta.exists():
        ficha.error = "El archivo no está en el almacén."
        return ficha
    try:
        ficha.sha256 = huella(ruta)
        import pikepdf
    except ImportError:
        ficha.error = "Falta la biblioteca de lectura de documentos portátiles."
        return ficha
    except Exception as e:
        ficha.error = f"No se pudo calcular la huella: {e}"
        return ficha

    resoluciones: list[int] = []
    bits: list[int] = []
    try:
        with pikepdf.open(ruta) as pdf:
            ficha.paginas = len(pdf.pages)
            for pagina in pdf.pages:
                caja = pagina.get("/MediaBox") or [0, 0, 612, 792]
                ancho_pulgadas = abs(float(caja[2]) - float(caja[0])) / 72.0
                alto_pulgadas = abs(float(caja[3]) - float(caja[1])) / 72.0
                if "/Contents" in pagina and _tiene_texto(pagina):
                    ficha.tiene_capa_de_texto = True

                imagenes = list(_imagenes(pagina))
                if not imagenes:
                    ficha.paginas_sin_imagen += 1
                    continue
                for img in imagenes:
                    try:
                        pixeles_ancho = int(img.get("/Width", 0))
                        pixeles_alto = int(img.get("/Height", 0))
                        if img.get("/BitsPerComponent") is not None:
                            bits.append(int(img["/BitsPerComponent"]))
                        if pixeles_ancho and ancho_pulgadas > 0:
                            resoluciones.append(round(pixeles_ancho / ancho_pulgadas))
                        if pixeles_alto and alto_pulgadas > 0:
                            resoluciones.append(round(pixeles_alto / alto_pulgadas))
                    except Exception:
                        continue
    except Exception as e:
        ficha.error = f"No se pudo leer el documento: {type(e).__name__}: {e}"
        return ficha

    if resoluciones:
        ficha.dpi_minimo = min(resoluciones)
        ficha.dpi_medio = round(sum(resoluciones) / len(resoluciones))
    if bits:
        ficha.bits_por_color = min(bits)

    _avisar(ficha)
    return ficha


def _tiene_texto(pagina) -> bool:
    """Si la página ya trae capa de texto, no hace falta volver a reconocerla."""
    try:
        recursos = pagina.get("/Resources") or {}
        return "/Font" in recursos
    except Exception:
        return False


def _imagenes(pagina):
    """Las imágenes incrustadas en una página, que son las hojas escaneadas."""
    try:
        recursos = pagina.get("/Resources") or {}
        xobjetos = recursos.get("/XObject") or {}
        for nombre in xobjetos.keys():
            obj = xobjetos[nombre]
            if obj.get("/Subtype") == "/Image":
                yield obj
    except Exception:
        return


def _avisar(ficha: FichaTecnica) -> None:
    if ficha.dpi_minimo is None:
        if ficha.paginas_sin_imagen == ficha.paginas and ficha.tiene_capa_de_texto:
            ficha.avisos.append(
                "El archivo no trae imágenes escaneadas: parece un documento nacido digital, "
                "no la reproducción de un papel. Compruebe que sea el archivo correcto.")
        return

    if UMBRAL_DPI > 0 and ficha.dpi_minimo < UMBRAL_DPI:
        ficha.avisos.append(
            f"RESOLUCIÓN INSUFICIENTE. La página peor capturada está en {ficha.dpi_minimo} "
            f"puntos por pulgada y el mínimo exigido es {UMBRAL_DPI}. Hay que volver a "
            "escanear el expediente: la resolución no se puede subir después, solo se captura.")
    if ficha.paginas_sin_imagen and ficha.paginas_sin_imagen < ficha.paginas:
        ficha.avisos.append(
            f"{ficha.paginas_sin_imagen} de {ficha.paginas} páginas no traen imagen. "
            "Revise que no se hayan colado hojas en blanco o separadores del escáner.")
    if ficha.bits_por_color == 1 and UMBRAL_DPI > 0:
        ficha.avisos.append(
            "El expediente está capturado en blanco y negro puro. Para documento histórico se "
            "pierde el detalle del soporte, las tintas y el estado de conservación; se "
            "recomienda escala de grises o color.")


# ---------------------------------------------------------------------------
# Matriz de preservación y copia de consulta
# ---------------------------------------------------------------------------

def disponible() -> bool:
    """Si el equipo tiene instalado el motor de procesamiento de imagen."""
    return shutil.which("ocrmypdf") is not None


def _correr(argumentos: list[str]) -> tuple[bool, str]:
    try:
        r = subprocess.run(argumentos, capture_output=True, text=True, timeout=SEGUNDOS_PROCESO)
    except subprocess.TimeoutExpired:
        return False, f"El procesamiento superó los {SEGUNDOS_PROCESO} segundos."
    except FileNotFoundError:
        return False, "No está instalado el motor de procesamiento de imagen."
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "").strip()[:400]
    return True, ""


def matriz_de_preservacion(origen: Path, destino: Path) -> tuple[bool, str]:
    """
    Convierte a PDF/A **sin tocar las imágenes**.

    Es la reproducción fiel del original. No se endereza, no se limpia y no se recorta: lo que
    se ve es lo que hay en el papel, incluidas las manchas y los dobleces, que son evidencia
    del estado de conservación y alimentan el elemento 3.4.4 de la descripción.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    return _correr([
        "ocrmypdf", "--output-type", "pdfa", "--skip-text", "--optimize", "0",
        "--quiet", str(origen), str(destino)])


def copia_de_consulta(origen: Path, destino: Path, con_ocr: bool = True) -> tuple[bool, str]:
    """
    Copia trabajada para consultar y buscar.

    Aquí sí se endereza el papel, se quitan los bordes de la cama del escáner, se rotan las
    páginas acostadas y se agrega la capa de texto buscable. Nunca sustituye a la matriz.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    # --clean-final deja en el archivo la imagen ya limpiada, que es de lo que se trata una
    # copia de consulta. --clean a secas limpia solo para reconocer y guarda la imagen sucia.
    # --skip-text va siempre: si la página ya trae texto no se vuelve a reconocer, y sin esa
    # opción el motor se detiene con error en vez de continuar.
    argumentos = ["ocrmypdf", "--output-type", "pdfa", "--deskew", "--clean-final",
                  "--rotate-pages", "--skip-text", "--quiet"]
    if con_ocr:
        # El texto reconocido se guarda además aparte. Sirve para dárselo al modelo junto con
        # la imagen: sobre lo mecanografiado le ahorra trabajo y le evita errores de lectura.
        argumentos += ["-l", IDIOMA_OCR, "--sidecar", str(destino.with_suffix(".txt"))]
    else:
        argumentos += ["--tesseract-timeout", "0"]
    argumentos += [str(origen), str(destino)]
    return _correr(argumentos)


def texto_reconocido(ruta_texto: Path | None, tope_caracteres: int = 60000) -> str:
    """
    El texto que el reconocimiento óptico sacó del expediente.

    Se le entrega al modelo COMO APOYO, junto con la imagen, nunca en lugar de ella. Sobre
    documento mecanografiado le ahorra descifrar y le evita confundir cifras; sobre manuscrito
    antiguo el reconocimiento devuelve casi basura, y por eso se le advierte al modelo que
    puede venir mal y que mande lo que él mismo vea en la imagen.
    """
    if not ruta_texto or not Path(ruta_texto).exists():
        return ""
    try:
        texto = Path(ruta_texto).read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""
    # Si salieron cuatro palabras sueltas, es manuscrito y el reconocimiento no sirvió.
    if len(texto) < 200:
        return ""
    return texto[:tope_caracteres]
