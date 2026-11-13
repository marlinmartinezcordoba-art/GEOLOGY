"""M13 · API del OCR local: resumen del proyecto, lectura por tandas, texto de cada página y búsqueda en el contenido."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from arca.api.deps import Contexto, requiere
from arca.modelos import RecursoDigital, TextoPagina, UnidadDocumental
from arca.modulos.hoja_control.servicios import unidad_de
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.modulos.m13_ocr import servicios
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/ocr", tags=["M13 · OCR"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Cargador = Annotated[Contexto, Depends(requiere(Permiso.CAPTURAR))]
Elaborador = Annotated[Contexto, Depends(requiere(Permiso.HOJA_CONTROL))]


class Lectura(BaseModel):
    limite: int = Field(default=30, ge=1, le=200, description="Páginas por tanda")
    releer: bool = False


@rutas.get("/resumen")
def resumen(proyecto_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    return servicios.resumen(ctx, obtener_proyecto(ctx, proyecto_id))


@rutas.post("/leer")
def leer_proyecto(proyecto_id: uuid.UUID, ctx: Cargador, limite: int = Query(default=30, ge=1, le=200)) -> dict[str, Any]:
    """Una tanda de OCR sobre las páginas pendientes del proyecto. Se llama de nuevo hasta que no queden."""
    return servicios.leer_proyecto(ctx, obtener_proyecto(ctx, proyecto_id), limite)


@rutas.get("/unidades/{unidad_id}")
def textos(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Lector) -> list[dict[str, Any]]:
    p = obtener_proyecto(ctx, proyecto_id)
    return servicios.textos(ctx, unidad_de(ctx, p, unidad_id))


@rutas.post("/unidades/{unidad_id}/leer")
def leer_unidad(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, datos: Lectura, ctx: Elaborador) -> dict[str, Any]:
    p = obtener_proyecto(ctx, proyecto_id)
    return servicios.leer_unidad(ctx, p, unidad_de(ctx, p, unidad_id), datos.limite, datos.releer)


@rutas.get("/buscar")
def buscar(proyecto_id: uuid.UUID, ctx: Lector, q: str = Query(min_length=3, max_length=200), limite: int = Query(default=50, le=200)) -> list[dict[str, Any]]:
    """Expedientes y páginas cuyo texto leído contiene lo buscado, con el fragmento alrededor."""
    p = obtener_proyecto(ctx, proyecto_id)
    filas = ctx.db.execute(
        select(TextoPagina, RecursoDigital.unidad_id, UnidadDocumental.identificador, UnidadDocumental.nombre)
        .join(RecursoDigital, TextoPagina.recurso_id == RecursoDigital.id).join(UnidadDocumental, RecursoDigital.unidad_id == UnidadDocumental.id)
        .where(TextoPagina.proyecto_id == p.id, TextoPagina.texto.ilike(f"%{q.strip()}%")).limit(limite)
    ).all()
    salida = []
    for t, unidad_id, identificador, nombre in filas:
        i = t.texto.lower().find(q.strip().lower())
        salida.append({"unidad_id": unidad_id, "identificador": identificador, "nombre": nombre, "recurso_id": t.recurso_id, "pagina_en_archivo": t.pagina,
                       "fragmento": t.texto[max(0, i - 60): i + len(q) + 60].replace("\n", " "), "confianza": t.confianza})
    return salida
