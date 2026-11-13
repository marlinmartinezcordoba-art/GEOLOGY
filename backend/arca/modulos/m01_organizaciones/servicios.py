"""M01 Administración de organizaciones y tenants.

Reglas:
- Crear la organización crea el tenant, siembra los roles base y deja un administrador con acceso.
- Suspender y reactivar exigen motivo. Una organización suspendida no atiende a sus usuarios, pero
  nada se borra: sus datos y su auditoría se conservan.
- El operador de la plataforma administra organizaciones; no obtiene por ello acceso a su contenido.
"""

import re
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from arca.modelos import EstadoOrganizacion, Membresia, Organizacion, Proyecto, Rol, TipoIdentificacion, Usuario
from arca.modulos.m25_auditoria.servicios import aplicar_cambios, registrar
from arca.nucleo.errores import Conflicto, DatosInvalidos, NoEncontrado, TransicionInvalida
from arca.nucleo.permisos import ADMINISTRADOR, ROLES_BASE
from arca.nucleo.seguridad import clave_temporal, hashear_clave, normalizar_nit

# Límites que la plataforma ya sabe hacer cumplir. Otros (almacenamiento, consumo de IA) llegan con ARC-27.
LIMITES_SOPORTADOS = {"usuarios", "proyectos"}
_IDIOMA = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")


def validar_identificacion(tipo: str, identificacion: str) -> str:
    if tipo == TipoIdentificacion.NIT.value:
        try:
            return normalizar_nit(identificacion)
        except ValueError as e:
            raise DatosInvalidos(str(e)) from e
    limpio = identificacion.strip()
    if len(limpio) < 3:
        raise DatosInvalidos("La identificación es demasiado corta")
    return limpio


def validar_zona_e_idioma(zona_horaria: str, idioma: str) -> None:
    try:
        ZoneInfo(zona_horaria)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise DatosInvalidos(f"Zona horaria desconocida: {zona_horaria}") from e
    if not _IDIOMA.match(idioma):
        raise DatosInvalidos("Idioma inválido: use un código como es-CO")


def validar_limites(limites: dict) -> dict:
    desconocidos = set(limites) - LIMITES_SOPORTADOS
    if desconocidos:
        raise DatosInvalidos(f"Límites no soportados todavía: {', '.join(sorted(desconocidos))}")
    for clave, valor in limites.items():
        if not isinstance(valor, int) or isinstance(valor, bool) or valor < 1:
            raise DatosInvalidos(f"El límite «{clave}» debe ser un entero mayor que cero")
    return dict(limites)


def obtener(db: Session, organizacion_id: uuid.UUID) -> Organizacion:
    org = db.get(Organizacion, organizacion_id)
    if org is None:
        raise NoEncontrado("La organización no existe")
    return org


def sembrar_roles(db: Session, org: Organizacion, actor_id: uuid.UUID | None) -> dict[str, Rol]:
    roles = {}
    for base in ROLES_BASE:
        rol = Rol(
            tenant_id=org.id,
            nombre=base["nombre"],
            descripcion=base["descripcion"],
            permisos=[str(p) for p in base["permisos"]],
            es_base=True,
            creado_por=actor_id,
        )
        db.add(rol)
        roles[rol.nombre] = rol
    db.flush()
    return roles


def obtener_o_crear_usuario(db: Session, correo: str, nombre_completo: str, actor_id: uuid.UUID | None) -> tuple[Usuario, str | None]:
    """Devuelve el usuario y, si se creó, su contraseña temporal (se muestra una sola vez)."""
    correo = correo.strip().lower()
    usuario = db.scalar(select(Usuario).where(Usuario.correo == correo))
    if usuario is not None:
        return usuario, None
    temporal = clave_temporal()
    usuario = Usuario(correo=correo, nombre_completo=nombre_completo.strip(), clave_hash=hashear_clave(temporal), debe_cambiar_clave=True, creado_por=actor_id)
    db.add(usuario)
    db.flush()
    return usuario, temporal


def crear(db: Session, operador: Usuario, datos: dict, origen) -> tuple[Organizacion, Usuario, str | None]:
    identificacion = validar_identificacion(datos["tipo_identificacion"], datos["identificacion"])
    validar_zona_e_idioma(datos["zona_horaria"], datos["idioma"])
    limites = validar_limites(datos.get("limites") or {})
    if db.scalar(select(Organizacion).where(Organizacion.identificacion == identificacion)):
        raise Conflicto("Ya existe una organización con esa identificación")

    org = Organizacion(
        nombre=datos["nombre"].strip(),
        razon_social=datos["razon_social"].strip(),
        tipo_identificacion=datos["tipo_identificacion"],
        identificacion=identificacion,
        zona_horaria=datos["zona_horaria"],
        idioma=datos["idioma"],
        limites=limites,
        creado_por=operador.id,
    )
    db.add(org)
    db.flush()
    roles = sembrar_roles(db, org, operador.id)
    admin = datos["administrador"]
    usuario, temporal = obtener_o_crear_usuario(db, admin["correo"], admin["nombre_completo"], operador.id)
    db.add(Membresia(tenant_id=org.id, usuario_id=usuario.id, rol_id=roles[ADMINISTRADOR].id, creado_por=operador.id))

    comun = {"usuario": operador, "ip": origen.ip, "agente": origen.agente, "correlacion_id": origen.correlacion_id}
    registrar(db, tenant_id=None, accion="CREAR_ORGANIZACION", objeto="Organizacion", objeto_id=org.id, detalle=f"{org.nombre} ({org.identificacion})", **comun)
    registrar(
        db, tenant_id=org.id, accion="CREAR_ORGANIZACION", objeto="Organizacion", objeto_id=org.id, detalle=f"Administrador inicial: {usuario.correo}", **comun
    )
    db.commit()
    return org, usuario, temporal


def actualizar(db: Session, operador: Usuario, org: Organizacion, nuevos: dict, motivo: str, origen) -> Organizacion:
    nuevos = {k: v for k, v in nuevos.items() if v is not None or k == "limites"}
    if "zona_horaria" in nuevos or "idioma" in nuevos:
        validar_zona_e_idioma(nuevos.get("zona_horaria", org.zona_horaria), nuevos.get("idioma", org.idioma))
    if "limites" in nuevos:
        nuevos["limites"] = validar_limites(nuevos["limites"] or {})
    nuevos = {k: v.strip() if isinstance(v, str) else v for k, v in nuevos.items()}
    diferencias = aplicar_cambios(org, nuevos)
    if diferencias:
        org.actualizado_por = operador.id
        for clave in (None, org.id):
            registrar(
                db,
                tenant_id=clave,
                usuario=operador,
                accion="EDITAR_ORGANIZACION",
                objeto="Organizacion",
                objeto_id=org.id,
                motivo=motivo,
                cambios=diferencias,
                ip=origen.ip,
                agente=origen.agente,
                correlacion_id=origen.correlacion_id,
            )
        db.commit()
    return org


def cambiar_estado(db: Session, operador: Usuario, org: Organizacion, destino: EstadoOrganizacion, motivo: str, origen) -> Organizacion:
    if org.estado == destino.value:
        raise TransicionInvalida(f"La organización ya está {destino.value}")
    anterior = org.estado
    org.estado, org.motivo_estado, org.actualizado_por = destino.value, motivo, operador.id
    accion = "SUSPENDER_ORGANIZACION" if destino == EstadoOrganizacion.SUSPENDIDA else "REACTIVAR_ORGANIZACION"
    for clave in (None, org.id):
        registrar(
            db,
            tenant_id=clave,
            usuario=operador,
            accion=accion,
            objeto="Organizacion",
            objeto_id=org.id,
            motivo=motivo,
            cambios={"estado": [anterior, destino.value]},
            ip=origen.ip,
            agente=origen.agente,
            correlacion_id=origen.correlacion_id,
        )
    db.commit()
    return org


def uso(db: Session, org: Organizacion) -> dict[str, int]:
    usuarios = db.scalar(select(func.count()).select_from(Membresia).where(Membresia.tenant_id == org.id, Membresia.activa.is_(True))) or 0
    proyectos = db.scalar(select(func.count()).select_from(Proyecto).where(Proyecto.tenant_id == org.id)) or 0
    return {"usuarios": usuarios, "proyectos": proyectos}


def exigir_cupo(db: Session, org: Organizacion, recurso: str) -> None:
    """ARC-27 parcial: no se crea un recurso por encima del límite del plan."""
    limite = (org.limites or {}).get(recurso)
    if limite is not None and uso(db, org)[recurso] >= limite:
        raise Conflicto(f"La organización alcanzó su límite de {recurso} ({limite}). Solicite ampliarlo al operador de la plataforma.")
