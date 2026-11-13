"""M24 Productividad: el modelo estrella del reporte de Power BI, dentro de ARCA y por proyecto.

Dimensiones (configuración del proyecto): frentes, actividades, turnos, metas por actividad y turno,
calendario operativo y plan de personal. Hechos (lo que pasa cada día): producción, calidad por muestreo,
novedades y entregas. Las tablas llevan los mismos nombres y llaves del diseño de Power BI
(`Cod_Frente`, `Actividad_Clave`, `Turno`), para que el reporte se conecte sin transformar nada.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from arca.modelos.base import Base, IdMixin, TenantMixin


class _DelProyecto(IdMixin, TenantMixin):
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)


class Frente(_DelProyecto, Base):
    __tablename__ = "prod_frentes"
    __table_args__ = (UniqueConstraint("proyecto_id", "codigo"),)

    codigo: Mapped[str] = mapped_column(String(40))
    nombre: Mapped[str] = mapped_column(String(200))
    sede: Mapped[str] = mapped_column(String(200), default="")
    unidad: Mapped[str] = mapped_column(String(60))
    volumen_total: Mapped[float] = mapped_column(Float, default=0)
    actividad_avance: Mapped[str | None] = mapped_column(String(160))  # clave de la actividad que mide el avance
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date)


class Actividad(_DelProyecto, Base):
    __tablename__ = "prod_actividades"
    __table_args__ = (UniqueConstraint("proyecto_id", "clave"),)

    clave: Mapped[str] = mapped_column(String(160))
    frente: Mapped[str] = mapped_column(String(40), index=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    nombre: Mapped[str] = mapped_column(String(200))
    unidad: Mapped[str] = mapped_column(String(60))
    rol: Mapped[str] = mapped_column(String(200), default="")
    cuenta_avance: Mapped[bool] = mapped_column(Boolean, default=False)
    # Si la produce ARCA misma, se cuenta sola: imagenes_recibidas | imagenes_aprobadas | expedientes_inventariados
    fuente_automatica: Mapped[str | None] = mapped_column(String(40))


class Turno(_DelProyecto, Base):
    __tablename__ = "prod_turnos"
    __table_args__ = (UniqueConstraint("proyecto_id", "codigo"),)

    codigo: Mapped[str] = mapped_column(String(10))
    horario: Mapped[str] = mapped_column(String(40), default="")  # «06:00 – 14:00»
    jornada: Mapped[str] = mapped_column(String(40), default="")


class MetaTurno(_DelProyecto, Base):
    __tablename__ = "prod_metas"
    __table_args__ = (UniqueConstraint("proyecto_id", "actividad", "turno"),)

    actividad: Mapped[str] = mapped_column(String(160))
    turno: Mapped[str] = mapped_column(String(10))
    personas_plan: Mapped[float] = mapped_column(Float, default=0)
    meta_turno: Mapped[float] = mapped_column(Float, default=0)


class DiaCalendario(_DelProyecto, Base):
    __tablename__ = "prod_calendario"
    __table_args__ = (UniqueConstraint("proyecto_id", "fecha"),)

    fecha: Mapped[date] = mapped_column(Date)
    operativo: Mapped[bool] = mapped_column(Boolean, default=True)
    fase: Mapped[str] = mapped_column(String(120), default="")
    fecha_entrega_corte: Mapped[date | None] = mapped_column(Date)
    es_dia_entrega: Mapped[bool] = mapped_column(Boolean, default=False)


class PlanPersonal(_DelProyecto, Base):
    __tablename__ = "prod_personal"

    frente: Mapped[str] = mapped_column(String(60))
    rol: Mapped[str] = mapped_column(String(300))
    turno_a: Mapped[float] = mapped_column(Float, default=0)
    turno_b: Mapped[float] = mapped_column(Float, default=0)
    turno_c: Mapped[float] = mapped_column(Float, default=0)
    nomina_con_relevos: Mapped[float] = mapped_column(Float, default=0)
    meta_persona_turno: Mapped[float] = mapped_column(Float, default=0)
    unidad: Mapped[str | None] = mapped_column(String(60))
    que_hace: Mapped[str] = mapped_column(Text, default="")


class _Registro(_DelProyecto):
    origen: Mapped[str] = mapped_column(String(20), default="formulario")  # formulario | importado
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class RegistroProduccion(_Registro, Base):
    __tablename__ = "prod_registro_produccion"

    fecha: Mapped[date] = mapped_column(Date, index=True)
    turno: Mapped[str] = mapped_column(String(10))
    actividad: Mapped[str] = mapped_column(String(160), index=True)
    lote: Mapped[str] = mapped_column(String(80), default="")
    caja_desde: Mapped[str] = mapped_column(String(40), default="")
    caja_hasta: Mapped[str] = mapped_column(String(40), default="")
    cantidad: Mapped[float] = mapped_column(Float)
    personas_presentes: Mapped[float | None] = mapped_column(Float)
    horas_efectivas: Mapped[float | None] = mapped_column(Float)
    supervisor: Mapped[str] = mapped_column(String(200), default="")
    observaciones: Mapped[str] = mapped_column(Text, default="")


class RegistroCalidad(_Registro, Base):
    __tablename__ = "prod_registro_calidad"

    fecha: Mapped[date] = mapped_column(Date, index=True)
    frente: Mapped[str] = mapped_column(String(40), index=True)
    lote: Mapped[str] = mapped_column(String(80), default="")
    unidad_inspeccion: Mapped[str] = mapped_column(String(60), default="")
    tamano_lote: Mapped[float] = mapped_column(Float, default=0)
    muestra: Mapped[float] = mapped_column(Float, default=0)
    criticos: Mapped[int] = mapped_column(Integer, default=0)
    mayores: Mapped[int] = mapped_column(Integer, default=0)
    menores: Mapped[int] = mapped_column(Integer, default=0)
    limitaciones_original: Mapped[int] = mapped_column(Integer, default=0)
    resultado: Mapped[str] = mapped_column(String(60))
    analista: Mapped[str] = mapped_column(String(200), default="")
    observaciones: Mapped[str] = mapped_column(Text, default="")


class Novedad(_Registro, Base):
    __tablename__ = "prod_registro_novedades"

    fecha: Mapped[date] = mapped_column(Date, index=True)
    turno: Mapped[str] = mapped_column(String(10), default="")
    frente: Mapped[str] = mapped_column(String(40), index=True)
    lote: Mapped[str] = mapped_column(String(80), default="")
    caja: Mapped[str] = mapped_column(String(40), default="")
    tipo: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    accion_tomada: Mapped[str] = mapped_column(Text, default="")
    responsable: Mapped[str] = mapped_column(String(200), default="")
    estado: Mapped[str] = mapped_column(String(20), default="Abierta")
    fecha_cierre: Mapped[date | None] = mapped_column(Date)


class Entrega(_Registro, Base):
    __tablename__ = "prod_registro_entregas"

    fecha_entrega: Mapped[date] = mapped_column(Date, index=True)
    frente: Mapped[str] = mapped_column(String(40), index=True)
    lote: Mapped[str] = mapped_column(String(80), default="")
    cantidad: Mapped[float] = mapped_column(Float)
    unidad: Mapped[str] = mapped_column(String(60), default="")
    numero_acta: Mapped[str] = mapped_column(String(80), default="")
    estado: Mapped[str] = mapped_column(String(60), default="Entregado")
    fecha_aceptacion: Mapped[date | None] = mapped_column(Date)
    observaciones: Mapped[str] = mapped_column(Text, default="")


class ClaveReporte(_DelProyecto, Base):
    """Llave de solo lectura para que Power BI (u otra herramienta) lea las tablas del proyecto."""

    __tablename__ = "prod_claves_reporte"

    nombre: Mapped[str] = mapped_column(String(120))
    prefijo: Mapped[str] = mapped_column(String(20))
    huella: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256 de la llave; la llave no se guarda
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    ultimo_uso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CajaProyecto(_DelProyecto, Base):
    """Una caja entregada al proyecto: la base contra la que se mide qué está procesado y qué falta.

    Se carga desde un listado (Excel o CSV) o se arma desde el FUID integrado. Las carpetas son las
    que la caja trae según el listado o el inventario; el avance sale de los rangos «Caja desde» y
    «Caja hasta» de los registros de producción.
    """

    __tablename__ = "prod_cajas"
    __table_args__ = (UniqueConstraint("proyecto_id", "clave"),)

    codigo: Mapped[str] = mapped_column(String(60))
    clave: Mapped[str] = mapped_column(String(60), index=True)  # código normalizado, para comparar rangos
    frente: Mapped[str | None] = mapped_column(String(40), index=True)
    lote: Mapped[str] = mapped_column(String(80), default="")
    sede: Mapped[str] = mapped_column(String(200), default="")
    ubicacion: Mapped[str] = mapped_column(String(200), default="")
    carpetas: Mapped[int | None] = mapped_column(Integer)
    origen: Mapped[str] = mapped_column(String(20), default="listado")  # listado | fuid
    notas: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
