"""Dependencias compartidas: sesión de BD, usuario autenticado, organización activa y permisos.

Reciclado de Kustos (api/deps.py) con dos cambios para ARCA:
- La organización activa llega en la cabecera `X-Organizacion`. Si el usuario pertenece a varias, la
  cabecera es obligatoria: ARCA nunca escoge por él una organización.
- El operador de la plataforma no tiene membresías y por eso no entra a datos de ninguna organización.
Todo registro de otra organización responde 404, para no revelar siquiera que existe.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from arca.modelos import Membresia, Organizacion, Usuario
from arca.nucleo.bd import obtener_sesion
from arca.nucleo.permisos import Permiso
from arca.nucleo.seguridad import TIPO_ACCESO, leer_token

Sesion = Annotated[Session, Depends(obtener_sesion)]
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


@dataclass
class Peticion:
    ip: str | None
    agente: str | None
    correlacion_id: str | None


def datos_peticion(request: Request) -> Peticion:
    return Peticion(
        ip=request.client.host if request.client else None,
        agente=request.headers.get("user-agent"),
        correlacion_id=getattr(request.state, "correlacion_id", None),
    )


Origen = Annotated[Peticion, Depends(datos_peticion)]


def _usuario_desde_token(db: Session, token: str) -> Usuario:
    invalida = HTTPException(status.HTTP_401_UNAUTHORIZED, "La sesión expiró o no es válida. Ingrese de nuevo.", headers={"WWW-Authenticate": "Bearer"})
    datos = leer_token(token)
    if datos is None or datos.tipo != TIPO_ACCESO:
        raise invalida
    usuario = db.scalar(
        select(Usuario)
        .where(Usuario.id == datos.usuario_id)
        .options(selectinload(Usuario.membresias).selectinload(Membresia.rol), selectinload(Usuario.membresias).selectinload(Membresia.organizacion))
    )
    if usuario is None or not usuario.activo or usuario.bloqueado or datos.version_sesion != usuario.version_sesion:
        raise invalida
    return usuario


def usuario_autenticado(db: Sesion, token: Annotated[str, Depends(_oauth2)]) -> Usuario:
    """Usuario con sesión válida, aunque todavía tenga que cambiar su contraseña temporal."""
    return _usuario_desde_token(db, token)


UsuarioSesion = Annotated[Usuario, Depends(usuario_autenticado)]


def usuario_habilitado(usuario: UsuarioSesion) -> Usuario:
    if usuario.debe_cambiar_clave:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Debe cambiar su contraseña temporal antes de continuar")
    return usuario


UsuarioActual = Annotated[Usuario, Depends(usuario_habilitado)]


def solo_operador(usuario: UsuarioActual) -> Usuario:
    if not usuario.es_operador:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operación reservada al operador de la plataforma")
    return usuario


Operador = Annotated[Usuario, Depends(solo_operador)]


@dataclass
class Contexto:
    """Usuario autenticado trabajando sobre su organización activa."""

    db: Session
    usuario: Usuario
    organizacion: Organizacion
    membresia: Membresia
    origen: Peticion

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.organizacion.id

    @property
    def permisos(self) -> set[str]:
        return set(self.membresia.rol.permisos)

    @property
    def alcance_proyectos(self) -> set[uuid.UUID] | None:
        """None = todos los proyectos de la organización."""
        if self.membresia.proyectos is None:
            return None
        return {uuid.UUID(p) for p in self.membresia.proyectos}

    def puede(self, permiso: Permiso) -> bool:
        return permiso.value in self.permisos

    def exigir(self, permiso: Permiso) -> None:
        if not self.puede(permiso):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Su rol no tiene permiso para esta acción")

    def auditar(self, **datos) -> None:
        from arca.modulos.m25_auditoria.servicios import registrar  # noqa: PLC0415

        registrar(
            self.db,
            tenant_id=self.tenant_id,
            usuario=self.usuario,
            ip=self.origen.ip,
            agente=self.origen.agente,
            correlacion_id=self.origen.correlacion_id,
            **datos,
        )


def membresias_vigentes(usuario: Usuario) -> list[Membresia]:
    return [m for m in usuario.membresias if m.activa and m.organizacion.activa]


def obtener_contexto(db: Sesion, usuario: UsuarioActual, origen: Origen, x_organizacion: Annotated[str | None, Header()] = None) -> Contexto:
    vigentes = membresias_vigentes(usuario)
    if not vigentes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tiene acceso a ninguna organización activa")
    if x_organizacion:
        try:
            oid = uuid.UUID(x_organizacion)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Organización inválida") from e
        membresia = next((m for m in vigentes if m.tenant_id == oid), None)
        if membresia is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tiene acceso a esa organización")
    elif len(vigentes) == 1:
        membresia = vigentes[0]
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pertenece a varias organizaciones: indique cuál en la cabecera X-Organizacion")
    if not usuario.mfa_activo:
        from arca.modulos.m03_configuracion.servicios import mfa_exigido  # noqa: PLC0415

        if mfa_exigido(db, membresia):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Su organización exige verificación en dos pasos para su rol: actívela en «Mi cuenta» para continuar.")
    return Contexto(db=db, usuario=usuario, organizacion=membresia.organizacion, membresia=membresia, origen=origen)


Ctx = Annotated[Contexto, Depends(obtener_contexto)]


def requiere(permiso: Permiso) -> Callable[..., Contexto]:
    def dependencia(ctx: Ctx) -> Contexto:
        ctx.exigir(permiso)
        return ctx

    return dependencia
