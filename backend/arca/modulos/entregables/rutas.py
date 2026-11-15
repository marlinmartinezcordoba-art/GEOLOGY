"""Entregables · API de plantillas versionadas (organización y proyecto) y expedición de FUID y rótulos."""

import json
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from arca.api.deps import Contexto, requiere
from arca.modulos.entregables import servicios
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.nucleo.errores import DatosInvalidos, NoEncontrado
from arca.nucleo.permisos import Permiso

plantillas = APIRouter(prefix="/plantillas", tags=["Entregables · Plantillas"])
expedicion = APIRouter(prefix="/proyectos/{proyecto_id}/entregables", tags=["Entregables · Expedición"])
Gestor = Annotated[Contexto, Depends(requiere(Permiso.PLANTILLAS))]
Expedidor = Annotated[Contexto, Depends(requiere(Permiso.EXPEDIR))]
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class PlantillaNueva(BaseModel):
    tipo: str
    nombre: str = Field(min_length=3, max_length=200)
    descripcion: str = ""
    proyecto_id: uuid.UUID | None = Field(default=None, description="Vacío = para toda la organización")


class VersionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    codigo_formato: str
    campos: list[str]
    valores_fijos: dict[str, Any]
    vigente_desde: datetime
    estado: str
    motivo: str
    creado_en: datetime


class PlantillaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    nombre: str
    descripcion: str
    proyecto_id: uuid.UUID | None
    creado_en: datetime
    versiones: list[VersionSalida] = []


class Expedir(BaseModel):
    tipo: str
    cajas: list[str] | None = Field(default=None, description="Solo estas cajas; vacío = todas")
    lote: str | None = None
    plantilla_id: uuid.UUID | None = Field(default=None, description="Vacío = la vigente del proyecto o, si no hay, la de la organización")


class ExpedicionSalida(BaseModel):
    id: uuid.UUID
    tipo: str
    elementos: int
    filtro: dict[str, Any]
    creado_en: datetime
    plantilla_version: int
    codigo_formato: str
    nombre_archivo: str
    sha256: str


def _salida(ctx, p) -> PlantillaSalida:
    s = PlantillaSalida.model_validate(p)
    s.versiones = [VersionSalida.model_validate(v) for v in servicios.versiones(ctx, p)]
    return s


def _descarga(contenido: bytes, nombre: str, sha256: str | None = None) -> Response:
    cabeceras = {"Content-Disposition": f'attachment; filename="{nombre.replace(chr(34), "")}"', "Cache-Control": "no-store"}
    if sha256:
        cabeceras["X-Content-SHA256"] = sha256
    return Response(content=contenido, media_type=XLSX, headers=cabeceras)


@plantillas.get("/tipos")
def tipos(_: Lector) -> dict[str, Any]:
    """Tipos de plantilla y los marcadores que admite cada uno (encabezado y fila)."""
    return {k: {"nombre": t["nombre"], "encabezado": t["encabezado"], "fila": t["fila"]} for k, t in servicios.TIPOS.items()}


@plantillas.get("/tipos/{tipo}/base")
def base(tipo: str, _: Lector):
    """Formato de partida sin datos, con los marcadores ya puestos, para ajustarlo a la imagen de la entidad."""
    return _descarga(servicios.plantilla_base(tipo), f"Plantilla_base_{tipo}.xlsx")


@plantillas.get("", response_model=list[PlantillaSalida])
def listar(ctx: Lector, proyecto_id: uuid.UUID | None = None):
    return [_salida(ctx, p) for p in servicios.listar(ctx, proyecto_id)]


@plantillas.post("", status_code=status.HTTP_201_CREATED, response_model=PlantillaSalida)
def crear(datos: PlantillaNueva, ctx: Gestor):
    return _salida(ctx, servicios.crear(ctx, datos.tipo, datos.nombre, datos.descripcion, datos.proyecto_id))


@plantillas.post("/{plantilla_id}/versiones", status_code=status.HTTP_201_CREATED, response_model=PlantillaSalida)
async def publicar(
    plantilla_id: uuid.UUID,
    ctx: Gestor,
    archivo: UploadFile = File(...),
    motivo: str = Form(..., min_length=5),
    codigo_formato: str = Form(default=""),
    valores_fijos: str = Form(default="{}", description='JSON: {"oficina_productora": "Archivo central"}'),
    vigente_desde: datetime | None = Form(default=None),
):
    try:
        fijos = json.loads(valores_fijos or "{}")
        assert isinstance(fijos, dict)
    except (ValueError, AssertionError) as e:
        raise DatosInvalidos("Los valores fijos deben ser un objeto JSON") from e
    p = servicios.obtener(ctx, plantilla_id)
    servicios.publicar_version(ctx, p, await archivo.read(), archivo.filename or "plantilla.xlsx", motivo, codigo_formato, fijos, vigente_desde)
    return _salida(ctx, p)


@plantillas.get("/versiones/{version_id}/archivo")
def descargar_version(version_id: uuid.UUID, ctx: Lector):
    datos, archivo = servicios.archivo_version(ctx, version_id)
    return _descarga(datos, archivo.nombre_original, archivo.sha256)


@expedicion.post("", status_code=status.HTTP_201_CREATED, response_model=ExpedicionSalida)
def expedir(proyecto_id: uuid.UUID, datos: Expedir, ctx: Expedidor):
    proyecto = obtener_proyecto(ctx, proyecto_id)
    servicios.tipo_o_error(datos.tipo)
    if datos.tipo == "acta_eliminacion":
        raise DatosInvalidos("El acta de eliminación se expide desde su proceso, en Disposición final")
    if datos.tipo == "descripcion_isadg":
        raise DatosInvalidos("La base de descripción ISAD(G) se expide desde Descripción, con lo aprobado")
    if datos.tipo == "hoja_control":
        raise DatosInvalidos("La hoja de control se expide desde el expediente, cuando está verificada")
    e = servicios.expedir(ctx, proyecto, datos.tipo, datos.cajas, datos.lote, datos.plantilla_id)
    return next(x for x in listar_expediciones(proyecto_id, ctx, limite=200) if x.id == e.id)


@expedicion.get("", response_model=list[ExpedicionSalida])
def listar_expediciones(proyecto_id: uuid.UUID, ctx: Lector, limite: int = Query(default=50, le=200)):
    proyecto = obtener_proyecto(ctx, proyecto_id)
    return [
        ExpedicionSalida(id=e.id, tipo=e.tipo, elementos=e.elementos, filtro=e.filtro, creado_en=e.creado_en, plantilla_version=v.version,
                         codigo_formato=v.codigo_formato, nombre_archivo=a.nombre_original, sha256=a.sha256)
        for e, v, a in servicios.expediciones(ctx, proyecto)[:limite]
    ]


@expedicion.get("/{expedicion_id}/archivo")
def descargar(proyecto_id: uuid.UUID, expedicion_id: uuid.UUID, ctx: Lector):
    datos, archivo = servicios.archivo_de(ctx, obtener_proyecto(ctx, proyecto_id), expedicion_id)
    ctx.auditar(accion="DESCARGAR_EXPEDICION", objeto="Expedicion", objeto_id=expedicion_id, detalle=archivo.nombre_original)
    ctx.db.commit()
    return _descarga(datos, archivo.nombre_original, archivo.sha256)


@expedicion.get("/{expedicion_id}/pdf")
def descargar_pdf(proyecto_id: uuid.UUID, expedicion_id: uuid.UUID, ctx: Lector):
    """El entregable en PDF/A-2b con el logo de la entidad (si el proyecto lo tiene)."""
    contenido, nombre, conforme = servicios.pdf_de_expedicion(ctx, obtener_proyecto(ctx, proyecto_id), expedicion_id)
    return Response(contenido, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nombre}"', "X-PDFA": "2b" if conforme else "no"})


logo = APIRouter(prefix="/proyectos/{proyecto_id}/logo", tags=["Entregables · Logo de la entidad"])
Director = Annotated[Contexto, Depends(requiere(Permiso.PROYECTOS))]


@logo.put("", status_code=status.HTTP_201_CREATED)
async def subir_logo(proyecto_id: uuid.UUID, ctx: Director, archivo: UploadFile = File(...)) -> dict[str, Any]:
    a = servicios.guardar_logo(ctx, obtener_proyecto(ctx, proyecto_id), await archivo.read(servicios.MAX_LOGO + 1), archivo.filename or "logo")
    return {"archivo_id": a.id, "sha256": a.sha256}


@logo.get("")
def ver_logo(proyecto_id: uuid.UUID, ctx: Lector):
    datos = servicios.logo_de(ctx, obtener_proyecto(ctx, proyecto_id))
    if datos is None:
        raise NoEncontrado("El proyecto no tiene logo")
    return Response(datos, media_type="image/png" if datos.startswith(b"\x89PNG") else "image/jpeg", headers={"Cache-Control": "private, max-age=300"})
