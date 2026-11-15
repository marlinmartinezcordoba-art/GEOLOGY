"""M02 · API de ingreso (/auth), usuarios de la organización (/usuarios) y roles (/roles)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from arca.api.deps import Contexto, Ctx, Origen, Sesion, UsuarioSesion, membresias_vigentes, requiere
from arca.modelos import Usuario
from arca.modulos.m02_usuarios import servicios
from arca.nucleo.permisos import TODOS, Permiso

auth = APIRouter(prefix="/auth", tags=["M02 · Ingreso"])
usuarios = APIRouter(prefix="/usuarios", tags=["M02 · Usuarios"])
roles = APIRouter(prefix="/roles", tags=["M02 · Roles"])

Administrador = Annotated[Contexto, Depends(requiere(Permiso.USUARIOS))]
GestorRoles = Annotated[Contexto, Depends(requiere(Permiso.ROLES))]


# --- Esquemas ---------------------------------------------------------------------------------


class Ingreso(BaseModel):
    correo: EmailStr
    clave: str = Field(min_length=1)
    codigo_mfa: str | None = Field(default=None, description="Código de 6 dígitos si tiene activa la verificación en dos pasos")


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    debe_cambiar_clave: bool


class CambioClave(BaseModel):
    clave_actual: str
    clave_nueva: str


class CodigoMfa(BaseModel):
    codigo: str = Field(min_length=6, max_length=6)


class Motivo(BaseModel):
    motivo: str = Field(min_length=5)


class MembresiaResumen(BaseModel):
    organizacion_id: uuid.UUID
    organizacion: str
    rol: str
    permisos: list[str]
    mfa_exigido: bool = False


class Yo(BaseModel):
    id: uuid.UUID
    correo: str
    nombre_completo: str
    es_operador: bool
    debe_cambiar_clave: bool
    mfa_activo: bool
    organizaciones: list[MembresiaResumen]


class UsuarioNuevo(BaseModel):
    correo: EmailStr
    nombre_completo: str = Field(min_length=3, max_length=200)
    rol_id: uuid.UUID
    proyectos: list[uuid.UUID] | None = Field(default=None, description="Limitar a estos proyectos. Vacío = todos.")


class CambioAcceso(BaseModel):
    rol_id: uuid.UUID | None = None
    proyectos: list[uuid.UUID] | None = None
    motivo: str = Field(min_length=5)


class MiembroSalida(BaseModel):
    usuario_id: uuid.UUID
    correo: str
    nombre_completo: str
    rol_id: uuid.UUID
    rol: str
    activa: bool
    proyectos: list[uuid.UUID] | None
    mfa_activo: bool
    bloqueado: bool


class PersonaDirectorio(BaseModel):
    usuario_id: uuid.UUID
    nombre_completo: str
    correo: str
    rol: str


class UsuarioAgregado(BaseModel):
    miembro: MiembroSalida
    clave_temporal: str | None = Field(description="Solo si la cuenta es nueva y no se pudo enviar por correo. Se muestra una única vez.")
    enviada_por_correo: bool = False


class RolNuevo(BaseModel):
    nombre: str = Field(min_length=3, max_length=120)
    descripcion: str = ""
    permisos: list[str]


class RolCambios(BaseModel):
    descripcion: str | None = None
    permisos: list[str] | None = None
    motivo: str = Field(min_length=5)


class RolSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    descripcion: str
    permisos: list[str]
    es_base: bool
    creado_en: datetime


def _miembro(m) -> MiembroSalida:
    return MiembroSalida(
        usuario_id=m.usuario_id,
        correo=m.usuario.correo,
        nombre_completo=m.usuario.nombre_completo,
        rol_id=m.rol_id,
        rol=m.rol.nombre,
        activa=m.activa,
        proyectos=m.proyectos,
        mfa_activo=m.usuario.mfa_activo,
        bloqueado=m.usuario.bloqueado,
    )


def _no_autenticado(e: servicios.NoAutenticado) -> HTTPException:
    cabeceras = {"WWW-Authenticate": "Bearer"}
    if isinstance(e, servicios.MfaRequerido):
        cabeceras["X-ARCA-MFA"] = "requerido"
    return HTTPException(status.HTTP_401_UNAUTHORIZED, e.mensaje, headers=cabeceras)


# --- Ingreso ----------------------------------------------------------------------------------


@auth.post("/ingresar", response_model=Token)
def ingresar(datos: Ingreso, db: Sesion, origen: Origen):
    try:
        return servicios.ingresar(db, datos.correo, datos.clave, datos.codigo_mfa, origen)
    except servicios.NoAutenticado as e:
        raise _no_autenticado(e) from e


@auth.post("/token", response_model=Token, include_in_schema=True, summary="Ingreso por formulario (para la documentación interactiva)")
def token(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: Sesion, origen: Origen):
    """Mismo ingreso que /auth/ingresar. Con verificación en dos pasos, escriba el código en «client_secret»."""
    try:
        return servicios.ingresar(db, form.username, form.password, form.client_secret, origen)
    except servicios.NoAutenticado as e:
        raise _no_autenticado(e) from e


@auth.get("/yo", response_model=Yo)
def yo(usuario: UsuarioSesion, db: Sesion):
    from arca.modulos.m03_configuracion.servicios import mfa_exigido  # noqa: PLC0415

    organizaciones = [
        MembresiaResumen(organizacion_id=m.tenant_id, organizacion=m.organizacion.nombre, rol=m.rol.nombre, permisos=sorted(m.rol.permisos),
                         mfa_exigido=mfa_exigido(db, m))
        for m in membresias_vigentes(usuario)
    ]
    return Yo(
        id=usuario.id,
        correo=usuario.correo,
        nombre_completo=usuario.nombre_completo,
        es_operador=usuario.es_operador,
        debe_cambiar_clave=usuario.debe_cambiar_clave,
        mfa_activo=usuario.mfa_activo,
        organizaciones=organizaciones,
    )


@auth.post("/cambiar-clave", response_model=Token)
def cambiar_clave(datos: CambioClave, db: Sesion, usuario: UsuarioSesion, origen: Origen):
    return servicios.cambiar_clave(db, usuario, datos.clave_actual, datos.clave_nueva, origen)


@auth.post("/cerrar-sesiones", status_code=status.HTTP_204_NO_CONTENT)
def cerrar_sesiones(db: Sesion, usuario: UsuarioSesion, origen: Origen):
    servicios.cerrar_sesiones(db, usuario, origen)


@auth.post("/mfa/iniciar")
def iniciar_mfa(db: Sesion, usuario: UsuarioSesion) -> dict[str, str]:
    """Devuelve el secreto y la URI otpauth para registrarlo en la aplicación autenticadora."""
    return servicios.iniciar_mfa(db, usuario)


@auth.post("/mfa/confirmar", status_code=status.HTTP_204_NO_CONTENT)
def confirmar_mfa(datos: CodigoMfa, db: Sesion, usuario: UsuarioSesion, origen: Origen):
    """Activa la verificación en dos pasos y cierra las sesiones abiertas (hay que ingresar con código)."""
    servicios.confirmar_mfa(db, usuario, datos.codigo, origen)


# --- Usuarios de la organización --------------------------------------------------------------


@usuarios.get("", response_model=list[MiembroSalida])
def listar_usuarios(ctx: Administrador):
    return [_miembro(m) for m in servicios.membresias(ctx.db, ctx.tenant_id)]


@usuarios.get("/directorio", response_model=list[PersonaDirectorio])
def directorio(ctx: Ctx):
    """Personas activas de la organización, para escoger responsable y equipo de un proyecto."""
    if not (ctx.puede(Permiso.USUARIOS) or ctx.puede(Permiso.PROYECTOS)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Su rol no tiene permiso para esta acción")
    return [
        PersonaDirectorio(usuario_id=m.usuario_id, nombre_completo=m.usuario.nombre_completo, correo=m.usuario.correo, rol=m.rol.nombre)
        for m in servicios.membresias(ctx.db, ctx.tenant_id)
        if m.activa
    ]


@usuarios.post("", status_code=status.HTTP_201_CREATED, response_model=UsuarioAgregado)
def agregar_usuario(datos: UsuarioNuevo, ctx: Administrador):
    m, temporal = servicios.agregar_usuario(ctx, datos.correo, datos.nombre_completo, datos.rol_id, datos.proyectos)
    enviada = bool(temporal) and servicios.entregar_temporal(m.usuario.correo, m.usuario.nombre_completo, temporal, ctx.organizacion.nombre, "Le crearon una cuenta")
    return UsuarioAgregado(miembro=_miembro(m), clave_temporal=None if enviada else temporal, enviada_por_correo=enviada)


@usuarios.patch("/{usuario_id}", response_model=MiembroSalida)
def cambiar_acceso(usuario_id: uuid.UUID, datos: CambioAcceso, ctx: Administrador):
    m = servicios.cambiar_acceso(ctx, usuario_id, datos.rol_id, datos.proyectos, "proyectos" in datos.model_fields_set, datos.motivo)
    return _miembro(m)


@usuarios.post("/{usuario_id}/desactivar", response_model=MiembroSalida)
def desactivar(usuario_id: uuid.UUID, datos: Motivo, ctx: Administrador):
    return _miembro(servicios.cambiar_estado_membresia(ctx, usuario_id, False, datos.motivo))


@usuarios.post("/{usuario_id}/reactivar", response_model=MiembroSalida)
def reactivar(usuario_id: uuid.UUID, datos: Motivo, ctx: Administrador):
    return _miembro(servicios.cambiar_estado_membresia(ctx, usuario_id, True, datos.motivo))


@usuarios.post("/{usuario_id}/revocar-sesiones", status_code=status.HTTP_204_NO_CONTENT)
def revocar_sesiones(usuario_id: uuid.UUID, datos: Motivo, ctx: Administrador):
    servicios.revocar_sesiones(ctx, usuario_id, datos.motivo)


@usuarios.post("/{usuario_id}/restablecer-clave")
def restablecer_clave(usuario_id: uuid.UUID, datos: Motivo, ctx: Administrador) -> dict[str, Any]:
    temporal = servicios.restablecer_clave(ctx, usuario_id, datos.motivo)
    u = ctx.db.get(Usuario, usuario_id)
    enviada = servicios.entregar_temporal(u.correo, u.nombre_completo, temporal, ctx.organizacion.nombre, "Le restablecieron la contraseña")
    return {"clave_temporal": None if enviada else temporal, "enviada_por_correo": enviada}


class Recuperacion(BaseModel):
    correo: EmailStr


class Restablecimiento(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    clave_nueva: str = Field(min_length=1, max_length=200)


@auth.post("/recuperar")
def recuperar(datos: Recuperacion, db: Sesion, origen: Origen) -> dict[str, str]:
    """Pide un enlace para restablecer la contraseña. Siempre responde lo mismo, exista o no la cuenta."""
    servicios.solicitar_recuperacion(db, datos.correo, origen)
    return {"mensaje": "Si el correo está registrado y la plataforma tiene correo configurado, le enviamos un enlace para restablecer la contraseña."}


@auth.post("/restablecer", status_code=status.HTTP_204_NO_CONTENT)
def restablecer(datos: Restablecimiento, db: Sesion, origen: Origen):
    servicios.restablecer_con_token(db, datos.token, datos.clave_nueva, origen)


# --- Roles ------------------------------------------------------------------------------------


@roles.get("/permisos")
def catalogo_permisos(_: Ctx) -> list[str]:
    return TODOS


@roles.get("", response_model=list[RolSalida])
def listar_roles(ctx: Ctx):
    if not (ctx.puede(Permiso.ROLES) or ctx.puede(Permiso.USUARIOS)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Su rol no tiene permiso para esta acción")
    return servicios.roles(ctx.db, ctx.tenant_id)


@roles.post("", status_code=status.HTTP_201_CREATED, response_model=RolSalida)
def crear_rol(datos: RolNuevo, ctx: GestorRoles):
    return servicios.crear_rol(ctx, datos.nombre, datos.descripcion, datos.permisos)


@roles.patch("/{rol_id}", response_model=RolSalida)
def editar_rol(rol_id: uuid.UUID, datos: RolCambios, ctx: GestorRoles):
    return servicios.editar_rol(ctx, rol_id, datos.descripcion, datos.permisos, datos.motivo)
