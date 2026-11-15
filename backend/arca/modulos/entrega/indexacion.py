"""Archivo de indexación para el SGDEA de la entidad (D-47).

Cada SGDEA carga los expedientes con su propio archivo de indexación: unas columnas con unos nombres. ARCA no lo
adivina: la dirección lo configura por proyecto en el parámetro versionado `entrega.indexacion` (M03), con motivo:

    {"por": "expediente" | "documento", "separador": ";", "nombre_archivo": "indice.csv",
     "columnas": [{"nombre": "NUMERO_IDENTIFICACION", "campo": "titular.numero_documento"},
                  {"nombre": "RUTA", "campo": "pdf.ruta"}, {"nombre": "SERIE", "campo": "fijo:Historias laborales"}]}

`por: documento` escribe una fila por cada documento de la hoja de control verificada (y los campos `documento.*`).
El archivo va dentro del paquete de entrega, con su huella en el manifiesto.
"""

import csv
import io
from typing import Any

CAMPOS: dict[str, str] = {
    "proyecto.codigo": "Código del proyecto", "proyecto.entidad": "Entidad cliente",
    "unidad.identificador": "Identificador del expediente", "unidad.numero_orden": "Número de orden", "unidad.nombre": "Nombre del expediente",
    "unidad.codigo_serie_fuid": "Código de serie del FUID", "unidad.fecha_inicial": "Fecha inicial", "unidad.fecha_final": "Fecha final",
    "unidad.caja": "Caja", "unidad.carpeta": "Carpeta", "unidad.tomo": "Tomo", "unidad.folios": "Folios (contados en la hoja verificada, si la hay)",
    "unidad.soporte": "Soporte", "unidad.fase": "Fase del ciclo vital",
    "clasificacion.codigo": "Código de la TRD", "clasificacion.nombre": "Serie o subserie", "clasificacion.dependencia": "Dependencia",
    "clasificacion.acceso": "Acceso según la TRD", "clasificacion.disposicion": "Disposición final",
    "titular.tipo_documento": "Tipo de documento del titular", "titular.numero_documento": "Número de documento del titular",
    "titular.nombres": "Nombre del titular", "titular.cargo": "Cargo del titular", "titular.fecha_vinculacion": "Fecha de vinculación",
    "titular.fecha_retiro": "Fecha de retiro",
    "pdf.ruta": "Ruta del PDF dentro del paquete", "pdf.formato": "Formato del PDF (PDF/A-2b o PDF)", "pdf.sha256": "Huella SHA-256 del PDF",
    "pdf.paginas": "Número de páginas",
    "documento.orden": "Número del documento en la hoja", "documento.tipo_documental": "Tipo documental", "documento.fecha": "Fecha del documento",
    "documento.folio_desde": "Folio inicial", "documento.folio_hasta": "Folio final", "documento.pagina_desde": "Página inicial en el PDF",
    "documento.pagina_hasta": "Página final en el PDF", "documento.asunto": "Asunto", "documento.remitente": "Remitente",
    "documento.destinatario": "Destinatario", "documento.radicado": "Radicado",
}
SEPARADORES = (";", ",", "|", "\t")


def validar(valor: Any) -> None:
    """Lo usa M03 al publicar el parámetro: si algo no sirve, se dice antes de guardarlo."""
    if not isinstance(valor, dict):
        raise ValueError("entrega.indexacion es un objeto con «columnas», «por», «separador» y «nombre_archivo»")
    columnas = valor.get("columnas")
    if not isinstance(columnas, list) or not 1 <= len(columnas) <= 80:
        raise ValueError("«columnas» es una lista de 1 a 80 columnas {nombre, campo}")
    por = valor.get("por", "expediente")
    if por not in ("expediente", "documento"):
        raise ValueError("«por» es «expediente» o «documento»")
    if valor.get("separador", ";") not in SEPARADORES:
        raise ValueError("«separador» es ; , | o tabulador")
    nombre = str(valor.get("nombre_archivo", "indice.csv"))
    if not nombre.lower().endswith((".csv", ".txt")) or "/" in nombre or ".." in nombre:
        raise ValueError("«nombre_archivo» es un nombre de archivo .csv o .txt, sin carpetas")
    for c in columnas:
        campo = str((c or {}).get("campo", ""))
        if not str((c or {}).get("nombre", "")).strip():
            raise ValueError("Cada columna necesita su «nombre»")
        if not (campo in CAMPOS or campo.startswith("fijo:")):
            raise ValueError(f"Campo desconocido: «{campo}». Use uno de la lista o «fijo:texto»")
        if campo.startswith("documento.") and por != "documento":
            raise ValueError(f"«{campo}» solo sirve con «por»: «documento»")


def _valor(campo: str, meta: dict[str, Any], pdf: dict[str, Any], doc: dict[str, Any] | None) -> Any:
    if campo.startswith("fijo:"):
        return campo[5:]
    grupo, clave = campo.split(".", 1)
    if grupo == "proyecto":
        return meta["proyecto"].get("codigo" if clave == "codigo" else "entidad")
    if grupo == "unidad":
        if clave == "folios":
            h = meta.get("hoja_control")
            return h["total_folios"] if h and h.get("total_folios") is not None else meta["unidad"].get("folios_inventario")
        return meta["unidad"].get(clave)
    if grupo == "clasificacion":
        return (meta.get("clasificacion") or {}).get(clave)
    if grupo == "titular":
        return (meta.get("titular") or {}).get(clave)
    if grupo == "pdf":
        return pdf.get(clave)
    if grupo == "documento" and doc is not None:
        if clave in ("asunto", "remitente", "destinatario"):
            return (doc.get("metadatos") or {}).get(clave)
        return doc.get({"radicado": "no_radicado"}.get(clave, clave))
    return None


def filas(config: dict[str, Any], meta: dict[str, Any], pdf: dict[str, Any]) -> list[list[Any]]:
    documentos = (meta.get("hoja_control") or {}).get("documentos") or []
    unidades = documentos if config.get("por") == "documento" else [None]
    return [[_valor(c["campo"], meta, pdf, d) for c in config["columnas"]] for d in unidades]


def archivo(config: dict[str, Any], todas: list[list[Any]]) -> bytes:
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=config.get("separador", ";"), lineterminator="\r\n")
    escritor.writerow([c["nombre"] for c in config["columnas"]])
    escritor.writerows([["" if v is None else v for v in f] for f in todas])
    return salida.getvalue().encode("utf-8-sig")
