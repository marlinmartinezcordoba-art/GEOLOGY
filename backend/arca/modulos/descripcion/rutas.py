"""Configuración de procesos por lote y descripción ISAD(G) · API."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from arca.api.deps import Contexto, requiere
from arca.modelos import ArchivoDigital
from arca.modulos.descripcion import servicios
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.modulos.procesos.servicios import procesos_de
from arca.nucleo.errores import NoEncontrado
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}", tags=["Descripción ISAD(G)"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Descriptor = Annotated[Contexto, Depends(requiere(Permiso.DESCRIBIR))]
Aprobador = Annotated[Contexto, Depends(requiere(Permiso.APROBAR_DESCRIPCION))]
Expedidor = Annotated[Contexto, Depends(requiere(Permiso.EXPEDIR))]


class Cambios(BaseModel):
    campos: dict[str, str]


class Elemento(BaseModel):
    elemento: str


class Devolucion(BaseModel):
    motivo: str = Field(min_length=5)
    observaciones: dict[str, str] = {}


class Motivo(BaseModel):
    motivo: str = Field(min_length=5)


def _detalle(ctx, p, u) -> dict[str, Any]:
    d = servicios.descripcion_de(ctx, u)
    procesos = procesos_de(ctx, p, u)
    _, _, avisos = servicios.calcular(ctx, p, u, procesos)
    return {
        "unidad": {"id": u.id, "identificador": u.identificador, "nombre": u.nombre, "caja": u.caja, "carpeta": u.carpeta, "fase": u.fase},
        "procesos": procesos,
        "elementos": [{"clave": k, "numero": n, "etiqueta": e, "area": a, "editable": ed} for k, n, e, a, ed in servicios.ELEMENTOS],
        "descripcion": None if d is None else {"id": d.id, "estado": d.estado, "campos": d.campos, "origen": d.origen, "observaciones": d.observaciones,
                                                "novedad": d.novedad, "creado_por": d.creado_por, "enviada_por": d.enviada_por, "aprobada_en": d.aprobada_en},
        "revision": servicios.revisar(ctx, p, u, d) if d else None,
        "avisos": avisos,
    }


def _u(ctx, proyecto_id, unidad_id):
    p = obtener_proyecto(ctx, proyecto_id)
    return p, servicios.unidad_de(ctx, p, unidad_id)


def _d(ctx, proyecto_id, unidad_id):
    p, u = _u(ctx, proyecto_id, unidad_id)
    d = servicios.descripcion_de(ctx, u)
    if d is None:
        raise NoEncontrado("La unidad no tiene descripción")
    return p, u, d


@rutas.get("/descripciones")
def bandeja(proyecto_id: uuid.UUID, ctx: Lector, estado: str | None = None, q: str | None = None, desplazamiento: int = Query(default=0, ge=0),
            limite: int = Query(default=100, le=500)) -> dict[str, Any]:
    total, filas, cuenta = servicios.bandeja(ctx, obtener_proyecto(ctx, proyecto_id), estado, q, desplazamiento, limite)
    return {"total": total, "filas": filas, "cuenta": cuenta}


@rutas.post("/descripciones/expedir", status_code=status.HTTP_201_CREATED)
def expedir(proyecto_id: uuid.UUID, ctx: Expedidor) -> dict[str, Any]:
    """La base de descripción con todo lo aprobado, en la plantilla de la entidad; se descarga por Entregables."""
    e = servicios.expedir(ctx, obtener_proyecto(ctx, proyecto_id))
    a = ctx.db.get(ArchivoDigital, e.archivo_id)
    return {"expedicion_id": e.id, "elementos": e.elementos, "nombre_archivo": a.nombre_original, "sha256": a.sha256}


@rutas.get("/descripciones/unidades/{unidad_id}")
def ver(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    p, u = _u(ctx, proyecto_id, unidad_id)
    return _detalle(ctx, p, u)


@rutas.post("/descripciones/unidades/{unidad_id}", status_code=status.HTTP_201_CREATED)
def crear(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Descriptor) -> dict[str, Any]:
    p, u = _u(ctx, proyecto_id, unidad_id)
    servicios.crear(ctx, p, u)
    return _detalle(ctx, p, u)


@rutas.patch("/descripciones/unidades/{unidad_id}")
def editar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, datos: Cambios, ctx: Descriptor) -> dict[str, Any]:
    p, u, d = _d(ctx, proyecto_id, unidad_id)
    servicios.editar(ctx, p, d, datos.campos)
    return _detalle(ctx, p, u)


@rutas.post("/descripciones/unidades/{unidad_id}/confirmar")
def confirmar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, datos: Elemento, ctx: Descriptor) -> dict[str, Any]:
    p, u, d = _d(ctx, proyecto_id, unidad_id)
    servicios.confirmar(ctx, p, d, datos.elemento)
    return _detalle(ctx, p, u)


@rutas.post("/descripciones/unidades/{unidad_id}/recalcular")
def recalcular(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Descriptor) -> dict[str, Any]:
    """Vuelve a tomar lo deducido (hoja verificada, clasificación, digitalización). Lo escrito por una persona se conserva."""
    p, u, d = _d(ctx, proyecto_id, unidad_id)
    servicios.recalcular(ctx, p, u, d)
    return _detalle(ctx, p, u)


@rutas.post("/descripciones/unidades/{unidad_id}/enviar")
def enviar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Descriptor) -> dict[str, Any]:
    p, u, d = _d(ctx, proyecto_id, unidad_id)
    servicios.enviar(ctx, p, u, d)
    return _detalle(ctx, p, u)


@rutas.post("/descripciones/unidades/{unidad_id}/aprobar")
def aprobar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Aprobador) -> dict[str, Any]:
    p, u, d = _d(ctx, proyecto_id, unidad_id)
    servicios.aprobar(ctx, p, u, d)
    return _detalle(ctx, p, u)


@rutas.post("/descripciones/unidades/{unidad_id}/devolver")
def devolver(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, datos: Devolucion, ctx: Aprobador) -> dict[str, Any]:
    p, u, d = _d(ctx, proyecto_id, unidad_id)
    servicios.devolver(ctx, p, u, d, datos.observaciones, datos.motivo)
    return _detalle(ctx, p, u)


@rutas.post("/descripciones/unidades/{unidad_id}/reabrir")
def reabrir(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, datos: Motivo, ctx: Aprobador) -> dict[str, Any]:
    p, u, d = _d(ctx, proyecto_id, unidad_id)
    servicios.reabrir(ctx, p, d, datos.motivo)
    return _detalle(ctx, p, u)
