"""M23 · API de consulta: búsqueda en los proyectos del alcance, ficha de la unidad, páginas y exportación."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from arca.api.deps import Contexto, requiere
from arca.modelos import ArchivoDigital, RecursoDigital, UnidadDocumental
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.modulos.m10_digitalizacion.paginas import imagen_pagina, paginas
from arca.modulos.m23_consulta import servicios
from arca.nucleo import almacen
from arca.nucleo.errores import NoEncontrado
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/consulta", tags=["M23 · Consulta"])
Consultor = Annotated[Contexto, Depends(requiere(Permiso.CONSULTAR))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _proyectos(ctx, proyecto_id: uuid.UUID | None):
    return [obtener_proyecto(ctx, proyecto_id)] if proyecto_id else servicios.proyectos_visibles(ctx)


Filtros = dict[str, Any]


def filtros(q: str | None = None, proyecto_id: uuid.UUID | None = None, codigo: str | None = None, dependencia: str | None = None, caja: str | None = None,
            fase: str | None = None, desde: date | None = None, hasta: date | None = None, digitalizadas: bool = False, con_hoja: bool = False,
            descritas: bool = False, fuentes: list[str] | None = Query(default=None)) -> Filtros:
    f = {"q": q, "proyecto_id": proyecto_id, "codigo": codigo, "dependencia": dependencia, "caja": caja, "fase": fase, "desde": desde, "hasta": hasta,
         "digitalizadas": digitalizadas, "con_hoja": con_hoja, "descritas": descritas, "fuentes": fuentes or []}
    servicios.validar_filtros(f)
    return f


@rutas.get("/proyectos")
def proyectos(ctx: Consultor) -> list[dict[str, Any]]:
    """Los proyectos en los que la persona puede consultar."""
    return [{"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "entidad": p.entidad_cliente} for p in servicios.proyectos_visibles(ctx)]


@rutas.get("/buscar")
def buscar(ctx: Consultor, f: Annotated[Filtros, Depends(filtros)], desplazamiento: int = Query(default=0, ge=0), limite: int = Query(default=50, le=200)) -> dict[str, Any]:
    return servicios.buscar(ctx, _proyectos(ctx, f["proyecto_id"]), f, desplazamiento, limite, ctx.puede(Permiso.CONSULTA_RESERVADA))


@rutas.get("/exportar")
def exportar(ctx: Consultor, f: Annotated[Filtros, Depends(filtros)]):
    datos = servicios.exportar(ctx, _proyectos(ctx, f["proyecto_id"]), f, ctx.puede(Permiso.CONSULTA_RESERVADA))
    return Response(content=datos, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="Consulta_ARCA_{date.today():%Y%m%d}.xlsx"', "Cache-Control": "no-store"})


def _unidad(ctx, proyecto_id: uuid.UUID, unidad_id: uuid.UUID):
    p = obtener_proyecto(ctx, proyecto_id)
    u = ctx.db.get(UnidadDocumental, unidad_id)
    if u is None or u.proyecto_id != p.id:
        raise NoEncontrado("La unidad no existe en el proyecto")
    return p, u


@rutas.get("/proyectos/{proyecto_id}/unidades/{unidad_id}")
def ficha(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Consultor) -> dict[str, Any]:
    """Todo lo validado de la unidad en un solo lugar. Abrirla queda en la auditoría."""
    p, u = _unidad(ctx, proyecto_id, unidad_id)
    return servicios.ficha(ctx, p, u, ctx.puede(Permiso.CONSULTA_RESERVADA))


@rutas.get("/proyectos/{proyecto_id}/unidades/{unidad_id}/paginas/{n}/imagen")
def imagen(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, n: int, ctx: Consultor, ancho: int = Query(default=1400, ge=200, le=2400)):
    _, u = _unidad(ctx, proyecto_id, unidad_id)
    servicios.exigir_contenido(ctx, u, ctx.puede(Permiso.CONSULTA_RESERVADA))
    return Response(content=imagen_pagina(ctx, u, n, ancho), media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@rutas.get("/proyectos/{proyecto_id}/unidades/{unidad_id}/paginas/{n}/original")
def original(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, n: int, ctx: Consultor):
    p, u = _unidad(ctx, proyecto_id, unidad_id)
    servicios.exigir_contenido(ctx, u, ctx.puede(Permiso.CONSULTA_RESERVADA))
    lista = paginas(ctx, u)
    if not 1 <= n <= len(lista):
        raise NoEncontrado("La página no existe en el expediente")
    r = ctx.db.get(RecursoDigital, lista[n - 1]["recurso_id"])
    a = ctx.db.get(ArchivoDigital, r.archivo_id)
    datos = almacen.leer(a.clave_almacen, ctx.tenant_id)
    if almacen.huella(datos) != a.sha256:
        raise NoEncontrado("El archivo no coincide con su huella: avise al administrador")
    ctx.auditar(accion="DESCARGAR_ORIGINAL_CONSULTA", objeto="RecursoDigital", objeto_id=r.id, detalle=f"{p.codigo} · {u.identificador} · página {n}")
    ctx.db.commit()
    return Response(content=datos, media_type=a.mime, headers={"Content-Disposition": f'inline; filename="{a.nombre_original.replace(chr(34), "")}"', "X-Content-SHA256": a.sha256})
