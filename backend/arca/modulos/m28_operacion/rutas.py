"""M28 base · Estado del servicio, para monitoreo (sin autenticación y sin datos de ninguna organización)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from arca.api.deps import Sesion
from arca.modelos.base import ahora_utc
from arca.nucleo.config import ajustes

rutas = APIRouter(tags=["M28 · Operación"])


@rutas.get("/estado")
def estado(db: Sesion):
    a = ajustes()
    try:
        db.execute(text("SELECT 1"))
        base_datos = "disponible"
    except Exception:  # noqa: BLE001 - el monitoreo informa, no falla
        base_datos = "no disponible"
    from arca.modulos.m13_ocr import lector  # noqa: PLC0415

    ocr = f"{lector.version()} ({', '.join(x for x in lector.idiomas() if x != 'osd')})" if lector.disponible() else "no disponible"
    cuerpo = {"servicio": a.nombre, "version": a.version, "entorno": a.entorno, "hora_utc": ahora_utc().isoformat(), "base_de_datos": base_datos, "ocr": ocr}
    return JSONResponse(status_code=200 if base_datos == "disponible" else 503, content=cuerpo)
