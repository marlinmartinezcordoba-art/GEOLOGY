"""Hoja de control · API: bandeja del proyecto, elaboración sobre lo digitalizado, visor, verificación y expedición."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from arca.api.deps import Contexto, requiere
from arca.modelos import ArchivoDigital, RecursoDigital
from arca.modulos.hoja_control import servicios
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.modulos.m10_digitalizacion.paginas import imagen_pagina, paginas
from arca.nucleo import almacen
from arca.nucleo.errores import NoEncontrado
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/hojas-control", tags=["Hoja de control"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Elaborador = Annotated[Contexto, Depends(requiere(Permiso.HOJA_CONTROL))]
Verificador = Annotated[Contexto, Depends(requiere(Permiso.VERIFICAR_HOJA))]
Expedidor = Annotated[Contexto, Depends(requiere(Permiso.EXPEDIR))]


class Nueva(BaseModel):
    imagenes_por_folio: int = Field(default=1, description="1 = cada imagen es un folio; 2 = recto y verso")


class Cambios(BaseModel):
    fecha: str | None = None
    tipo_documental: str | None = None
    detalle: str | None = None
    no_radicado: str | None = None
    observaciones: str | None = None
    folio_desde: int | None = None
    folio_hasta: int | None = None
    metadatos: dict[str, str] | None = None


class PropuestaOcr(BaseModel):
    reemplazar: bool = Field(default=False, description="Reemplazar los trámites que ya se trabajaron")


class Division(BaseModel):
    pagina: int = Field(ge=2)


class Valor(BaseModel):
    valor: int


class Revision(BaseModel):
    conforme: bool
    observacion: str = ""


class Motivo(BaseModel):
    motivo: str = Field(min_length=5)


def _tramite(t) -> dict[str, Any]:
    return {"id": t.id, "orden": t.orden, "fecha": t.fecha, "fecha_texto": t.fecha_texto, "tipo_documental": t.tipo_documental, "detalle": t.detalle,
            "folio_desde": t.folio_desde, "folio_hasta": t.folio_hasta, "pagina_desde": t.pagina_desde, "pagina_hasta": t.pagina_hasta, "no_radicado": t.no_radicado,
            "observaciones": t.observaciones, "metadatos": t.metadatos or {}, "origen": t.origen or {}, "revision": t.revision, "observacion_revision": t.observacion_revision}


def _detalle(ctx, p, u) -> dict[str, Any]:
    h = servicios.hoja_de(ctx, u)
    clasif = servicios._clasificacion(ctx, u)
    return {
        "unidad": {"id": u.id, "identificador": u.identificador, "nombre": u.nombre, "caja": u.caja, "carpeta": u.carpeta, "folios": u.folios},
        "hoja": None if h is None else {"id": h.id, "estado": h.estado, "imagenes_por_folio": h.imagenes_por_folio, "origen": h.origen, "importacion": h.importacion or {},
                                        "novedad": h.novedad, "total_folios": h.total_folios, "creado_por": h.creado_por, "enviada_por": h.enviada_por,
                                        "enviada_en": h.enviada_en, "verificada_en": h.verificada_en, "verificada_por": h.verificada_por},
        "tramites": [_tramite(t) for t in servicios.tramites(ctx, h)] if h else [],
        "validacion": servicios.validar(ctx, h) if h else None,
        "metadatos": servicios.metadatos(ctx, p, h, u),
        "paginas": paginas(ctx, u),
        "tipos_documentales": servicios.tipos_sugeridos(clasif),
    }


def _u(ctx, proyecto_id, unidad_id):
    p = obtener_proyecto(ctx, proyecto_id)
    return p, servicios.unidad_de(ctx, p, unidad_id)


def _h(ctx, proyecto_id, unidad_id):
    p, u = _u(ctx, proyecto_id, unidad_id)
    h = servicios.hoja_de(ctx, u)
    if h is None:
        raise NoEncontrado("La unidad no tiene hoja de control")
    return p, u, h


@rutas.get("")
def bandeja(proyecto_id: uuid.UUID, ctx: Lector, estado: str | None = None, q: str | None = None, desplazamiento: int = Query(default=0, ge=0),
            limite: int = Query(default=100, le=500)) -> dict[str, Any]:
    total, filas, cuenta = servicios.bandeja(ctx, obtener_proyecto(ctx, proyecto_id), estado, q, desplazamiento, limite)
    return {"total": total, "filas": filas, "cuenta": cuenta}


@rutas.post("/importar")
async def importar(proyecto_id: uuid.UUID, ctx: Elaborador, archivo: UploadFile = File(...), imagenes_por_folio: int = Form(default=1)) -> list[dict[str, Any]]:
    """Hojas de control diligenciadas en Excel: una por pestaña, asociada a la unidad por el código de carpeta."""
    return servicios.importar(ctx, obtener_proyecto(ctx, proyecto_id), await archivo.read(), archivo.filename or "hojas.xlsx", imagenes_por_folio)


@rutas.get("/unidades/{unidad_id}")
def ver(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    p, u = _u(ctx, proyecto_id, unidad_id)
    return _detalle(ctx, p, u)


@rutas.post("/unidades/{unidad_id}", status_code=status.HTTP_201_CREATED)
def crear(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, datos: Nueva, ctx: Elaborador) -> dict[str, Any]:
    p, u = _u(ctx, proyecto_id, unidad_id)
    servicios.crear(ctx, p, u, datos.imagenes_por_folio)
    return _detalle(ctx, p, u)


@rutas.get("/unidades/{unidad_id}/paginas/{n}/imagen")
def imagen(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, n: int, ctx: Lector, ancho: int = Query(default=1400, ge=200, le=2400)):
    """La página n del expediente digitalizado, como imagen para el visor."""
    _, u = _u(ctx, proyecto_id, unidad_id)
    return Response(content=imagen_pagina(ctx, u, n, ancho), media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@rutas.get("/unidades/{unidad_id}/paginas/{n}/original")
def original(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, n: int, ctx: Lector):
    """El archivo original que contiene la página n, verificado contra su huella."""
    _, u = _u(ctx, proyecto_id, unidad_id)
    lista = paginas(ctx, u)
    if not 1 <= n <= len(lista):
        raise NoEncontrado("La página no existe en el expediente")
    r = ctx.db.get(RecursoDigital, lista[n - 1]["recurso_id"])
    a = ctx.db.get(ArchivoDigital, r.archivo_id)
    datos = almacen.leer(a.clave_almacen, ctx.tenant_id)
    ctx.auditar(accion="VER_ORIGINAL", objeto="RecursoDigital", objeto_id=r.id, detalle=f"{u.identificador} · página {n} · desde la hoja de control")
    ctx.db.commit()
    return Response(content=datos, media_type=a.mime, headers={"Content-Disposition": f'inline; filename="{a.nombre_original.replace(chr(34), "")}"', "X-Content-SHA256": a.sha256})


@rutas.put("/unidades/{unidad_id}/imagenes-por-folio")
def imagenes_por_folio(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, datos: Valor, ctx: Elaborador) -> dict[str, Any]:
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.cambiar_imagenes_por_folio(ctx, p, h, datos.valor)
    return _detalle(ctx, p, u)


@rutas.post("/unidades/{unidad_id}/tramites")
def agregar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Elaborador) -> dict[str, Any]:
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.agregar(ctx, p, h)
    return _detalle(ctx, p, u)


@rutas.patch("/unidades/{unidad_id}/tramites/{tramite_id}")
def editar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, tramite_id: uuid.UUID, datos: Cambios, ctx: Elaborador) -> dict[str, Any]:
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.editar(ctx, p, h, tramite_id, datos.model_dump(exclude_unset=True))
    return _detalle(ctx, p, u)


@rutas.delete("/unidades/{unidad_id}/tramites/{tramite_id}")
def quitar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, tramite_id: uuid.UUID, ctx: Elaborador) -> dict[str, Any]:
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.quitar(ctx, p, h, tramite_id)
    return _detalle(ctx, p, u)


@rutas.post("/unidades/{unidad_id}/tramites/{tramite_id}/dividir")
def dividir(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, tramite_id: uuid.UUID, datos: Division, ctx: Elaborador) -> dict[str, Any]:
    """«Aquí empieza otro documento»: parte el trámite en esa página del expediente."""
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.dividir(ctx, p, h, tramite_id, datos.pagina)
    return _detalle(ctx, p, u)


@rutas.post("/unidades/{unidad_id}/tramites/{tramite_id}/unir")
def unir(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, tramite_id: uuid.UUID, ctx: Elaborador) -> dict[str, Any]:
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.unir(ctx, p, h, tramite_id)
    return _detalle(ctx, p, u)


@rutas.post("/unidades/{unidad_id}/proponer-ocr")
def proponer_ocr(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, datos: PropuestaOcr, ctx: Elaborador) -> dict[str, Any]:
    """Arma los trámites con lo leído por OCR: dónde empieza cada documento, tipo, fecha, detalle y radicado, como propuesta."""
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.proponer_desde_ocr(ctx, p, h, datos.reemplazar)
    return _detalle(ctx, p, u)


@rutas.post("/unidades/{unidad_id}/tramites/{tramite_id}/confirmar")
def confirmar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, tramite_id: uuid.UUID, ctx: Elaborador) -> dict[str, Any]:
    """Acepta tal cual lo que el OCR propuso para el trámite."""
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.confirmar(ctx, p, h, tramite_id)
    return _detalle(ctx, p, u)


@rutas.post("/unidades/{unidad_id}/enviar")
def enviar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Elaborador) -> dict[str, Any]:
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.enviar(ctx, p, h)
    return _detalle(ctx, p, u)


@rutas.post("/unidades/{unidad_id}/tramites/{tramite_id}/revisar")
def revisar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, tramite_id: uuid.UUID, datos: Revision, ctx: Verificador) -> dict[str, Any]:
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.revisar(ctx, p, h, tramite_id, datos.conforme, datos.observacion)
    return _detalle(ctx, p, u)


@rutas.post("/unidades/{unidad_id}/verificar")
def verificar(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Verificador) -> dict[str, Any]:
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.verificar(ctx, p, h)
    return _detalle(ctx, p, u)


@rutas.post("/unidades/{unidad_id}/devolver")
def devolver(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, datos: Motivo, ctx: Verificador) -> dict[str, Any]:
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.devolver(ctx, p, h, datos.motivo)
    return _detalle(ctx, p, u)


@rutas.post("/unidades/{unidad_id}/reabrir")
def reabrir(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, datos: Motivo, ctx: Verificador) -> dict[str, Any]:
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    servicios.reabrir(ctx, p, h, datos.motivo)
    return _detalle(ctx, p, u)


@rutas.post("/unidades/{unidad_id}/expedir", status_code=status.HTTP_201_CREATED)
def expedir(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Expedidor) -> dict[str, Any]:
    """La hoja verificada en el formato de la entidad; se descarga por Entregables."""
    p, u, h = _h(ctx, proyecto_id, unidad_id)
    e = servicios.expedir(ctx, p, h)
    a = ctx.db.get(ArchivoDigital, e.archivo_id)
    return {"expedicion_id": e.id, "elementos": e.elementos, "nombre_archivo": a.nombre_original, "sha256": a.sha256}
