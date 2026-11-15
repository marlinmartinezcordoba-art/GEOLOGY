"""M03 Configuración institucional: parámetros versionados con vigencia.

Reglas:
- Un parámetro no se edita: se publica una versión nueva con su fecha de vigencia y su motivo.
- La vigencia no puede ser pasada. Así una configuración nueva solo afecta lo que ocurra desde su
  vigencia y un proceso histórico se sigue explicando con la configuración que tenía.
- Un parámetro de proyecto prevalece sobre el de la organización con la misma clave.
"""

import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from arca.modelos import Parametro, Proyecto
from arca.modelos.base import ahora_utc, en_utc
from arca.nucleo.errores import DatosInvalidos, NoEncontrado

_CLAVE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
# Tolerancia para la hora del cliente al publicar con vigencia «ahora».
_TOLERANCIA = timedelta(minutes=2)

# Parámetros que ARCA ya interpreta. Los demás se guardan pero ningún proceso los lee todavía.
CONOCIDOS: dict[str, str] = {
    "seguridad.mfa_privilegiados": "true exige verificación en dos pasos a los roles que administran usuarios, roles o configuración (anterior a seguridad.mfa_obligatorio)",
    "seguridad.mfa_obligatorio": "A quién se exige verificación en dos pasos: «ninguno», «privilegiados» (administran usuarios, roles o configuración), «direccion» (además, quien dirige proyectos, aprueba instrumentos o ve lo reservado) o «todos»",
    "entrega.indexacion": "Archivo de indexación para el SGDEA de la entidad: columnas {nombre, campo}, «por» expediente o documento, separador y nombre del archivo (va en el paquete de entrega)",
    "digitalizacion.perfil": "Perfil de digitalización del proyecto: formatos, resolución, color, blancos, rechazo automático e identificación de expedientes",
}


NIVELES_MFA = ("ninguno", "privilegiados", "direccion", "todos")
DIRECCION = {"proyectos:gestionar", "instrumentos:aprobar", "consulta:reservada", "disposicion:aprobar"}


def mfa_exigido(db: Session, membresia) -> bool:
    """Si la organización exige verificación en dos pasos a esta membresía (por su rol)."""
    from arca.nucleo.permisos import PRIVILEGIADOS  # noqa: PLC0415

    nivel = valor_vigente(db, membresia.tenant_id, "seguridad.mfa_obligatorio", por_defecto=None)
    if nivel is None:
        nivel = "privilegiados" if valor_vigente(db, membresia.tenant_id, "seguridad.mfa_privilegiados", por_defecto=False) is True else "ninguno"
    permisos = set(membresia.rol.permisos)
    if nivel == "todos":
        return True
    if nivel == "direccion":
        return bool(PRIVILEGIADOS & permisos or DIRECCION & permisos)
    if nivel == "privilegiados":
        return bool(PRIVILEGIADOS & permisos)
    return False


def _validar_clave(clave: str) -> None:
    if not _CLAVE.match(clave):
        raise DatosInvalidos("La clave debe ir en minúsculas con al menos un punto, por ejemplo «seguridad.mfa_privilegiados»")


def _validar_valor(clave: str, valor) -> None:
    if clave == "seguridad.mfa_privilegiados" and not isinstance(valor, bool):
        raise DatosInvalidos("«seguridad.mfa_privilegiados» solo admite true o false")
    if clave == "seguridad.mfa_obligatorio" and valor not in NIVELES_MFA:
        raise DatosInvalidos(f"«seguridad.mfa_obligatorio» admite: {', '.join(NIVELES_MFA)}")
    if clave == "entrega.indexacion":
        from arca.modulos.entrega import indexacion  # noqa: PLC0415

        try:
            indexacion.validar(valor)
        except ValueError as e:
            raise DatosInvalidos(str(e)) from e
    if clave == "digitalizacion.perfil":
        from arca.modulos.m10_digitalizacion import perfil  # noqa: PLC0415

        try:
            perfil.validar(valor)
        except ValueError as e:
            raise DatosInvalidos(str(e)) from e


def _proyecto_del_tenant(db: Session, tenant_id: uuid.UUID, proyecto_id: uuid.UUID | None) -> None:
    if proyecto_id is None:
        return
    proyecto = db.get(Proyecto, proyecto_id)
    if proyecto is None or proyecto.tenant_id != tenant_id:
        raise NoEncontrado("El proyecto no existe")


def publicar(db: Session, ctx, clave: str, valor, motivo: str, vigente_desde: datetime | None = None, proyecto_id: uuid.UUID | None = None) -> Parametro:
    _validar_clave(clave)
    _validar_valor(clave, valor)
    _proyecto_del_tenant(db, ctx.tenant_id, proyecto_id)
    ahora = ahora_utc()
    vigencia = en_utc(vigente_desde) if vigente_desde else ahora
    if vigencia < ahora - _TOLERANCIA:
        raise DatosInvalidos("La vigencia no puede ser pasada: una configuración nueva no cambia lo ya ocurrido")
    vigencia = max(vigencia, ahora)
    filtro = [
        Parametro.tenant_id == ctx.tenant_id,
        Parametro.clave == clave,
        Parametro.proyecto_id.is_(None) if proyecto_id is None else Parametro.proyecto_id == proyecto_id,
    ]
    ultima = db.scalar(select(func.max(Parametro.version)).where(*filtro)) or 0
    parametro = Parametro(
        tenant_id=ctx.tenant_id,
        proyecto_id=proyecto_id,
        clave=clave,
        version=ultima + 1,
        valor=valor,
        vigente_desde=vigencia,
        motivo=motivo,
        creado_en=ahora,
        creado_por=ctx.usuario.id,
    )
    db.add(parametro)
    db.flush()
    ctx.auditar(
        accion="PUBLICAR_PARAMETRO",
        objeto="Parametro",
        objeto_id=parametro.id,
        motivo=motivo,
        detalle=f"{clave} v{parametro.version} vigente desde {vigencia.isoformat()}" + (f" (proyecto {proyecto_id})" if proyecto_id else ""),
        cambios={"valor": [None, valor]},
    )
    db.commit()
    return parametro


def _vigente(db: Session, tenant_id: uuid.UUID, clave: str, proyecto_id: uuid.UUID | None, fecha: datetime) -> Parametro | None:
    filtro_proyecto = Parametro.proyecto_id.is_(None) if proyecto_id is None else Parametro.proyecto_id == proyecto_id
    return db.scalar(
        select(Parametro)
        .where(Parametro.tenant_id == tenant_id, Parametro.clave == clave, filtro_proyecto, Parametro.vigente_desde <= fecha)
        .order_by(Parametro.vigente_desde.desc(), Parametro.version.desc())
        .limit(1)
    )


def parametro_vigente(db: Session, tenant_id: uuid.UUID, clave: str, proyecto_id: uuid.UUID | None = None, fecha: datetime | None = None) -> Parametro | None:
    """La versión que regía en `fecha` (ahora, por defecto). El del proyecto prevalece sobre el de la organización."""
    fecha = en_utc(fecha) if fecha else ahora_utc()
    if proyecto_id is not None and (propio := _vigente(db, tenant_id, clave, proyecto_id, fecha)) is not None:
        return propio
    return _vigente(db, tenant_id, clave, None, fecha)


def valor_vigente(db: Session, tenant_id: uuid.UUID, clave: str, por_defecto=None, proyecto_id: uuid.UUID | None = None, fecha: datetime | None = None):
    parametro = parametro_vigente(db, tenant_id, clave, proyecto_id, fecha)
    return por_defecto if parametro is None else parametro.valor


def vigentes(db: Session, tenant_id: uuid.UUID, proyecto_id: uuid.UUID | None = None, fecha: datetime | None = None) -> list[Parametro]:
    filtro = [Parametro.tenant_id == tenant_id]
    filtro.append(Parametro.proyecto_id.is_(None) if proyecto_id is None else Parametro.proyecto_id.in_([proyecto_id]) | Parametro.proyecto_id.is_(None))
    claves = db.scalars(select(Parametro.clave).where(*filtro).distinct()).all()
    resultado = [parametro_vigente(db, tenant_id, clave, proyecto_id, fecha) for clave in sorted(claves)]
    return [p for p in resultado if p is not None]


def historial(db: Session, tenant_id: uuid.UUID, clave: str, proyecto_id: uuid.UUID | None = None) -> list[Parametro]:
    filtro_proyecto = Parametro.proyecto_id.is_(None) if proyecto_id is None else Parametro.proyecto_id == proyecto_id
    return list(db.scalars(select(Parametro).where(Parametro.tenant_id == tenant_id, Parametro.clave == clave, filtro_proyecto).order_by(Parametro.version)))
