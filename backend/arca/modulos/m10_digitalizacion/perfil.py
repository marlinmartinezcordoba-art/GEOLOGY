"""Perfil de digitalización del proyecto: lo que se configura desde la pantalla y rige la recepción y la calidad.

Se guarda como el parámetro versionado `digitalizacion.perfil` del proyecto (M03): cada cambio es una
versión nueva con su vigencia y su motivo, y cada archivo recibido anota qué versión del perfil se le aplicó.
Las tolerancias son por proyecto y soporte (Maestro, ARC-09).
"""

from typing import Any

CLAVE = "digitalizacion.perfil"

FORMATOS = ("PDF", "TIFF", "JPEG", "PNG")
COLOR = ("cualquiera", "grises", "color")

# Hallazgos que el control de calidad sabe detectar hoy, y su gravedad por defecto.
HALLAZGOS: dict[str, str] = {
    "ilegible": "El archivo no se puede abrir: está dañado, cifrado o no es lo que dice ser",
    "formato_no_admitido": "Formato no admitido por el perfil del proyecto",
    "resolucion_baja": "Resolución por debajo del mínimo del perfil",
    "color_insuficiente": "Profundidad de color por debajo de la exigida",
    "pagina_en_blanco": "Imagen en blanco o casi en blanco",
    "sin_imagenes": "El PDF no trae imágenes escaneadas: parece un documento nacido digital",
    "duplicado": "El mismo archivo (misma huella) ya se había recibido en el proyecto",
    "salto_secuencia": "Falta una página o una parte en la secuencia",
    "folios_no_coinciden": "El número de imágenes no coincide con los folios del inventario",
}

POR_DEFECTO: dict[str, Any] = {
    "modalidades": ["pdf", "imagenes"],  # PDF por carpeta y/o una imagen por página
    "formatos": list(FORMATOS),
    "dpi_minimo": 0,  # 0 = se mide y se anota, pero no se exige
    "color_minimo": "cualquiera",
    "detectar_blancos": True,
    "umbral_blanco": 0.995,  # proporción de píxeles casi blancos para considerar la imagen en blanco
    "comparar_folios": True,  # avisa si imágenes ≠ folios del FUID (la doble cara hace que no siempre coincidan)
    "identificar_por": "archivo_o_carpeta",  # archivo_o_carpeta | carpeta | archivo
    "rechazo_automatico": ["ilegible", "formato_no_admitido", "duplicado"],
}


def vigente(valor: Any) -> dict[str, Any]:
    """El perfil completo: lo publicado sobre los valores por defecto."""
    return {**POR_DEFECTO, **(valor or {})}


def validar(valor: Any) -> dict[str, Any]:
    if not isinstance(valor, dict):
        raise ValueError("El perfil de digitalización debe ser un objeto con sus opciones")
    desconocidas = set(valor) - set(POR_DEFECTO)
    if desconocidas:
        raise ValueError(f"Opciones desconocidas en el perfil: {', '.join(sorted(desconocidas))}")
    p = vigente(valor)
    if not p["modalidades"] or not set(p["modalidades"]) <= {"pdf", "imagenes"}:
        raise ValueError("modalidades: use «pdf», «imagenes» o ambas")
    if not p["formatos"] or not set(p["formatos"]) <= set(FORMATOS):
        raise ValueError(f"formatos: use {', '.join(FORMATOS)}")
    if not isinstance(p["dpi_minimo"], int) or isinstance(p["dpi_minimo"], bool) or not 0 <= p["dpi_minimo"] <= 1200:
        raise ValueError("dpi_minimo: un entero entre 0 y 1200")
    if p["color_minimo"] not in COLOR:
        raise ValueError(f"color_minimo: {', '.join(COLOR)}")
    if not isinstance(p["detectar_blancos"], bool) or not isinstance(p["comparar_folios"], bool):
        raise ValueError("detectar_blancos y comparar_folios son verdadero o falso")
    if not isinstance(p["umbral_blanco"], int | float) or not 0.9 <= float(p["umbral_blanco"]) <= 1:
        raise ValueError("umbral_blanco: un número entre 0.9 y 1")
    if p["identificar_por"] not in ("archivo_o_carpeta", "carpeta", "archivo"):
        raise ValueError("identificar_por: archivo_o_carpeta, carpeta o archivo")
    if not set(p["rechazo_automatico"]) <= set(HALLAZGOS):
        raise ValueError("rechazo_automatico: solo hallazgos conocidos")
    return valor
