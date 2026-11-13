"""Disposición final · API: plan a la fecha de corte y procesos de eliminación, selección y digitalización."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from arca.api.deps import Contexto, requiere
from arca.modelos import ArchivoDigital
from arca.modulos.disposicion import servicios
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.nucleo.errores import NoEncontrado
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/disposicion", tags=["Disposición final"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Gestor = Annotated[Contexto, Depends(requiere(Permiso.DISPONER))]
Aprobador = Annotated[Contexto, Depends(requiere(Permiso.APROBAR_DISPOSICION))]


class Nuevo(BaseModel):
    tipo: str = Field(description="eliminacion | seleccion | digitalizacion")
    fecha_corte: date | None = None
    serie: str = Field(default="", description="Código de la serie o subserie; vacío = todas")
    observaciones: str = ""


class Unidades(BaseModel):
    unidades: list[uuid.UUID] = Field(min_length=1, max_length=10000)


class Retiro(Unidades):
    motivo: str = Field(min_length=5)


class Marca(Unidades):
    seleccionada: bool


class Muestreo(BaseModel):
    porcentaje: float = Field(gt=0, le=100)
    semilla: int | None = Field(default=None, description="Vacío = ARCA la elige y la registra")
    criterio: str = ""


class Aprobacion(BaseModel):
    acta_comite: str = Field(min_length=3, max_length=200)
    fecha_acta: date
    motivo: str = Field(min_length=5)


class Publicacion(BaseModel):
    inicio: date
    dias: int = Field(ge=1, le=365, description="Plazo de publicación que fije la entidad según la norma vigente")
    enlace: str = Field(min_length=5, max_length=500)


class Ejecucion(BaseModel):
    acta_numero: str = ""
    metodo: str = ""
    destino_fisico: str | None = Field(default=None, description="Solo digitalización: conservar | eliminar")


class Motivo(BaseModel):
    motivo: str = Field(min_length=5)


class ProcesoSalida(BaseModel):
    id: uuid.UUID
    numero: int
    tipo: str
    estado: str
    fecha_corte: date
    observaciones: str
    origen_id: uuid.UUID | None
    comite_acta: str | None
    comite_fecha: date | None
    aprobado_en: datetime | None
    publicacion_inicio: date | None
    publicacion_dias: int | None
    publicacion_fin: date | None
    publicacion_enlace: str | None
    muestreo: dict[str, Any]
    destino_fisico: str | None
    metodo: str | None
    acta_numero: str | None
    ejecutado_en: datetime | None
    novedad: str
    creado_en: datetime
    creado_por: uuid.UUID | None
    resumen: dict[str, int]


def _salida(ctx, p) -> ProcesoSalida:
    campos = {k: getattr(p, k) for k in ProcesoSalida.model_fields if k not in ("resumen", "publicacion_fin")}
    return ProcesoSalida(**campos, publicacion_fin=servicios.fin_publicacion(p), resumen=servicios.resumen(ctx, p))


def _p(ctx, proyecto_id, proceso_id):
    pr = obtener_proyecto(ctx, proyecto_id)
    return pr, servicios.obtener(ctx, pr, proceso_id)


@rutas.get("/plan")
def plan(proyecto_id: uuid.UUID, ctx: Lector, fecha_corte: date | None = None) -> dict[str, Any]:
    return servicios.plan(ctx, obtener_proyecto(ctx, proyecto_id), fecha_corte or date.today())


@rutas.get("", response_model=list[ProcesoSalida])
def listar(proyecto_id: uuid.UUID, ctx: Lector):
    return [_salida(ctx, p) for p in servicios.listar(ctx, obtener_proyecto(ctx, proyecto_id))]


@rutas.post("", status_code=status.HTTP_201_CREATED, response_model=ProcesoSalida)
def crear(proyecto_id: uuid.UUID, datos: Nuevo, ctx: Gestor):
    pr = obtener_proyecto(ctx, proyecto_id)
    return _salida(ctx, servicios.crear(ctx, pr, datos.tipo, datos.fecha_corte or date.today(), datos.serie.strip(), datos.observaciones))


@rutas.get("/{proceso_id}")
def ver(proyecto_id: uuid.UUID, proceso_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    _, p = _p(ctx, proyecto_id, proceso_id)
    faltan = servicios.avisos(ctx, p)
    return {"proceso": _salida(ctx, p), "unidades": [
        {"unidad_id": u.id, "identificador": u.identificador, "nombre": u.nombre, "caja": u.caja, "carpeta": u.carpeta, "folios": u.folios, "fecha_inicial": u.fecha_inicial,
         "fecha_final": u.fecha_final, "fase": u.fase, "estado": e.estado, "aviso": faltan.get(u.id) or e.aviso, "observacion": e.observacion}
        for e, u in servicios.elementos(ctx, p)]}


@rutas.post("/{proceso_id}/retirar")
def retirar(proyecto_id: uuid.UUID, proceso_id: uuid.UUID, datos: Retiro, ctx: Gestor) -> dict[str, int]:
    pr, p = _p(ctx, proyecto_id, proceso_id)
    return {"retiradas": servicios.retirar(ctx, pr, p, datos.unidades, datos.motivo)}


@rutas.post("/{proceso_id}/muestrear")
def muestrear(proyecto_id: uuid.UUID, proceso_id: uuid.UUID, datos: Muestreo, ctx: Gestor) -> dict[str, Any]:
    pr, p = _p(ctx, proyecto_id, proceso_id)
    return servicios.muestrear(ctx, pr, p, datos.porcentaje, datos.semilla, datos.criterio)


@rutas.post("/{proceso_id}/marcar")
def marcar(proyecto_id: uuid.UUID, proceso_id: uuid.UUID, datos: Marca, ctx: Gestor) -> dict[str, int]:
    pr, p = _p(ctx, proyecto_id, proceso_id)
    return {"marcadas": servicios.marcar(ctx, pr, p, datos.unidades, datos.seleccionada)}


@rutas.post("/{proceso_id}/aprobar", response_model=ProcesoSalida)
def aprobar(proyecto_id: uuid.UUID, proceso_id: uuid.UUID, datos: Aprobacion, ctx: Aprobador):
    pr, p = _p(ctx, proyecto_id, proceso_id)
    return _salida(ctx, servicios.aprobar(ctx, pr, p, datos.acta_comite, datos.fecha_acta, datos.motivo))


@rutas.post("/{proceso_id}/publicar", response_model=ProcesoSalida)
def publicar(proyecto_id: uuid.UUID, proceso_id: uuid.UUID, datos: Publicacion, ctx: Gestor):
    pr, p = _p(ctx, proyecto_id, proceso_id)
    return _salida(ctx, servicios.publicar(ctx, pr, p, datos.inicio, datos.dias, datos.enlace))


@rutas.post("/{proceso_id}/ejecutar")
def ejecutar(proyecto_id: uuid.UUID, proceso_id: uuid.UUID, datos: Ejecucion, ctx: Gestor) -> dict[str, Any]:
    pr, p = _p(ctx, proyecto_id, proceso_id)
    return servicios.ejecutar(ctx, pr, p, datos.acta_numero, datos.metodo, datos.destino_fisico)


@rutas.post("/{proceso_id}/anular", response_model=ProcesoSalida)
def anular(proyecto_id: uuid.UUID, proceso_id: uuid.UUID, datos: Motivo, ctx: Gestor):
    pr, p = _p(ctx, proyecto_id, proceso_id)
    return _salida(ctx, servicios.anular(ctx, pr, p, datos.motivo))


@rutas.post("/{proceso_id}/documentos/{cual}", status_code=status.HTTP_201_CREATED)
def documento(proyecto_id: uuid.UUID, proceso_id: uuid.UUID, cual: str, ctx: Lector) -> dict[str, Any]:
    """«inventario» (FUID) o «acta» (acta de eliminación), sobre la plantilla vigente de la entidad. Se descarga por Entregables."""
    pr, p = _p(ctx, proyecto_id, proceso_id)
    if cual not in ("inventario", "acta"):
        raise NoEncontrado("Documento desconocido")
    e = servicios.documento(ctx, pr, p, cual)
    a = ctx.db.get(ArchivoDigital, e.archivo_id)
    return {"expedicion_id": e.id, "elementos": e.elementos, "nombre_archivo": a.nombre_original, "sha256": a.sha256}
