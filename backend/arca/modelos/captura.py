"""Incremento 2: archivos digitales, inventario FUID (M08), unidades documentales y digitalización (M10, M11).

Se distinguen, como exige el Documento Maestro (§7.1), la UNIDAD DOCUMENTAL del inventario (el expediente o
carpeta descrito en el FUID), el ARCHIVO DIGITAL guardado en el repositorio y el RECURSO DIGITAL que asocia
ese archivo a la unidad (un PDF por carpeta o una imagen por página). Folio, página e imagen no se mezclan.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from arca.modelos.base import Base, CamposControlMixin, IdMixin, Json, TenantMixin


class ArchivoDigital(IdMixin, TenantMixin, Base):
    """Un original guardado en el repositorio. Inmutable: nunca se edita ni se borra."""

    __tablename__ = "archivos"

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    nombre_original: Mapped[str] = mapped_column(String(500))
    formato: Mapped[str] = mapped_column(String(20))
    mime: Mapped[str] = mapped_column(String(120))
    tamano: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    clave_almacen: Mapped[str] = mapped_column(String(300), unique=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))


class EstadoLote(StrEnum):
    VALIDADO = "validado"  # todas las filas pasan
    CON_ERRORES = "con_errores"  # hay filas que no pasan
    INTEGRADO = "integrado"  # las filas válidas ya son unidades documentales
    DESCARTADO = "descartado"


class LoteInventario(IdMixin, TenantMixin, CamposControlMixin, Base):
    """Un FUID importado. Se conserva el archivo fuente, el mapeo de columnas y cada fila tal como llegó."""

    __tablename__ = "inventario_lotes"

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    archivo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("archivos.id", ondelete="RESTRICT"))
    nombre_archivo: Mapped[str] = mapped_column(String(500))
    hoja: Mapped[str | None] = mapped_column(String(200))
    fila_encabezado: Mapped[int] = mapped_column(Integer)
    encabezados: Mapped[list] = mapped_column(Json)
    mapeo: Mapped[dict] = mapped_column(Json)  # {campo: índice de columna}
    estado: Mapped[str] = mapped_column(String(20), index=True)
    total_filas: Mapped[int] = mapped_column(Integer, default=0)
    filas_validas: Mapped[int] = mapped_column(Integer, default=0)
    filas_con_error: Mapped[int] = mapped_column(Integer, default=0)
    filas_integradas: Mapped[int] = mapped_column(Integer, default=0)
    motivo_estado: Mapped[str | None] = mapped_column(Text)


class FilaInventario(IdMixin, TenantMixin, Base):
    __tablename__ = "inventario_filas"
    __table_args__ = (UniqueConstraint("lote_id", "numero_fila"),)

    lote_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventario_lotes.id", ondelete="RESTRICT"), index=True)
    numero_fila: Mapped[int] = mapped_column(Integer)  # fila en la hoja de cálculo, como la ve quien la hizo
    original: Mapped[list] = mapped_column(Json)  # las celdas tal como llegaron
    normalizado: Mapped[dict] = mapped_column(Json)
    errores: Mapped[list] = mapped_column(Json, default=list)
    avisos: Mapped[list] = mapped_column(Json, default=list)
    unidad_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"))


class UnidadDocumental(IdMixin, TenantMixin, CamposControlMixin, Base):
    """Expediente, carpeta o tomo descrito en el inventario. Su identificador es el que llevan los archivos digitalizados."""

    __tablename__ = "unidades_documentales"
    __table_args__ = (UniqueConstraint("proyecto_id", "clave"),)

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    lote_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inventario_lotes.id", ondelete="RESTRICT"))
    identificador: Mapped[str] = mapped_column(String(120))
    clave: Mapped[str] = mapped_column(String(120), index=True)  # identificador normalizado, para reconocer archivos
    numero_orden: Mapped[str | None] = mapped_column(String(40))
    codigo_serie: Mapped[str | None] = mapped_column(String(80))
    nombre: Mapped[str] = mapped_column(Text)
    fecha_inicial: Mapped[date | None] = mapped_column(Date)
    fecha_final: Mapped[date | None] = mapped_column(Date)
    caja: Mapped[str | None] = mapped_column(String(60))
    carpeta: Mapped[str | None] = mapped_column(String(60))
    tomo: Mapped[str | None] = mapped_column(String(60))
    otro: Mapped[str | None] = mapped_column(String(60))
    folios: Mapped[int | None] = mapped_column(Integer)
    soporte: Mapped[str] = mapped_column(String(20), default="fisico")
    frecuencia_consulta: Mapped[str | None] = mapped_column(String(60))
    notas: Mapped[str | None] = mapped_column(Text)
    # Ciclo vital: dónde está hoy la unidad. Cambia solo por una transferencia recibida o al registrar la fase de partida.
    fase: Mapped[str] = mapped_column(String(20), default="gestion", server_default="gestion", index=True)  # gestion | central | historico | eliminada
    # Disposición final ya aplicada: eliminada | seleccionada (quedó en la muestra) | digitalizada (medio técnico).
    disposicion_aplicada: Mapped[str | None] = mapped_column(String(20))


class EstadoRecurso(StrEnum):
    APROBADO = "aprobado"  # pasó las reglas o lo aprobó una persona
    EN_REVISION = "en_revision"  # tiene alertas: decide una persona
    RECHAZADO = "rechazado"  # incumple una regla de rechazo automático
    RECAPTURA = "recaptura"  # una persona pidió volver a digitalizar
    REEMPLAZADO = "reemplazado"  # llegó la recaptura; se conserva como evidencia
    SIN_IDENTIFICAR = "sin_identificar"  # no se pudo asociar a ninguna unidad del inventario


class RecursoDigital(IdMixin, TenantMixin, Base):
    """Un archivo digitalizado asociado (o por asociar) a una unidad documental, con su control de calidad."""

    __tablename__ = "recursos_digitales"

    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True)
    unidad_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("unidades_documentales.id", ondelete="RESTRICT"), index=True)
    archivo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("archivos.id", ondelete="RESTRICT"))
    ruta_original: Mapped[str] = mapped_column(String(1000))  # ruta dentro de la carpeta cargada
    modalidad: Mapped[str] = mapped_column(String(20))  # pdf | imagen
    parte: Mapped[int] = mapped_column(Integer, default=0)  # PDF por partes: 0 = completo
    pagina: Mapped[int | None] = mapped_column(Integer)  # imagen por página: su número en la secuencia
    paginas: Mapped[int] = mapped_column(Integer, default=0)
    ficha: Mapped[dict] = mapped_column(Json, default=dict)  # ficha técnica medida sin tocar el archivo
    hallazgos: Mapped[list] = mapped_column(Json, default=list)
    estado: Mapped[str] = mapped_column(String(20), index=True)
    perfil_version: Mapped[int | None] = mapped_column(Integer)  # versión del perfil de digitalización aplicado
    reemplaza_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recursos_digitales.id", ondelete="RESTRICT"))
    decidido_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    motivo_decision: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))

    archivo: Mapped[ArchivoDigital] = relationship()
    unidad: Mapped[UnidadDocumental | None] = relationship()
