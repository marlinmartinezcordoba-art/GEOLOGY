"""M01 Organizaciones (tenants) y M02 identidad: usuarios, roles y membresías."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from arca.modelos.base import Base, CamposControlMixin, IdMixin, Json, TenantMixin


class EstadoOrganizacion(StrEnum):
    ACTIVA = "activa"
    SUSPENDIDA = "suspendida"


class TipoIdentificacion(StrEnum):
    NIT = "NIT"
    EXTRANJERA = "EXTRANJERA"


class Organizacion(IdMixin, CamposControlMixin, Base):
    """Cliente de la plataforma SaaS. Es el tenant: todo lo demás cuelga de aquí."""

    __tablename__ = "organizaciones"

    nombre: Mapped[str] = mapped_column(String(200))
    razon_social: Mapped[str] = mapped_column(String(300))
    tipo_identificacion: Mapped[str] = mapped_column(String(20), default=TipoIdentificacion.NIT.value)
    identificacion: Mapped[str] = mapped_column(String(40), unique=True)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoOrganizacion.ACTIVA.value, index=True)
    motivo_estado: Mapped[str | None] = mapped_column(Text)
    zona_horaria: Mapped[str] = mapped_column(String(60), default="America/Bogota")
    idioma: Mapped[str] = mapped_column(String(10), default="es-CO")
    # Límites del plan: {"usuarios": 25, "proyectos": 10}. Una clave ausente = sin límite definido.
    limites: Mapped[dict] = mapped_column(Json, default=dict)

    @property
    def activa(self) -> bool:
        return self.estado == EstadoOrganizacion.ACTIVA.value


class Usuario(IdMixin, CamposControlMixin, Base):
    """Identidad única de una persona. Puede pertenecer a varias organizaciones mediante membresías."""

    __tablename__ = "usuarios"

    correo: Mapped[str] = mapped_column(String(254), unique=True)
    nombre_completo: Mapped[str] = mapped_column(String(200))
    clave_hash: Mapped[str] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    bloqueado: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_bloqueo: Mapped[str | None] = mapped_column(Text)
    # Operador de la plataforma SaaS: administra organizaciones, NO ve su contenido (regla ARC-01).
    es_operador: Mapped[bool] = mapped_column(Boolean, default=False)
    debe_cambiar_clave: Mapped[bool] = mapped_column(Boolean, default=True)
    # Subir la versión invalida todos los tokens emitidos (cerrar sesiones, bloquear, cambiar clave).
    version_sesion: Mapped[int] = mapped_column(Integer, default=0)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_ingreso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Verificación en dos pasos. El secreto debe cifrarse en reposo cuando se apruebe el gestor de llaves (D-11).
    mfa_secreto: Mapped[str | None] = mapped_column(String(64))
    mfa_activo: Mapped[bool] = mapped_column(Boolean, default=False)

    membresias: Mapped[list["Membresia"]] = relationship(back_populates="usuario", foreign_keys="Membresia.usuario_id")


class Rol(IdMixin, TenantMixin, CamposControlMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "nombre"),)

    nombre: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    permisos: Mapped[list] = mapped_column(Json, default=list)
    # Los roles base se siembran al crear la organización y no se editan (se crea un rol propio).
    es_base: Mapped[bool] = mapped_column(Boolean, default=False)


class Membresia(IdMixin, TenantMixin, CamposControlMixin, Base):
    """Pertenencia de un usuario a una organización, con su rol y su alcance."""

    __tablename__ = "membresias"
    __table_args__ = (UniqueConstraint("tenant_id", "usuario_id"),)

    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True)
    rol_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    motivo_estado: Mapped[str | None] = mapped_column(Text)
    # Alcance: lista de ids de proyecto a los que se limita. None = todos los de la organización.
    proyectos: Mapped[list | None] = mapped_column(Json)

    usuario: Mapped[Usuario] = relationship(back_populates="membresias", foreign_keys=[usuario_id])
    rol: Mapped[Rol] = relationship()
    organizacion: Mapped[Organizacion] = relationship()
