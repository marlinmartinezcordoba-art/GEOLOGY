"""M02 Usuarios, roles y permisos: ingreso, verificación en dos pasos y administración por organización.

Reglas:
- Denegar por defecto: el rol de la membresía activa dice qué se puede hacer.
- El ingreso no revela si un correo existe. Tras N intentos fallidos la cuenta se bloquea.
- Nadie cambia su propio rol, ni edita el rol que tiene, ni desactiva su propia membresía.
- La organización nunca se queda sin alguien que administre usuarios.
- Restablecer la contraseña de alguien que pertenece a otras organizaciones le corresponde al operador.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from arca.modelos import Membresia, Proyecto, Rol, Usuario
from arca.modelos.base import ahora_utc
from arca.modulos.m01_organizaciones.servicios import exigir_cupo, obtener_o_crear_usuario
from arca.modulos.m25_auditoria.servicios import registrar
from arca.nucleo.config import ajustes
from arca.nucleo.errores import AccesoDenegado, Conflicto, DatosInvalidos, ErrorDominio, NoEncontrado, TransicionInvalida
from arca.nucleo.permisos import Permiso, validar_permisos
from arca.nucleo.seguridad import clave_temporal, crear_token, hashear_clave, nuevo_secreto_totp, uri_totp, verificar_clave, verificar_totp


class NoAutenticado(ErrorDominio):
    codigo_http = 401


class MfaRequerido(NoAutenticado):
    pass


# --- Ingreso y sesión ---------------------------------------------------------------------------


def _evento_plataforma(
    db: Session, usuario: Usuario | None, accion: str, origen, detalle: str = "", resultado: str = "exito", nombre: str | None = None
) -> None:
    registrar(
        db,
        tenant_id=None,
        usuario=usuario,
        accion=accion,
        objeto="Usuario",
        objeto_id=usuario.id if usuario else None,
        detalle=detalle,
        resultado=resultado,
        ip=origen.ip,
        agente=origen.agente,
        correlacion_id=origen.correlacion_id,
        usuario_nombre=nombre,
    )


def _fallo(db: Session, usuario: Usuario | None, correo: str, origen, causa: str) -> None:
    if usuario is not None:
        usuario.intentos_fallidos += 1
        if usuario.intentos_fallidos >= ajustes().intentos_antes_de_bloquear and not usuario.bloqueado:
            usuario.bloqueado, usuario.motivo_bloqueo = True, "Bloqueo automático por intentos fallidos de ingreso"
            usuario.version_sesion += 1
            _evento_plataforma(db, usuario, "BLOQUEO_AUTOMATICO", origen, detalle=f"{usuario.intentos_fallidos} intentos fallidos")
    _evento_plataforma(
        db, usuario, "INGRESO_FALLIDO", origen, detalle=causa, resultado="bloqueado", nombre=None if usuario else f"(correo no registrado) {correo[:120]}"
    )
    db.commit()


def ingresar(db: Session, correo: str, clave: str, codigo_mfa: str | None, origen) -> dict[str, Any]:
    correo = correo.strip().lower()
    usuario = db.scalar(select(Usuario).where(Usuario.correo == correo))
    if not verificar_clave(clave, usuario.clave_hash if usuario else None):
        _fallo(db, usuario, correo, origen, "Contraseña incorrecta")
        raise NoAutenticado("Correo o contraseña incorrectos")
    assert usuario is not None
    if usuario.bloqueado or not usuario.activo:
        _evento_plataforma(db, usuario, "INGRESO_FALLIDO", origen, detalle="Cuenta bloqueada o inactiva", resultado="bloqueado")
        db.commit()
        raise NoAutenticado("La cuenta está bloqueada o inactiva. Comuníquese con el administrador de su organización.")
    if usuario.mfa_activo:
        if not codigo_mfa:
            raise MfaRequerido("Escriba el código de verificación en dos pasos")
        if not verificar_totp(usuario.mfa_secreto or "", codigo_mfa):
            _fallo(db, usuario, correo, origen, "Código de verificación incorrecto")
            raise NoAutenticado("El código de verificación no es válido")
    usuario.intentos_fallidos = 0
    usuario.ultimo_ingreso = ahora_utc()
    _evento_plataforma(db, usuario, "INGRESO", origen)
    db.commit()
    return {"access_token": crear_token(usuario.id, usuario.version_sesion), "token_type": "bearer", "debe_cambiar_clave": usuario.debe_cambiar_clave}


def validar_clave_nueva(clave: str, correo: str) -> None:
    minimo = ajustes().longitud_minima_clave
    if len(clave) < minimo:
        raise DatosInvalidos(f"La contraseña debe tener al menos {minimo} caracteres")
    if correo.split("@")[0].lower() in clave.lower():
        raise DatosInvalidos("La contraseña no puede contener su usuario de correo")


def cambiar_clave(db: Session, usuario: Usuario, actual: str, nueva: str, origen) -> dict[str, Any]:
    if not verificar_clave(actual, usuario.clave_hash):
        raise DatosInvalidos("La contraseña actual no es correcta")
    if actual == nueva:
        raise DatosInvalidos("La contraseña nueva debe ser distinta de la actual")
    validar_clave_nueva(nueva, usuario.correo)
    usuario.clave_hash, usuario.debe_cambiar_clave = hashear_clave(nueva), False
    usuario.version_sesion += 1  # cierra las demás sesiones
    _evento_plataforma(db, usuario, "CAMBIAR_CLAVE", origen)
    db.commit()
    return {"access_token": crear_token(usuario.id, usuario.version_sesion), "token_type": "bearer", "debe_cambiar_clave": False}


def cerrar_sesiones(db: Session, usuario: Usuario, origen) -> None:
    usuario.version_sesion += 1
    _evento_plataforma(db, usuario, "CERRAR_SESIONES", origen)
    db.commit()


def iniciar_mfa(db: Session, usuario: Usuario) -> dict[str, str]:
    if usuario.mfa_activo:
        raise TransicionInvalida("La verificación en dos pasos ya está activa")
    usuario.mfa_secreto = nuevo_secreto_totp()
    db.commit()
    return {"secreto": usuario.mfa_secreto, "uri": uri_totp(usuario.mfa_secreto, usuario.correo)}


def confirmar_mfa(db: Session, usuario: Usuario, codigo: str, origen) -> None:
    if usuario.mfa_activo:
        raise TransicionInvalida("La verificación en dos pasos ya está activa")
    if not usuario.mfa_secreto or not verificar_totp(usuario.mfa_secreto, codigo):
        raise DatosInvalidos("El código no corresponde. Revise la hora de su teléfono e inténtelo de nuevo.")
    usuario.mfa_activo = True
    usuario.version_sesion += 1
    _evento_plataforma(db, usuario, "ACTIVAR_MFA", origen)
    db.commit()


# --- Administración de usuarios de la organización --------------------------------------------


def _rol_del_tenant(db: Session, tenant_id: uuid.UUID, rol_id: uuid.UUID) -> Rol:
    rol = db.get(Rol, rol_id)
    if rol is None or rol.tenant_id != tenant_id:
        raise NoEncontrado("El rol no existe")
    return rol


def _validar_alcance(db: Session, tenant_id: uuid.UUID, proyectos: list[uuid.UUID] | None) -> list[str] | None:
    if proyectos is None:
        return None
    unicos = set(proyectos)
    encontrados = db.scalar(select(func.count()).select_from(Proyecto).where(Proyecto.tenant_id == tenant_id, Proyecto.id.in_(unicos))) if unicos else 0
    if encontrados != len(unicos):
        raise NoEncontrado("Uno o más proyectos del alcance no existen")
    return sorted(str(p) for p in unicos)


def membresia(db: Session, tenant_id: uuid.UUID, usuario_id: uuid.UUID) -> Membresia:
    m = db.scalar(select(Membresia).where(Membresia.tenant_id == tenant_id, Membresia.usuario_id == usuario_id))
    if m is None:
        raise NoEncontrado("El usuario no pertenece a esta organización")
    return m


def membresias(db: Session, tenant_id: uuid.UUID) -> list[Membresia]:
    return list(
        db.scalars(
            select(Membresia).where(Membresia.tenant_id == tenant_id).join(Usuario, Membresia.usuario_id == Usuario.id).order_by(Usuario.nombre_completo)
        )
    )


def _administra(m: Membresia) -> bool:
    return m.activa and Permiso.USUARIOS.value in (m.rol.permisos or [])


def _proteger_ultimo_administrador(db: Session, objetivo: Membresia, queda_administrando: bool) -> None:
    if queda_administrando or not _administra(objetivo):
        return
    otros = [m for m in membresias(db, objetivo.tenant_id) if m.id != objetivo.id and _administra(m)]
    if not otros:
        raise Conflicto("La organización se quedaría sin nadie que administre usuarios")


def _no_a_si_mismo(ctx, usuario_id: uuid.UUID) -> None:
    if ctx.usuario.id == usuario_id:
        raise AccesoDenegado("No puede cambiar su propio acceso: pídalo a otro administrador (segregación de funciones)")


def agregar_usuario(ctx, correo: str, nombre_completo: str, rol_id: uuid.UUID, proyectos: list[uuid.UUID] | None) -> tuple[Membresia, str | None]:
    db = ctx.db
    rol = _rol_del_tenant(db, ctx.tenant_id, rol_id)
    alcance = _validar_alcance(db, ctx.tenant_id, proyectos)
    usuario, temporal = obtener_o_crear_usuario(db, correo, nombre_completo, ctx.usuario.id)
    if db.scalar(select(Membresia).where(Membresia.tenant_id == ctx.tenant_id, Membresia.usuario_id == usuario.id)):
        raise Conflicto("Ese usuario ya pertenece a la organización")
    exigir_cupo(db, ctx.organizacion, "usuarios")
    m = Membresia(tenant_id=ctx.tenant_id, usuario_id=usuario.id, rol_id=rol.id, proyectos=alcance, creado_por=ctx.usuario.id)
    db.add(m)
    db.flush()
    ctx.auditar(
        accion="AGREGAR_USUARIO",
        objeto="Membresia",
        objeto_id=m.id,
        detalle=f"{usuario.correo} con rol «{rol.nombre}»" + (" (cuenta nueva)" if temporal else ""),
        cambios={"rol": [None, rol.nombre], "proyectos": [None, alcance]},
    )
    db.commit()
    db.refresh(m)
    return m, temporal


def cambiar_acceso(ctx, usuario_id: uuid.UUID, rol_id: uuid.UUID | None, proyectos: list[uuid.UUID] | None, cambiar_proyectos: bool, motivo: str) -> Membresia:
    _no_a_si_mismo(ctx, usuario_id)
    db = ctx.db
    m = membresia(db, ctx.tenant_id, usuario_id)
    cambios: dict[str, list] = {}
    if rol_id is not None and rol_id != m.rol_id:
        nuevo = _rol_del_tenant(db, ctx.tenant_id, rol_id)
        _proteger_ultimo_administrador(db, m, Permiso.USUARIOS.value in nuevo.permisos)
        cambios["rol"] = [m.rol.nombre, nuevo.nombre]
        m.rol_id, m.rol = nuevo.id, nuevo
    if cambiar_proyectos:
        alcance = _validar_alcance(db, ctx.tenant_id, proyectos)
        if alcance != m.proyectos:
            cambios["proyectos"] = [m.proyectos, alcance]
            m.proyectos = alcance
    if cambios:
        m.actualizado_por = ctx.usuario.id
        ctx.auditar(accion="CAMBIAR_ACCESO", objeto="Membresia", objeto_id=m.id, motivo=motivo, cambios=cambios)
        db.commit()
    return m


def cambiar_estado_membresia(ctx, usuario_id: uuid.UUID, activa: bool, motivo: str) -> Membresia:
    _no_a_si_mismo(ctx, usuario_id)
    db = ctx.db
    m = membresia(db, ctx.tenant_id, usuario_id)
    if m.activa == activa:
        raise TransicionInvalida("El usuario ya está " + ("activo" if activa else "desactivado") + " en la organización")
    if activa:
        exigir_cupo(db, ctx.organizacion, "usuarios")
    else:
        _proteger_ultimo_administrador(db, m, False)
    m.activa, m.motivo_estado, m.actualizado_por = activa, motivo, ctx.usuario.id
    ctx.auditar(
        accion="REACTIVAR_USUARIO" if activa else "DESACTIVAR_USUARIO",
        objeto="Membresia",
        objeto_id=m.id,
        motivo=motivo,
        cambios={"activa": [not activa, activa]},
    )
    db.commit()
    return m


def revocar_sesiones(ctx, usuario_id: uuid.UUID, motivo: str) -> None:
    m = membresia(ctx.db, ctx.tenant_id, usuario_id)
    m.usuario.version_sesion += 1
    ctx.auditar(accion="REVOCAR_SESIONES", objeto="Usuario", objeto_id=usuario_id, motivo=motivo)
    ctx.db.commit()


def restablecer_clave(ctx, usuario_id: uuid.UUID, motivo: str) -> str:
    _no_a_si_mismo(ctx, usuario_id)
    db = ctx.db
    m = membresia(db, ctx.tenant_id, usuario_id)
    otras = db.scalar(select(func.count()).select_from(Membresia).where(Membresia.usuario_id == usuario_id, Membresia.tenant_id != ctx.tenant_id)) or 0
    if otras or m.usuario.es_operador:
        raise Conflicto("Ese usuario pertenece a otras organizaciones: su contraseña la restablece el operador de la plataforma")
    temporal = clave_temporal()
    usuario = m.usuario
    usuario.clave_hash, usuario.debe_cambiar_clave = hashear_clave(temporal), True
    usuario.version_sesion += 1
    usuario.bloqueado, usuario.motivo_bloqueo, usuario.intentos_fallidos = False, None, 0
    ctx.auditar(accion="RESTABLECER_CLAVE", objeto="Usuario", objeto_id=usuario_id, motivo=motivo)
    db.commit()
    return temporal


# --- Roles --------------------------------------------------------------------------------------


def roles(db: Session, tenant_id: uuid.UUID) -> list[Rol]:
    return list(db.scalars(select(Rol).where(Rol.tenant_id == tenant_id).order_by(Rol.es_base.desc(), Rol.nombre)))


def crear_rol(ctx, nombre: str, descripcion: str, permisos: list[str]) -> Rol:
    db = ctx.db
    try:
        permisos = validar_permisos(permisos)
    except ValueError as e:
        raise DatosInvalidos(str(e)) from e
    nombre = nombre.strip()
    if db.scalar(select(Rol).where(Rol.tenant_id == ctx.tenant_id, Rol.nombre == nombre)):
        raise Conflicto("Ya existe un rol con ese nombre")
    rol = Rol(tenant_id=ctx.tenant_id, nombre=nombre, descripcion=descripcion.strip(), permisos=permisos, creado_por=ctx.usuario.id)
    db.add(rol)
    db.flush()
    ctx.auditar(accion="CREAR_ROL", objeto="Rol", objeto_id=rol.id, detalle=nombre, cambios={"permisos": [None, permisos]})
    db.commit()
    return rol


def editar_rol(ctx, rol_id: uuid.UUID, descripcion: str | None, permisos: list[str] | None, motivo: str) -> Rol:
    db = ctx.db
    rol = _rol_del_tenant(db, ctx.tenant_id, rol_id)
    if rol.es_base:
        raise Conflicto("Los roles base no se editan: cree un rol propio")
    if ctx.membresia.rol_id == rol.id:
        raise AccesoDenegado("No puede editar el rol que usted mismo tiene (segregación de funciones)")
    cambios: dict[str, list] = {}
    if permisos is not None:
        try:
            permisos = validar_permisos(permisos)
        except ValueError as e:
            raise DatosInvalidos(str(e)) from e
        if permisos != sorted(rol.permisos):
            if Permiso.USUARIOS.value not in permisos:
                for m in db.scalars(select(Membresia).where(Membresia.tenant_id == ctx.tenant_id, Membresia.rol_id == rol.id)):
                    _proteger_ultimo_administrador(db, m, False)
            cambios["permisos"] = [sorted(rol.permisos), permisos]
            rol.permisos = permisos
    if descripcion is not None and descripcion.strip() != rol.descripcion:
        cambios["descripcion"] = [rol.descripcion, descripcion.strip()]
        rol.descripcion = descripcion.strip()
    if cambios:
        rol.actualizado_por = ctx.usuario.id
        ctx.auditar(accion="EDITAR_ROL", objeto="Rol", objeto_id=rol.id, motivo=motivo, cambios=cambios)
        db.commit()
    return rol
