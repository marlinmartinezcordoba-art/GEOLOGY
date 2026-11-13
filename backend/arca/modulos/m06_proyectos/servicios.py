"""M06 Proyectos, contratos, sedes y equipo.

Reglas:
- Un proyecto pertenece a una organización y su código es único dentro de ella.
- El alcance (fechas, objeto, contrato, metas, responsable) queda versionado: cada cambio guarda una
  instantánea con su motivo. Un proyecto cerrado no se edita; se reabre con motivo.
- Para activarlo debe tener fechas, al menos una meta, responsable y al menos una sede.
- Las metas se miden por unidad (cajas, folios, imágenes…) y nunca se suman entre unidades distintas.
- Un usuario con alcance limitado solo ve los proyectos de su alcance; los demás responden 404.
"""

import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from arca.modelos import EstadoProyecto, Membresia, MiembroProyecto, Proyecto, Sede, UnidadMeta, VersionProyecto
from arca.modelos.base import ahora_utc
from arca.modulos.m01_organizaciones.servicios import exigir_cupo
from arca.nucleo.errores import Conflicto, DatosInvalidos, NoEncontrado, TransicionInvalida

_CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9\-_.]{1,39}$")
CAMPOS_ALCANCE = ("nombre", "entidad_cliente", "numero_contrato", "objeto", "fecha_inicio", "fecha_fin", "metas", "responsable_id")


def _validar_metas(metas: dict[str, Any]) -> dict[str, int | float]:
    validas = {u.value for u in UnidadMeta}
    desconocidas = set(metas) - validas
    if desconocidas:
        raise DatosInvalidos(f"Unidades de meta no reconocidas: {', '.join(sorted(desconocidas))}. Use: {', '.join(sorted(validas))}")
    for unidad, cantidad in metas.items():
        if isinstance(cantidad, bool) or not isinstance(cantidad, int | float) or cantidad <= 0:
            raise DatosInvalidos(f"La meta de {unidad} debe ser un número mayor que cero")
        if unidad != UnidadMeta.METROS_LINEALES.value and not float(cantidad).is_integer():
            raise DatosInvalidos(f"La meta de {unidad} debe ser un número entero")
    return dict(metas)


def _validar_fechas(inicio: date | None, fin: date | None) -> None:
    if inicio and fin and fin < inicio:
        raise DatosInvalidos("La fecha de fin no puede ser anterior a la de inicio")


def _miembro_activo(db: Session, tenant_id: uuid.UUID, usuario_id: uuid.UUID) -> Membresia:
    m = db.scalar(select(Membresia).where(Membresia.tenant_id == tenant_id, Membresia.usuario_id == usuario_id, Membresia.activa.is_(True)))
    if m is None:
        raise NoEncontrado("El usuario no pertenece a esta organización o está desactivado")
    return m


def _instantanea(p: Proyecto) -> dict[str, Any]:
    datos = {campo: getattr(p, campo) for campo in CAMPOS_ALCANCE}
    datos["estado"] = p.estado
    return {k: (v.isoformat() if isinstance(v, date) else str(v) if isinstance(v, uuid.UUID) else v) for k, v in datos.items()}


def _versionar(db: Session, ctx, p: Proyecto, motivo: str) -> None:
    db.add(
        VersionProyecto(
            tenant_id=p.tenant_id,
            proyecto_id=p.id,
            version=p.version,
            instantanea=_instantanea(p),
            motivo=motivo,
            creado_en=ahora_utc(),
            creado_por=ctx.usuario.id,
        )
    )


def obtener(ctx, proyecto_id: uuid.UUID) -> Proyecto:
    p = ctx.db.get(Proyecto, proyecto_id)
    alcance = ctx.alcance_proyectos
    if p is None or p.tenant_id != ctx.tenant_id or (alcance is not None and p.id not in alcance):
        raise NoEncontrado("El proyecto no existe")
    return p


def listar(ctx, estado: str | None = None) -> list[Proyecto]:
    consulta = select(Proyecto).where(Proyecto.tenant_id == ctx.tenant_id).order_by(Proyecto.codigo)
    if estado:
        consulta = consulta.where(Proyecto.estado == estado)
    alcance = ctx.alcance_proyectos
    if alcance is not None:
        consulta = consulta.where(Proyecto.id.in_(alcance))
    return list(ctx.db.scalars(consulta))


def crear(ctx, datos: dict[str, Any]) -> Proyecto:
    db = ctx.db
    codigo = datos["codigo"].strip().upper()
    if not _CODIGO.match(codigo):
        raise DatosInvalidos("El código debe tener de 2 a 40 caracteres: letras, números, guion, punto o guion bajo")
    if db.scalar(select(Proyecto).where(Proyecto.tenant_id == ctx.tenant_id, Proyecto.codigo == codigo)):
        raise Conflicto("Ya existe un proyecto con ese código")
    exigir_cupo(db, ctx.organizacion, "proyectos")
    _validar_fechas(datos.get("fecha_inicio"), datos.get("fecha_fin"))
    metas = _validar_metas(datos.get("metas") or {})
    if datos.get("responsable_id"):
        _miembro_activo(db, ctx.tenant_id, datos["responsable_id"])
    p = Proyecto(
        tenant_id=ctx.tenant_id,
        codigo=codigo,
        nombre=datos["nombre"].strip(),
        entidad_cliente=datos["entidad_cliente"].strip(),
        numero_contrato=(datos.get("numero_contrato") or "").strip() or None,
        objeto=(datos.get("objeto") or "").strip(),
        fecha_inicio=datos.get("fecha_inicio"),
        fecha_fin=datos.get("fecha_fin"),
        metas=metas,
        responsable_id=datos.get("responsable_id"),
        creado_por=ctx.usuario.id,
    )
    db.add(p)
    db.flush()
    _versionar(db, ctx, p, "Creación del proyecto")
    ctx.auditar(accion="CREAR_PROYECTO", objeto="Proyecto", objeto_id=p.id, detalle=f"{p.codigo} · {p.nombre}", cambios={"alcance": [None, _instantanea(p)]})
    db.commit()
    return p


def editar(ctx, p: Proyecto, nuevos: dict[str, Any], motivo: str) -> Proyecto:
    db = ctx.db
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado: reábralo con motivo para modificarlo")
    nuevos = {k: v for k, v in nuevos.items() if k in CAMPOS_ALCANCE}
    for obligatorio in ("nombre", "entidad_cliente"):
        if obligatorio in nuevos and not (nuevos[obligatorio] or "").strip():
            raise DatosInvalidos(f"«{obligatorio}» no puede quedar vacío")
    if "metas" in nuevos:
        nuevos["metas"] = _validar_metas(nuevos["metas"] or {})
    if nuevos.get("responsable_id"):
        _miembro_activo(db, ctx.tenant_id, nuevos["responsable_id"])
    _validar_fechas(nuevos.get("fecha_inicio", p.fecha_inicio), nuevos.get("fecha_fin", p.fecha_fin))
    if p.estado == EstadoProyecto.ACTIVO.value:
        _exigir_completo(db, p, nuevos)
    cambios: dict[str, list] = {}
    for campo, valor in nuevos.items():
        valor = valor.strip() if isinstance(valor, str) else valor
        if getattr(p, campo) != valor:
            cambios[campo] = [getattr(p, campo), valor]
            setattr(p, campo, valor)
    if cambios:
        p.version += 1
        p.actualizado_por = ctx.usuario.id
        _versionar(db, ctx, p, motivo)
        ctx.auditar(accion="EDITAR_PROYECTO", objeto="Proyecto", objeto_id=p.id, motivo=motivo, cambios=cambios, detalle=f"Versión {p.version}")
        db.commit()
    return p


def _exigir_completo(db: Session, p: Proyecto, nuevos: dict[str, Any] | None = None) -> None:
    datos = {campo: getattr(p, campo) for campo in CAMPOS_ALCANCE} | (nuevos or {})
    faltan = [
        texto
        for texto, ok in (
            ("fecha de inicio", datos["fecha_inicio"]),
            ("fecha de fin", datos["fecha_fin"]),
            ("al menos una meta", datos["metas"]),
            ("responsable", datos["responsable_id"]),
            ("al menos una sede", db.scalar(select(Sede.id).where(Sede.proyecto_id == p.id, Sede.activa.is_(True)).limit(1))),
        )
        if not ok
    ]
    if faltan:
        raise TransicionInvalida("Para que el proyecto esté activo le falta: " + ", ".join(faltan))


def cambiar_estado(ctx, p: Proyecto, destino: EstadoProyecto, motivo: str) -> Proyecto:
    permitidas = {
        EstadoProyecto.ACTIVO: {EstadoProyecto.BORRADOR.value, EstadoProyecto.CERRADO.value},
        EstadoProyecto.CERRADO: {EstadoProyecto.ACTIVO.value},
    }
    if p.estado not in permitidas.get(destino, set()):
        raise TransicionInvalida(f"No se puede pasar de «{p.estado}» a «{destino.value}»")
    if destino == EstadoProyecto.ACTIVO:
        _exigir_completo(ctx.db, p)
    acciones = {
        (EstadoProyecto.BORRADOR.value, EstadoProyecto.ACTIVO): "ACTIVAR_PROYECTO",
        (EstadoProyecto.CERRADO.value, EstadoProyecto.ACTIVO): "REABRIR_PROYECTO",
        (EstadoProyecto.ACTIVO.value, EstadoProyecto.CERRADO): "CERRAR_PROYECTO",
    }
    accion = acciones[(p.estado, destino)]
    anterior = p.estado
    p.estado, p.motivo_estado, p.actualizado_por = destino.value, motivo, ctx.usuario.id
    p.version += 1
    _versionar(ctx.db, ctx, p, motivo)
    ctx.auditar(accion=accion, objeto="Proyecto", objeto_id=p.id, motivo=motivo, cambios={"estado": [anterior, destino.value]})
    ctx.db.commit()
    return p


def versiones(ctx, p: Proyecto) -> list[VersionProyecto]:
    return list(ctx.db.scalars(select(VersionProyecto).where(VersionProyecto.proyecto_id == p.id).order_by(VersionProyecto.version)))


def _no_cerrado(p: Proyecto) -> None:
    if p.estado == EstadoProyecto.CERRADO.value:
        raise TransicionInvalida("El proyecto está cerrado")


def agregar_sede(ctx, p: Proyecto, nombre: str, ciudad: str, direccion: str) -> Sede:
    _no_cerrado(p)
    nombre = nombre.strip()
    if ctx.db.scalar(select(Sede).where(Sede.proyecto_id == p.id, Sede.nombre == nombre)):
        raise Conflicto("El proyecto ya tiene una sede con ese nombre")
    sede = Sede(tenant_id=p.tenant_id, proyecto_id=p.id, nombre=nombre, ciudad=ciudad.strip(), direccion=direccion.strip(), creado_por=ctx.usuario.id)
    ctx.db.add(sede)
    ctx.db.flush()
    ctx.auditar(accion="AGREGAR_SEDE", objeto="Sede", objeto_id=sede.id, detalle=f"{p.codigo} · {nombre} ({ciudad})")
    ctx.db.commit()
    return sede


def sedes(ctx, p: Proyecto) -> list[Sede]:
    return list(ctx.db.scalars(select(Sede).where(Sede.proyecto_id == p.id).order_by(Sede.nombre)))


def asignar_miembro(ctx, p: Proyecto, usuario_id: uuid.UUID, funcion: str) -> MiembroProyecto:
    _no_cerrado(p)
    m = _miembro_activo(ctx.db, ctx.tenant_id, usuario_id)
    if m.proyectos is not None and str(p.id) not in m.proyectos:
        raise Conflicto("El proyecto no está en el alcance de ese usuario: amplíe primero su alcance en Usuarios")
    if ctx.db.scalar(select(MiembroProyecto).where(MiembroProyecto.proyecto_id == p.id, MiembroProyecto.usuario_id == usuario_id)):
        raise Conflicto("El usuario ya está en el equipo del proyecto")
    miembro = MiembroProyecto(tenant_id=p.tenant_id, proyecto_id=p.id, usuario_id=usuario_id, funcion=funcion.strip(), creado_por=ctx.usuario.id)
    ctx.db.add(miembro)
    ctx.db.flush()
    ctx.auditar(accion="ASIGNAR_EQUIPO", objeto="MiembroProyecto", objeto_id=miembro.id, detalle=f"{p.codigo} · {m.usuario.correo} · {funcion}")
    ctx.db.commit()
    return miembro


def equipo(ctx, p: Proyecto) -> list[MiembroProyecto]:
    return list(ctx.db.scalars(select(MiembroProyecto).where(MiembroProyecto.proyecto_id == p.id)))
