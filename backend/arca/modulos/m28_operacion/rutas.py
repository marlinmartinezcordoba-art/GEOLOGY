"""M28 base · Estado del servicio, para monitoreo (sin autenticación y sin datos de ninguna organización).

Responde 503 si la base de datos o el almacén no responden, para que el monitor (y el orquestador de contenedores)
lo detecte. `alertas` dice en palabras lo que hay que atender: cola atascada, trabajos con error, poco disco,
archivos sin cifrar en producción.
"""

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
    from arca.nucleo import almacen  # noqa: PLC0415

    archivos = almacen.estado()
    alertas, cola = [], {}
    if base_datos == "disponible":
        from sqlalchemy import func, select  # noqa: PLC0415

        from arca.modelos import Trabajo  # noqa: PLC0415

        cola = dict(db.execute(select(Trabajo.estado, func.count()).group_by(Trabajo.estado)).all())
        mas_antiguo = db.scalar(select(func.min(Trabajo.creado_en)).where(Trabajo.estado == "pendiente"))
        if mas_antiguo is not None:
            minutos = (ahora_utc() - (mas_antiguo if mas_antiguo.tzinfo else mas_antiguo.replace(tzinfo=ahora_utc().tzinfo))).total_seconds() / 60
            cola["minutos_del_mas_antiguo"] = round(minutos, 1)
            if minutos > a.minutos_alerta_cola:
                alertas.append(f"La cola de trabajos tiene pendientes de hace {round(minutos)} minutos: revise que el trabajador esté en marcha")
        if cola.get("error"):
            alertas.append(f"{cola['error']} trabajos con error: revíselos en el tablero del flujo de cada proyecto")
    if not archivos.get("disponible"):
        alertas.append("El almacén de archivos no responde")
    if archivos.get("libre_gb") is not None and archivos["libre_gb"] < a.gb_minimos_libres:
        alertas.append(f"Quedan {archivos['libre_gb']} GB libres en el almacén")
    if a.entorno == "produccion" and not archivos.get("cifrado"):
        alertas.append("Los archivos nuevos no se están cifrando")
    if ocr == "no disponible":
        alertas.append("El OCR no está instalado en este servidor")
    archivos.pop("error", None)
    cuerpo = {"servicio": a.nombre, "version": a.version, "entorno": a.entorno, "hora_utc": ahora_utc().isoformat(), "base_de_datos": base_datos, "ocr": ocr,
              "almacen": archivos, "cola": cola, "alertas": alertas}
    sano = base_datos == "disponible" and archivos.get("disponible")
    return JSONResponse(status_code=200 if sano else 503, content=cuerpo)
