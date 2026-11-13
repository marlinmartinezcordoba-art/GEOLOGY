"""Errores de dominio y su traducción a respuestas HTTP (reciclado de Kustos, simplificado).

Los servicios lanzan estas excepciones sin conocer FastAPI. Toda respuesta de error lleva el
identificador de correlación de la petición, para rastrearla en la auditoría y en los registros.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorDominio(Exception):
    codigo_http = 400

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class NoEncontrado(ErrorDominio):
    codigo_http = 404


class Conflicto(ErrorDominio):
    codigo_http = 409


class AccesoDenegado(ErrorDominio):
    codigo_http = 403


class DatosInvalidos(ErrorDominio):
    codigo_http = 422


class TransicionInvalida(ErrorDominio):
    codigo_http = 422


def _correlacion(request: Request) -> str | None:
    return getattr(request.state, "correlacion_id", None)


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ErrorDominio)
    async def _dominio(request: Request, exc: ErrorDominio) -> JSONResponse:
        return JSONResponse(status_code=exc.codigo_http, content={"detail": exc.mensaje, "correlacion_id": _correlacion(request)})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "correlacion_id": _correlacion(request)},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validacion(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors()), "correlacion_id": _correlacion(request)})

    @app.exception_handler(Exception)
    async def _interno(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("arca.errores").exception("falla no controlada [%s]: %s", _correlacion(request), exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Ocurrió una falla interna. Comunique el identificador de correlación al soporte.", "correlacion_id": _correlacion(request)},
        )
