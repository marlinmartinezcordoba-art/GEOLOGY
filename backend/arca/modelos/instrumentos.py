"""M04 Instrumentos archivísticos del proyecto (TRD, TVD, CCD) con versiones, aprobación y vigencia.

El instrumento es de la entidad cliente, por eso vive en el proyecto. Cada versión conserva el archivo fuente,
sus elementos (dependencias, series y subseries con tipos documentales, retención y disposición) y los hallazgos
de la validación. Una versión nace en borrador; la aprueba alguien distinto de quien la importó, con el acto
administrativo; desde su vigencia reemplaza a la anterior, que queda como evidencia. No se edita: se versiona.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, Json, TenantMixin


class Instrumento(IdMixin, TenantMixin, Base):
    __tablename__ = "instrumentos"
    __table_args__ = (UniqueConstraint("proyecto_id", "tipo", "nombre"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    tipo: Mapped[str] = mapped_column(String(10))  # TRD | TVD | CCD
    nombre: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    # Para una TVD de fondo acumulado: el periodo institucional que valora.
    periodo_desde: Mapped[date | None] = mapped_column(Date)
    periodo_hasta: Mapped[date | None] = mapped_column(Date)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class VersionInstrumento(IdMixin, TenantMixin, Base):
    __tablename__ = "instrumento_versiones"
    __table_args__ = (UniqueConstraint("instrumento_id", "version"),)

    instrumento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instrumentos.id", ondelete="RESTRICT"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(20), index=True)  # borrador | programada | vigente | reemplazada | descartada
    archivo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("archivos.id", ondelete="RESTRICT"))
    totales: Mapped[dict] = mapped_column(Json, default=dict)
    errores: Mapped[list] = mapped_column(Json, default=list)
    avisos: Mapped[list] = mapped_column(Json, default=list)
    correcciones: Mapped[list] = mapped_column(Json, default=list)
    motivo: Mapped[str] = mapped_column(Text, default="")
    acto_administrativo: Mapped[str | None] = mapped_column(String(200))
    fecha_acto: Mapped[date | None] = mapped_column(Date)
    convalidacion: Mapped[str | None] = mapped_column(Text)
    vigente_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    aprobado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprobado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class ElementoInstrumento(IdMixin, TenantMixin, Base):
    """Una dependencia, serie o subserie de una versión, con lo que dice el instrumento sobre ella."""

    __tablename__ = "instrumento_elementos"
    __table_args__ = (UniqueConstraint("version_id", "nivel", "codigo"),)

    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instrumento_versiones.id", ondelete="RESTRICT"), index=True)
    nivel: Mapped[str] = mapped_column(String(20))  # dependencia | serie | subserie
    codigo: Mapped[str] = mapped_column(String(60), index=True)
    nombre: Mapped[str] = mapped_column(String(300))
    codigo_dependencia: Mapped[str] = mapped_column(String(40), default="")
    padre: Mapped[str | None] = mapped_column(String(60))
    tipos_documentales: Mapped[list] = mapped_column(Json, default=list)
    retencion_gestion: Mapped[int | None] = mapped_column(Integer)
    retencion_central: Mapped[int | None] = mapped_column(Integer)
    disposicion: Mapped[str | None] = mapped_column(String(4))  # CT | E | S | D
    soporte: Mapped[str | None] = mapped_column(String(20))
    procedimiento: Mapped[str] = mapped_column(Text, default="")
    acceso: Mapped[str] = mapped_column(String(20), default="publica")
    hoja: Mapped[str] = mapped_column(String(100), default="")
    fila: Mapped[int | None] = mapped_column(Integer)


class ClasificacionUnidad(IdMixin, TenantMixin, Base):
    """La serie o subserie que se le asignó a una unidad documental, con la versión del instrumento que se usó.

    No se edita. Reclasificar crea otra fila y la anterior queda «reemplazada». Así lo ya clasificado conserva
    el instrumento con que se hizo aunque después la TRD cambie.
    """

    __tablename__ = "clasificaciones"

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instrumento_versiones.id", ondelete="RESTRICT"), index=True)
    elemento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instrumento_elementos.id", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(20), index=True)  # propuesta | confirmada | rechazada | reemplazada
    origen: Mapped[str] = mapped_column(String(20))  # inventario | codigo | motor | manual | actualizacion
    confianza: Mapped[str | None] = mapped_column(String(10))  # alta | media | baja
    porque: Mapped[str] = mapped_column(Text, default="")
    motivo: Mapped[str] = mapped_column(Text, default="")
    reemplaza_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clasificaciones.id", ondelete="RESTRICT"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    decidido_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decidido_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
