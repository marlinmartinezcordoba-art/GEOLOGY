"""Informe de avance · API: el informe del periodo en Excel o en PDF/A con el logo de la entidad."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from arca.api.deps import Contexto, requiere
from arca.modulos.entregables.servicios import logo_de
from arca.modulos.informes import servicios
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/informe-avance", tags=["Informe de avance"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.PRODUCTIVIDAD_LEER))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@rutas.get("")
def informe(proyecto_id: uuid.UUID, ctx: Lector, desde: date = Query(...), hasta: date = Query(...), formato: str = Query(default="pdf", pattern="^(pdf|xlsx|json)$")):
    p = obtener_proyecto(ctx, proyecto_id)
    d = servicios.datos(ctx, p, desde, hasta)
    nombre = f"Informe_avance_{p.codigo}_{desde.isoformat()}_{hasta.isoformat()}"
    ctx.auditar(accion="EXPEDIR_INFORME_AVANCE", objeto="Proyecto", objeto_id=p.id, detalle=f"{p.codigo} · {desde.isoformat()} a {hasta.isoformat()} · {formato}")
    ctx.db.commit()
    if formato == "json":
        return d
    if formato == "xlsx":
        return Response(servicios.excel(d), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nombre}.xlsx"'})
    contenido, conforme = servicios.pdf_informe(d, logo_de(ctx, p), p.entidad_cliente)
    return Response(contenido, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nombre}.pdf"', "X-PDFA": "2b" if conforme else "no"})
