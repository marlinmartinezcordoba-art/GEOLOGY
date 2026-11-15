"""Paquete de entrega · API: pedir un paquete (se arma en la cola), ver los paquetes y descargar el ZIP."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from arca.api.deps import Contexto, requiere
from arca.modulos.entrega import pdfa, servicios
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.nucleo.config import ajustes
from arca.nucleo.errores import DatosInvalidos
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/entrega", tags=["Paquete de entrega"])
Expedidor = Annotated[Contexto, Depends(requiere(Permiso.EXPEDIR))]
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]


class Solicitud(BaseModel):
    cajas: list[str] = Field(default_factory=list, max_length=500)
    lote: str = ""
    solo_listos: bool = True


@rutas.post("/paquetes", status_code=status.HTTP_202_ACCEPTED)
def solicitar(proyecto_id: uuid.UUID, datos: Solicitud, ctx: Expedidor) -> dict[str, Any]:
    p = servicios.solicitar(ctx, obtener_proyecto(ctx, proyecto_id), datos.cajas, datos.lote.strip(), datos.solo_listos)
    return {"id": p.id, "numero": p.numero, "estado": p.estado, "unidades": p.unidades, "pendientes": len(p.pendientes)}


@rutas.get("/paquetes")
def listar(proyecto_id: uuid.UUID, ctx: Lector) -> list[dict[str, Any]]:
    return servicios.listar(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.get("/paquetes/{paquete_id}/archivo")
def descargar(proyecto_id: uuid.UUID, paquete_id: uuid.UUID, ctx: Expedidor) -> Response:
    datos, a = servicios.archivo(ctx, obtener_proyecto(ctx, proyecto_id), paquete_id)
    return Response(datos, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{a.nombre_original}"', "X-SHA256": a.sha256})


@rutas.post("/validar-pdfa")
async def validar_pdfa(proyecto_id: uuid.UUID, ctx: Lector, archivo: UploadFile = File(...), nivel: str = Form(default=pdfa.NIVEL)) -> dict[str, Any]:
    """Valida un PDF contra PDF/A-1b, 2b o 3b (por ejemplo, el que entregó un proveedor). No lo guarda ni lo modifica."""
    p = obtener_proyecto(ctx, proyecto_id)
    limite = ajustes().max_mb_por_archivo * 1024 * 1024
    contenido = await archivo.read(limite + 1)
    if len(contenido) > limite:
        raise DatosInvalidos(f"El archivo supera {ajustes().max_mb_por_archivo} MB")
    if not contenido.startswith(b"%PDF"):
        raise DatosInvalidos(f"«{archivo.filename}» no es un PDF")
    if nivel not in ("1b", "2b", "3b"):
        raise DatosInvalidos("Nivel PDF/A no admitido: use 1b, 2b o 3b")
    r = pdfa.validar(contenido, nivel)
    ctx.auditar(accion="VALIDAR_PDFA", objeto="Proyecto", objeto_id=p.id, detalle=f"{p.codigo} · «{(archivo.filename or '')[:120]}» · {r['nivel']} · {r['veredicto']}")
    ctx.db.commit()
    return {"archivo": archivo.filename, "bytes": len(contenido), **r}
