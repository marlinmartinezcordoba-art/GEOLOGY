"""M04 · API de instrumentos archivísticos del proyecto (TRD, TVD, CCD) con versiones y aprobación."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from arca.api.deps import Contexto, requiere
from arca.modelos import ArchivoDigital
from arca.modulos.m04_instrumentos import clasificacion, lector, servicios
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.nucleo import almacen
from arca.nucleo.errores import DatosInvalidos
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/instrumentos", tags=["M04 · Instrumentos archivísticos"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INSTRUMENTOS_LEER))]
Gestor = Annotated[Contexto, Depends(requiere(Permiso.INSTRUMENTOS))]
Aprobador = Annotated[Contexto, Depends(requiere(Permiso.INSTRUMENTOS_APROBAR))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class InstrumentoNuevo(BaseModel):
    tipo: str = Field(description="TRD | TVD | CCD")
    nombre: str = Field(min_length=3, max_length=200)
    descripcion: str = ""
    periodo_desde: date | None = None
    periodo_hasta: date | None = None


class VersionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    estado: str
    totales: dict[str, int]
    errores: list[str]
    avisos: list[str]
    correcciones: list[str]
    motivo: str
    acto_administrativo: str | None
    fecha_acto: date | None
    convalidacion: str | None
    vigente_desde: datetime | None
    creado_en: datetime
    creado_por: uuid.UUID | None
    aprobado_en: datetime | None
    aprobado_por: uuid.UUID | None


class InstrumentoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    nombre: str
    descripcion: str
    periodo_desde: date | None
    periodo_hasta: date | None
    creado_en: datetime
    versiones: list[VersionSalida] = []


class ElementoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nivel: str
    codigo: str
    nombre: str
    codigo_dependencia: str
    padre: str | None
    tipos_documentales: list[str]
    retencion_gestion: int | None
    retencion_central: int | None
    disposicion: str | None
    soporte: str | None
    procedimiento: str
    acceso: str
    hoja: str
    fila: int | None


class DetalleVersion(VersionSalida):
    nombre_archivo: str
    sha256: str
    elementos: list[ElementoSalida]


class Aprobacion(BaseModel):
    acto_administrativo: str = Field(min_length=3, max_length=200, description="Resolución o acuerdo que adopta el instrumento")
    fecha_acto: date
    convalidacion: str = Field(default="", description="Concepto o certificado de convalidación del consejo de archivos, si existe")
    vigente_desde: datetime | None = Field(default=None, description="Vacío = desde ahora; futura = queda programada")
    motivo: str = Field(min_length=5)


class Motivo(BaseModel):
    motivo: str = Field(min_length=5)


def _salida(ctx, i) -> InstrumentoSalida:
    s = InstrumentoSalida.model_validate(i)
    s.versiones = [VersionSalida.model_validate(v) for v in servicios.versiones(ctx, i)]
    return s


def _contexto(ctx, proyecto_id, instrumento_id):
    p = obtener_proyecto(ctx, proyecto_id)
    return p, servicios.obtener(ctx, p, instrumento_id)


@rutas.get("/plantilla")
def plantilla(proyecto_id: uuid.UUID, ctx: Lector, tipo: str = Query(default="TRD")):
    """Libro de partida, con columnas e instrucciones; los datos de ejemplo son ficticios."""
    obtener_proyecto(ctx, proyecto_id)
    if tipo not in servicios.TIPOS:
        raise DatosInvalidos("Tipo de instrumento desconocido")
    return Response(content=lector.plantilla(tipo), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="Plantilla_{tipo}.xlsx"'})


@rutas.get("", response_model=list[InstrumentoSalida])
def listar(proyecto_id: uuid.UUID, ctx: Lector):
    return [_salida(ctx, i) for i in servicios.listar(ctx, obtener_proyecto(ctx, proyecto_id))]


@rutas.post("", status_code=status.HTTP_201_CREATED, response_model=InstrumentoSalida)
def crear(proyecto_id: uuid.UUID, datos: InstrumentoNuevo, ctx: Gestor):
    p = obtener_proyecto(ctx, proyecto_id)
    return _salida(ctx, servicios.crear(ctx, p, datos.tipo, datos.nombre, datos.descripcion, datos.periodo_desde, datos.periodo_hasta))


@rutas.post("/{instrumento_id}/versiones", status_code=status.HTTP_201_CREATED, response_model=VersionSalida)
async def importar(proyecto_id: uuid.UUID, instrumento_id: uuid.UUID, ctx: Gestor, archivo: UploadFile = File(...), motivo: str = Form(..., min_length=5)):
    p, i = _contexto(ctx, proyecto_id, instrumento_id)
    return servicios.importar(ctx, p, i, await archivo.read(), archivo.filename or "instrumento.xlsx", motivo)


@rutas.get("/{instrumento_id}/versiones/{version_id}", response_model=DetalleVersion)
def ver_version(proyecto_id: uuid.UUID, instrumento_id: uuid.UUID, version_id: uuid.UUID, ctx: Lector):
    _, i = _contexto(ctx, proyecto_id, instrumento_id)
    servicios.versiones(ctx, i)
    v = servicios.obtener_version(ctx, i, version_id)
    a = ctx.db.get(ArchivoDigital, v.archivo_id)
    return DetalleVersion(**VersionSalida.model_validate(v).model_dump(), nombre_archivo=a.nombre_original, sha256=a.sha256,
                          elementos=[ElementoSalida.model_validate(e) for e in servicios.elementos(ctx, v)])


@rutas.get("/{instrumento_id}/versiones/{version_id}/archivo")
def archivo_fuente(proyecto_id: uuid.UUID, instrumento_id: uuid.UUID, version_id: uuid.UUID, ctx: Lector):
    _, i = _contexto(ctx, proyecto_id, instrumento_id)
    v = servicios.obtener_version(ctx, i, version_id)
    a = ctx.db.get(ArchivoDigital, v.archivo_id)
    return Response(content=almacen.leer(a.clave_almacen, ctx.tenant_id), media_type=a.mime,
                    headers={"Content-Disposition": f'attachment; filename="{a.nombre_original.replace(chr(34), "")}"', "X-Content-SHA256": a.sha256, "Cache-Control": "no-store"})


@rutas.post("/{instrumento_id}/versiones/{version_id}/aprobar", response_model=InstrumentoSalida)
def aprobar(proyecto_id: uuid.UUID, instrumento_id: uuid.UUID, version_id: uuid.UUID, datos: Aprobacion, ctx: Aprobador):
    p, i = _contexto(ctx, proyecto_id, instrumento_id)
    servicios.aprobar(ctx, p, i, servicios.obtener_version(ctx, i, version_id), datos.acto_administrativo, datos.fecha_acto, datos.convalidacion, datos.vigente_desde, datos.motivo)
    return _salida(ctx, i)


@rutas.post("/{instrumento_id}/versiones/{version_id}/descartar", response_model=InstrumentoSalida)
def descartar(proyecto_id: uuid.UUID, instrumento_id: uuid.UUID, version_id: uuid.UUID, datos: Motivo, ctx: Gestor):
    _, i = _contexto(ctx, proyecto_id, instrumento_id)
    servicios.descartar(ctx, i, servicios.obtener_version(ctx, i, version_id), datos.motivo)
    return _salida(ctx, i)


@rutas.get("/{instrumento_id}/comparar")
def comparar(proyecto_id: uuid.UUID, instrumento_id: uuid.UUID, desde: uuid.UUID, hasta: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    _, i = _contexto(ctx, proyecto_id, instrumento_id)
    return servicios.comparar(ctx, i, servicios.obtener_version(ctx, i, desde), servicios.obtener_version(ctx, i, hasta))


# ---------------------------------------------------------------- Clasificación de las unidades documentales

clasificacion_rutas = APIRouter(prefix="/proyectos/{proyecto_id}/clasificacion", tags=["M04 · Clasificación"])
LectorInventario = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Clasificador = Annotated[Contexto, Depends(requiere(Permiso.CLASIFICAR))]
SITUACIONES = ("pendiente", "propuesta", "confirmada", "version_anterior")


class Asignar(BaseModel):
    unidades: list[uuid.UUID] = Field(min_length=1, max_length=5000)
    elemento_id: uuid.UUID
    motivo: str = ""


class Decidir(BaseModel):
    clasificaciones: list[uuid.UUID] = Field(min_length=1, max_length=5000)
    motivo: str = ""


def _fila(f: dict[str, Any]) -> dict[str, Any]:
    u = f["unidad"]
    return {"unidad": {"id": u.id, "identificador": u.identificador, "numero_orden": u.numero_orden, "nombre": u.nombre, "codigo_serie": u.codigo_serie,
                       "fecha_inicial": u.fecha_inicial, "fecha_final": u.fecha_final, "caja": u.caja, "carpeta": u.carpeta, "folios": u.folios, "fase": u.fase},
            "clasificacion": f["clasificacion"], "situacion": f["situacion"], "alertas": f["alertas"]}


@clasificacion_rutas.get("/resumen")
def resumen(proyecto_id: uuid.UUID, ctx: LectorInventario) -> dict[str, Any]:
    p = obtener_proyecto(ctx, proyecto_id)
    filas = clasificacion.estado(ctx, p)
    cuenta = {s: sum(1 for f in filas if f["situacion"] == s) for s in SITUACIONES}
    fases = {k: sum(1 for f in filas if f["clasificacion"] and f["clasificacion"]["calendario"]["fase"] == k) for k in ("gestion", "central", "cumplida")}
    return {"unidades": len(filas), **cuenta, "con_alertas": sum(1 for f in filas if f["alertas"]), "fases": fases,
            "instrumentos": [{"instrumento": f"{vg.instrumento.tipo} · {vg.instrumento.nombre}", "version": vg.version.version, "acto": vg.version.acto_administrativo,
                              "periodo_desde": vg.instrumento.periodo_desde, "periodo_hasta": vg.instrumento.periodo_hasta} for vg in clasificacion.vigentes(ctx, p)]}


@clasificacion_rutas.get("")
def listar_unidades(proyecto_id: uuid.UUID, ctx: LectorInventario, situacion: str | None = None, alertas: bool = False, q: str | None = None,
                    desplazamiento: int = Query(default=0, ge=0), limite: int = Query(default=100, le=500)) -> dict[str, Any]:
    filas = clasificacion.estado(ctx, obtener_proyecto(ctx, proyecto_id))
    if situacion:
        filas = [f for f in filas if f["situacion"] == situacion]
    if alertas:
        filas = [f for f in filas if f["alertas"]]
    if q and (t := q.strip().lower()):
        filas = [f for f in filas if t in f"{f['unidad'].identificador} {f['unidad'].nombre} {f['unidad'].caja or ''} {f['unidad'].codigo_serie or ''}".lower()
                 or (f["clasificacion"] and t in f"{f['clasificacion']['codigo']} {f['clasificacion']['nombre']}".lower())]
    return {"total": len(filas), "filas": [_fila(f) for f in filas[desplazamiento:desplazamiento + limite]]}


@clasificacion_rutas.get("/opciones")
def opciones(proyecto_id: uuid.UUID, ctx: LectorInventario) -> list[dict[str, Any]]:
    """Series y subseries en las que se puede clasificar, de cada TRD o TVD vigente."""
    return clasificacion.opciones(ctx, obtener_proyecto(ctx, proyecto_id))


@clasificacion_rutas.post("/proponer")
def proponer(proyecto_id: uuid.UUID, ctx: Clasificador) -> dict[str, int]:
    """Clasifica lo pendiente: por el código del FUID (queda confirmada) o por el nombre del expediente (queda propuesta)."""
    return clasificacion.proponer(ctx, obtener_proyecto(ctx, proyecto_id))


@clasificacion_rutas.post("/asignar")
def asignar(proyecto_id: uuid.UUID, datos: Asignar, ctx: Clasificador) -> dict[str, int]:
    return {"clasificadas": clasificacion.asignar(ctx, obtener_proyecto(ctx, proyecto_id), datos.unidades, datos.elemento_id, datos.motivo)}


@clasificacion_rutas.post("/confirmar")
def confirmar(proyecto_id: uuid.UUID, datos: Decidir, ctx: Clasificador) -> dict[str, int]:
    return {"confirmadas": clasificacion.decidir(ctx, obtener_proyecto(ctx, proyecto_id), datos.clasificaciones, True, datos.motivo)}


@clasificacion_rutas.post("/rechazar")
def rechazar(proyecto_id: uuid.UUID, datos: Decidir, ctx: Clasificador) -> dict[str, int]:
    return {"rechazadas": clasificacion.decidir(ctx, obtener_proyecto(ctx, proyecto_id), datos.clasificaciones, False, datos.motivo)}


@clasificacion_rutas.post("/actualizar-version")
def actualizar_version(proyecto_id: uuid.UUID, datos: Motivo, ctx: Clasificador) -> dict[str, int]:
    """Pasa lo clasificado con versiones anteriores a la vigente, solo donde el mismo código sigue existiendo."""
    return clasificacion.actualizar_version(ctx, obtener_proyecto(ctx, proyecto_id), datos.motivo)
