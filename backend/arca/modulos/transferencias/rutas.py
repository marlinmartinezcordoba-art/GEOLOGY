"""Transferencias documentales · API (primaria y secundaria), plan por fecha de corte y fase de partida."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from arca.api.deps import Contexto, requiere
from arca.modelos import ArchivoDigital
from arca.modelos.transferencias import FASES
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.modulos.transferencias import servicios
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/transferencias", tags=["Transferencias documentales"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.INVENTARIO_LEER))]
Gestor = Annotated[Contexto, Depends(requiere(Permiso.TRANSFERIR))]
Receptor = Annotated[Contexto, Depends(requiere(Permiso.RECIBIR_TRANSFERENCIA))]


class Nueva(BaseModel):
    tipo: str = Field(description="primaria | secundaria")
    fecha_corte: date | None = Field(default=None, description="Vacío = hoy")
    codigo_dependencia: str = Field(default="", description="Vacío = todas las dependencias")
    observaciones: str = ""


class Unidades(BaseModel):
    unidades: list[uuid.UUID] = Field(min_length=1, max_length=10000)


class Devuelta(BaseModel):
    unidad_id: uuid.UUID
    observacion: str = Field(min_length=5)


class Recepcion(BaseModel):
    devueltas: list[Devuelta] = []
    motivo: str = ""


class Motivo(BaseModel):
    motivo: str = Field(min_length=5)


class FaseDePartida(BaseModel):
    unidades: list[uuid.UUID] = Field(default=[], max_length=10000)
    cajas: list[str] = Field(default=[], max_length=5000, description="En lugar de unidades: todas las unidades de estas cajas")
    fase: str
    motivo: str = Field(min_length=5)


class TransferenciaSalida(BaseModel):
    id: uuid.UUID
    numero: int
    tipo: str
    estado: str
    codigo_dependencia: str
    dependencia: str
    fecha_corte: date
    observaciones: str
    novedad: str
    creado_en: datetime
    creado_por: uuid.UUID | None
    enviada_en: datetime | None
    enviada_por: uuid.UUID | None
    recibida_en: datetime | None
    recibida_por: uuid.UUID | None
    resumen: dict[str, int]


def _salida(ctx, t) -> TransferenciaSalida:
    return TransferenciaSalida(**{k: getattr(t, k) for k in TransferenciaSalida.model_fields if k != "resumen"}, resumen=servicios.resumen(ctx, t))


def _t(ctx, proyecto_id, transferencia_id):
    p = obtener_proyecto(ctx, proyecto_id)
    return p, servicios.obtener(ctx, p, transferencia_id)


@rutas.get("/plan")
def plan(proyecto_id: uuid.UUID, ctx: Lector, fecha_corte: date | None = None) -> dict[str, Any]:
    """Unidades por fase y cuántas se pueden transferir a la fecha de corte, por dependencia."""
    return servicios.plan(ctx, obtener_proyecto(ctx, proyecto_id), fecha_corte or date.today())


@rutas.get("", response_model=list[TransferenciaSalida])
def listar(proyecto_id: uuid.UUID, ctx: Lector):
    return [_salida(ctx, t) for t in servicios.listar(ctx, obtener_proyecto(ctx, proyecto_id))]


@rutas.post("", status_code=status.HTTP_201_CREATED, response_model=TransferenciaSalida)
def crear(proyecto_id: uuid.UUID, datos: Nueva, ctx: Gestor):
    p = obtener_proyecto(ctx, proyecto_id)
    return _salida(ctx, servicios.crear(ctx, p, datos.tipo, datos.fecha_corte or date.today(), datos.codigo_dependencia, datos.observaciones))


@rutas.get("/{transferencia_id}")
def ver(proyecto_id: uuid.UUID, transferencia_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    _, t = _t(ctx, proyecto_id, transferencia_id)
    return {"transferencia": _salida(ctx, t), "unidades": [
        {"unidad_id": u.id, "identificador": u.identificador, "nombre": u.nombre, "caja": u.caja, "carpeta": u.carpeta, "folios": u.folios,
         "fecha_inicial": u.fecha_inicial, "fecha_final": u.fecha_final, "fase": u.fase, "elegible": e.elegible, "aviso": e.aviso, "estado": e.estado, "observacion": e.observacion}
        for e, u in servicios.elementos(ctx, t)]}


@rutas.get("/{transferencia_id}/candidatas")
def candidatas(proyecto_id: uuid.UUID, transferencia_id: uuid.UUID, ctx: Lector, q: str | None = None, limite: int = Query(default=200, le=1000)) -> list[dict[str, Any]]:
    """Unidades que se pueden agregar: en la fase de origen, clasificadas y libres. Las anticipadas vienen con su aviso."""
    p, t = _t(ctx, proyecto_id, transferencia_id)
    datos = servicios._contexto(ctx, p)
    salida = []
    for u in sorted(datos["unidades"].values(), key=lambda x: (x.caja or "", x.identificador)):
        if q and q.strip().lower() not in f"{u.identificador} {u.nombre} {u.caja or ''}".lower():
            continue
        ev = servicios._evaluar(datos, u, t.tipo, t.fecha_corte)
        if ev["puede"] and (not t.codigo_dependencia or ev["codigo_dependencia"] == t.codigo_dependencia):
            salida.append({"unidad_id": u.id, "identificador": u.identificador, "nombre": u.nombre, "caja": u.caja, "folios": u.folios, "elegible": ev["elegible"], "aviso": ev["aviso"]})
    return salida[:limite]


@rutas.post("/{transferencia_id}/agregar")
def agregar(proyecto_id: uuid.UUID, transferencia_id: uuid.UUID, datos: Unidades, ctx: Gestor) -> dict[str, Any]:
    p, t = _t(ctx, proyecto_id, transferencia_id)
    return servicios.agregar(ctx, p, t, datos.unidades)


@rutas.post("/{transferencia_id}/quitar")
def quitar(proyecto_id: uuid.UUID, transferencia_id: uuid.UUID, datos: Unidades, ctx: Gestor) -> dict[str, int]:
    p, t = _t(ctx, proyecto_id, transferencia_id)
    return {"quitadas": servicios.quitar(ctx, p, t, datos.unidades)}


@rutas.post("/{transferencia_id}/enviar", response_model=TransferenciaSalida)
def enviar(proyecto_id: uuid.UUID, transferencia_id: uuid.UUID, ctx: Gestor):
    p, t = _t(ctx, proyecto_id, transferencia_id)
    return _salida(ctx, servicios.enviar(ctx, p, t))


@rutas.post("/{transferencia_id}/recibir")
def recibir(proyecto_id: uuid.UUID, transferencia_id: uuid.UUID, datos: Recepcion, ctx: Receptor) -> dict[str, int]:
    p, t = _t(ctx, proyecto_id, transferencia_id)
    return servicios.recibir(ctx, p, t, {d.unidad_id: d.observacion for d in datos.devueltas}, datos.motivo)


@rutas.post("/{transferencia_id}/devolver", response_model=TransferenciaSalida)
def devolver(proyecto_id: uuid.UUID, transferencia_id: uuid.UUID, datos: Motivo, ctx: Receptor):
    p, t = _t(ctx, proyecto_id, transferencia_id)
    return _salida(ctx, servicios.devolver(ctx, p, t, datos.motivo))


@rutas.post("/{transferencia_id}/anular", response_model=TransferenciaSalida)
def anular(proyecto_id: uuid.UUID, transferencia_id: uuid.UUID, datos: Motivo, ctx: Gestor):
    p, t = _t(ctx, proyecto_id, transferencia_id)
    return _salida(ctx, servicios.anular(ctx, p, t, datos.motivo))


@rutas.post("/{transferencia_id}/inventario", status_code=status.HTTP_201_CREATED)
def inventario(proyecto_id: uuid.UUID, transferencia_id: uuid.UUID, ctx: Lector) -> dict[str, Any]:
    """Expide el FUID de la transferencia con la plantilla vigente; se descarga por Entregables."""
    p, t = _t(ctx, proyecto_id, transferencia_id)
    e = servicios.inventario(ctx, p, t)
    a = ctx.db.get(ArchivoDigital, e.archivo_id)
    return {"expedicion_id": e.id, "elementos": e.elementos, "nombre_archivo": a.nombre_original, "sha256": a.sha256}


@rutas.post("/fase-de-partida")
def fase_de_partida(proyecto_id: uuid.UUID, datos: FaseDePartida, ctx: Gestor) -> dict[str, int]:
    """Registra dónde está hoy un fondo que no llega por transferencia (por ejemplo, ya está en el archivo central)."""
    return {"registradas": servicios.fase_de_partida(ctx, obtener_proyecto(ctx, proyecto_id), datos.unidades, datos.fase, datos.motivo, datos.cajas)}


@rutas.get("/unidades/{unidad_id}/historial")
def historial(proyecto_id: uuid.UUID, unidad_id: uuid.UUID, ctx: Lector) -> list[dict[str, Any]]:
    return [{"desde": FASES.get(m.desde or "", None), "hasta": FASES[m.hasta], "motivo": m.motivo, "transferencia_id": m.transferencia_id, "creado_en": m.creado_en}
            for m in servicios.historial(ctx, obtener_proyecto(ctx, proyecto_id), unidad_id)]
