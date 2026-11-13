"""M24 · API de productividad del proyecto (con sesión) y fuente de datos de Power BI (con llave de lectura)."""

import csv
import io
import uuid
from datetime import date, datetime
from types import SimpleNamespace
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from arca.api.deps import Contexto, Sesion, requiere
from arca.modelos import ClaveReporte, Organizacion, Proyecto
from arca.modulos.m06_proyectos.servicios import obtener as obtener_proyecto
from arca.modulos.m24_productividad import diseno, servicios
from arca.nucleo.errores import NoEncontrado
from arca.nucleo.permisos import Permiso

rutas = APIRouter(prefix="/proyectos/{proyecto_id}/productividad", tags=["M24 · Productividad"])
powerbi = APIRouter(prefix="/powerbi", tags=["M24 · Power BI"])
Lector = Annotated[Contexto, Depends(requiere(Permiso.PRODUCTIVIDAD_LEER))]
Registrador = Annotated[Contexto, Depends(requiere(Permiso.PRODUCTIVIDAD_REGISTRAR))]
Configurador = Annotated[Contexto, Depends(requiere(Permiso.PRODUCTIVIDAD_CONFIGURAR))]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Motivo(BaseModel):
    motivo: str = Field(min_length=5)


class ClaveNueva(BaseModel):
    nombre: str = Field(min_length=3, max_length=120, description="Para qué es: «Power BI de la PMO», «Tablero del cliente»…")


class ClaveSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    prefijo: str
    activa: bool
    creado_en: datetime
    ultimo_uso: datetime | None


class ClaveCreada(BaseModel):
    clave: ClaveSalida
    token: str = Field(description="Se muestra una única vez. Guárdelo en la configuración del origen de datos de Power BI.")


def _csv(filas: list[dict[str, Any]], columnas: list[str]) -> str:
    salida = io.StringIO()
    escritor = csv.DictWriter(salida, fieldnames=columnas, extrasaction="ignore")
    escritor.writeheader()
    for f in filas:
        escritor.writerow({k: (", ".join(v) if isinstance(v, list) else v) for k, v in f.items()})
    return salida.getvalue()


def _columnas(nombre: str, filas: list[dict[str, Any]]) -> list[str]:
    tabla = diseno.POR_NOMBRE.get(nombre)
    return [c.nombre for c in tabla.columnas] if tabla else (list(filas[0]) if filas else [])


def _entregar(nombre: str, filas: list[dict[str, Any]], formato: str):
    if formato == "csv":
        return Response(content=_csv(filas, _columnas(nombre, filas)), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'inline; filename="{nombre}.csv"'})
    return filas


# --- Con sesión ---------------------------------------------------------------------------------


@rutas.get("/diseno")
def diseno_del_reporte(_: Lector) -> dict[str, Any]:
    """Tablas y columnas del diseño (para la pantalla y para documentar el modelo de Power BI)."""
    return {
        "tablas": [{"nombre": t.nombre, "hoja": t.hoja, "registro": t.es_registro, "columnas": [{"nombre": c.nombre, "tipo": c.tipo, "obligatoria": c.obligatoria} for c in t.columnas]} for t in diseno.TABLAS],
        "listas": {"resultados_calidad": diseno.RESULTADOS_CALIDAD, "tipos_novedad": diseno.TIPOS_NOVEDAD, "estados_novedad": diseno.ESTADOS_NOVEDAD,
                   "estados_entrega": diseno.ESTADOS_ENTREGA, "unidades": diseno.UNIDADES, "fuentes_automaticas": diseno.FUENTES_AUTOMATICAS},
        "tablas_disponibles": servicios.NOMBRES_TABLAS,
    }


@rutas.get("/tablero")
def tablero(proyecto_id: uuid.UUID, ctx: Lector, fecha_corte: date | None = None) -> dict[str, Any]:
    return servicios.tablero(ctx, obtener_proyecto(ctx, proyecto_id), fecha_corte)


@rutas.get("/tablas/{nombre}")
def tabla(proyecto_id: uuid.UUID, nombre: str, ctx: Lector, formato: str = Query(default="json", pattern="^(json|csv)$")):
    return _entregar(nombre, servicios.filas_tabla(ctx, obtener_proyecto(ctx, proyecto_id), nombre), formato)


@rutas.post("/registros/{nombre}", status_code=status.HTTP_201_CREATED)
def registrar(proyecto_id: uuid.UUID, nombre: str, valores: dict[str, Any], ctx: Registrador) -> dict[str, Any]:
    """Un registro con las columnas del diseño: fProduccion, fCalidad, fNovedades o fEntregas."""
    proyecto = obtener_proyecto(ctx, proyecto_id)
    registro = servicios.registrar(ctx, proyecto, nombre, valores)
    return diseno.fila_a_dict(diseno.POR_NOMBRE[nombre], registro)


@rutas.post("/libro")
async def importar_libro(proyecto_id: uuid.UUID, ctx: Configurador, archivo: UploadFile = File(...)) -> list[dict[str, Any]]:
    """Importa un libro con el diseño: las hojas d* reemplazan la configuración, las Registro_* se agregan."""
    return servicios.importar_libro(ctx, obtener_proyecto(ctx, proyecto_id), await archivo.read())


@rutas.get("/libro")
def descargar_libro(proyecto_id: uuid.UUID, ctx: Lector):
    proyecto = obtener_proyecto(ctx, proyecto_id)
    contenido = servicios.libro_lleno(ctx, proyecto)
    return Response(content=contenido, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="Productividad_{proyecto.codigo}.xlsx"'})


@rutas.get("/plantilla")
def plantilla(_: Lector):
    """El libro con el diseño y sin ningún dato, para diligenciar la configuración y los registros."""
    return Response(content=servicios.libro_vacio(), media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="ARCA_Productividad_plantilla.xlsx"'})


@rutas.get("/cajas")
def cajas(proyecto_id: uuid.UUID, ctx: Lector, frente: str | None = None, estado: str | None = Query(default=None, pattern="^(pendiente|en_proceso|procesada)$"), q: str | None = None) -> dict[str, Any]:
    return servicios.avance_cajas(ctx, obtener_proyecto(ctx, proyecto_id), frente, estado, q)


@rutas.post("/cajas/listado")
async def importar_cajas(proyecto_id: uuid.UUID, ctx: Configurador, archivo: UploadFile = File(...)) -> dict[str, Any]:
    return servicios.importar_cajas(ctx, obtener_proyecto(ctx, proyecto_id), await archivo.read(), archivo.filename or "cajas.xlsx")


@rutas.post("/cajas/desde-fuid")
def cajas_desde_fuid(proyecto_id: uuid.UUID, ctx: Configurador, frente: str | None = None) -> dict[str, Any]:
    return servicios.cajas_desde_fuid(ctx, obtener_proyecto(ctx, proyecto_id), frente)


@rutas.get("/claves", response_model=list[ClaveSalida])
def listar_claves(proyecto_id: uuid.UUID, ctx: Configurador):
    proyecto = obtener_proyecto(ctx, proyecto_id)
    return list(ctx.db.scalars(select(ClaveReporte).where(ClaveReporte.proyecto_id == proyecto.id).order_by(ClaveReporte.creado_en.desc())))


@rutas.post("/claves", status_code=status.HTTP_201_CREATED, response_model=ClaveCreada)
def crear_clave(proyecto_id: uuid.UUID, datos: ClaveNueva, ctx: Configurador):
    clave, token = servicios.crear_clave(ctx, obtener_proyecto(ctx, proyecto_id), datos.nombre)
    return ClaveCreada(clave=ClaveSalida.model_validate(clave), token=token)


@rutas.post("/claves/{clave_id}/revocar", response_model=ClaveSalida)
def revocar_clave(proyecto_id: uuid.UUID, clave_id: uuid.UUID, datos: Motivo, ctx: Configurador):
    return servicios.revocar_clave(ctx, obtener_proyecto(ctx, proyecto_id), clave_id, datos.motivo)


# --- Power BI: solo lectura, con llave del proyecto ------------------------------------------------


def contexto_powerbi(db: Sesion, authorization: Annotated[str | None, Header()] = None) -> SimpleNamespace:
    token = (authorization or "").removeprefix("Bearer ").strip()
    clave = servicios.autenticar_clave(db, token) if token else None
    if clave is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Llave de reporte inválida o revocada", headers={"WWW-Authenticate": "Bearer"})
    organizacion = db.get(Organizacion, clave.tenant_id)
    proyecto = db.get(Proyecto, clave.proyecto_id)
    if organizacion is None or not organizacion.activa or proyecto is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La organización de esta llave no está activa")
    return SimpleNamespace(db=db, organizacion=organizacion, tenant_id=organizacion.id, proyecto=proyecto)


PowerBI = Annotated[SimpleNamespace, Depends(contexto_powerbi)]


@powerbi.get("/tablas")
def tablas_powerbi(ctx: PowerBI) -> dict[str, Any]:
    return {"proyecto": ctx.proyecto.codigo, "tablas": servicios.NOMBRES_TABLAS}


@powerbi.get("/{nombre}")
def tabla_powerbi(nombre: str, ctx: PowerBI, formato: str = Query(default="json", pattern="^(json|csv)$"), fecha_corte: date | None = None):
    if nombre not in servicios.NOMBRES_TABLAS:
        raise NoEncontrado(f"Tabla «{nombre}» desconocida")
    if nombre == "Tablero" and fecha_corte:
        filas = servicios.tablero(ctx, ctx.proyecto, fecha_corte)["frentes"]
    else:
        filas = servicios.filas_tabla(ctx, ctx.proyecto, nombre)
    return _entregar(nombre, filas, formato)
