"""
Expediente, trámites e inventario de origen.

El expediente guarda su estado y los veintiséis elementos de la norma. Los trámites son
los renglones de la hoja de control F-GDM-007. La unidad de inventario es lo que el
inventario de origen del contrato dice de la carpeta, y es la que manda sobre el periodo
(R6) y la que decide si la carpeta pertenece a la selección inventariada (R3).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.services.estados import Estado


class UnidadInventario(Base):
    """Una fila del inventario de origen recibido del Servicio Geológico."""
    __tablename__ = "unidad_inventario"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_carpeta: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    periodo: Mapped[str] = mapped_column(String(6), default="")     # romano; vacío cuando viene S/F
    folios: Mapped[Optional[int]] = mapped_column(Integer)
    asunto: Mapped[Optional[str]] = mapped_column(Text)
    caja_origen: Mapped[Optional[str]] = mapped_column(String(20))
    caja_trabajo: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    # Clasificación que ya trae el inventario del Servicio Geológico. Sirve para prellenar la
    # hoja de control y ahorrarle al equipo volver a escribir lo que ya está escrito.
    # Anchas a propósito: el inventario recibido trae filas con las columnas corridas y ahí
    # aparecen textos como el nombre de una regional en la casilla del código.
    cod_serie: Mapped[Optional[str]] = mapped_column(String(60))
    serie: Mapped[Optional[str]] = mapped_column(String(200))
    cod_subserie: Mapped[Optional[str]] = mapped_column(String(60))
    subserie: Mapped[Optional[str]] = mapped_column(String(200))
    fecha_inicial: Mapped[Optional[date]] = mapped_column(Date)
    fecha_final: Mapped[Optional[date]] = mapped_column(Date)


class Expediente(Base):
    __tablename__ = "expediente"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_carpeta: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # Estado, que vive en la base de datos y sobrevive a cualquier reinicio (R39)
    estado: Mapped[str] = mapped_column(String(40), default=Estado.EN_COLA.value, index=True)
    responsable: Mapped[Optional[str]] = mapped_column(String(150))

    # Ubicación física, con las tres numeraciones que conviven (R5)
    caja_origen: Mapped[Optional[str]] = mapped_column(String(20))
    caja_trabajo: Mapped[Optional[str]] = mapped_column(String(20))
    caja_definitiva: Mapped[Optional[str]] = mapped_column(String(20))
    consecutivo_en_caja: Mapped[Optional[int]] = mapped_column(Integer)

    # Clasificación (R22 a R26)
    periodo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("periodo.id"))
    subserie_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subserie.id"))
    periodo_fijado_a_mano: Mapped[bool] = mapped_column(Boolean, default=False)   # R9
    # Libro empastado. Nulo significa que nadie se ha pronunciado y manda la detección del
    # inventario de origen; verdadero o falso es la decisión de una persona, y esa manda.
    encuadernada: Mapped[Optional[bool]] = mapped_column(Boolean)
    encuadernacion_por: Mapped[Optional[str]] = mapped_column(String(150))

    # Área 1, identificación
    codigo_referencia: Mapped[Optional[str]] = mapped_column(String(80), index=True)  # 3.1.1
    titulo: Mapped[Optional[str]] = mapped_column(Text)                               # 3.1.2
    # Campo 7 de la hoja de control F-GDM-007. NO es el título ISAD(G) y por eso tiene
    # columna propia. El campo 7 es corto y genérico a propósito —«Estudios de laboratorio»—
    # porque en la hoja identifica el expediente dentro de su carpeta. El 3.1.2, en cambio,
    # tiene que identificar esa unidad y ninguna otra en todo el fondo. Cuando los dos vivían
    # en la misma columna, el campo 7 llegaba primero y el título ISAD(G) nunca se escribía:
    # la descripción salía con «Informes» de título y por ahí la devuelven.
    nombre_expediente: Mapped[Optional[str]] = mapped_column(Text)
    fecha_inicial: Mapped[Optional[date]] = mapped_column(Date)                       # 3.1.3
    fecha_final: Mapped[Optional[date]] = mapped_column(Date)
    fechas_texto: Mapped[Optional[str]] = mapped_column(String(120))
    nivel_descripcion: Mapped[str] = mapped_column(String(30), default="Unidad documental")  # 3.1.4
    volumen_folios: Mapped[Optional[int]] = mapped_column(Integer)                    # 3.1.5
    # Cuando los folios que suma la hoja no son los que declara el inventario de origen, la
    # diferencia queda escrita aquí y sale en la hoja de control y en el inventario de salida.
    # Es un hecho del expediente, no una observación de conservación de un trámite.
    diferencia_folios: Mapped[Optional[str]] = mapped_column(Text)
    metros_lineales: Mapped[Optional[float]] = mapped_column(Float)                   # 3.1.5
    soporte: Mapped[Optional[str]] = mapped_column(String(60))

    # Área 2, contexto
    nombre_productor: Mapped[Optional[str]] = mapped_column(Text)                     # 3.2.1
    historia_institucional: Mapped[Optional[str]] = mapped_column(Text)               # 3.2.2
    historia_archivistica: Mapped[Optional[str]] = mapped_column(Text)                # 3.2.3
    forma_ingreso: Mapped[Optional[str]] = mapped_column(Text)                        # 3.2.4

    # Área 3, contenido y estructura
    alcance_contenido: Mapped[Optional[str]] = mapped_column(Text)                    # 3.3.1
    valoracion: Mapped[Optional[str]] = mapped_column(Text)                           # 3.3.2
    nuevos_ingresos: Mapped[Optional[str]] = mapped_column(Text)                      # 3.3.3
    organizacion: Mapped[Optional[str]] = mapped_column(Text)                         # 3.3.4

    # Área 4, condiciones de acceso y uso
    condiciones_acceso: Mapped[Optional[str]] = mapped_column(Text)                    # 3.4.1
    condiciones_reproduccion: Mapped[Optional[str]] = mapped_column(Text)              # 3.4.2
    lengua: Mapped[Optional[str]] = mapped_column(String(120))                         # 3.4.3
    caracteristicas_fisicas: Mapped[Optional[str]] = mapped_column(Text)               # 3.4.4
    instrumentos_descripcion: Mapped[Optional[str]] = mapped_column(Text)              # 3.4.5

    # Área 5, documentación asociada
    existencia_originales: Mapped[Optional[str]] = mapped_column(Text)                 # 3.5.1
    existencia_copias: Mapped[Optional[str]] = mapped_column(Text)                     # 3.5.2
    unidades_relacionadas: Mapped[Optional[str]] = mapped_column(Text)                 # 3.5.3
    nota_publicaciones: Mapped[Optional[str]] = mapped_column(Text)                    # 3.5.4

    # Área 6 y área 7
    notas: Mapped[Optional[str]] = mapped_column(Text)                                 # 3.6.1
    nota_archivero: Mapped[Optional[str]] = mapped_column(Text)                        # 3.7.1
    reglas_normas: Mapped[Optional[str]] = mapped_column(Text)                         # 3.7.2
    fecha_descripcion: Mapped[Optional[date]] = mapped_column(Date)                    # 3.7.3
    describio: Mapped[Optional[str]] = mapped_column(String(150))
    # Qué motor redactó los elementos narrativos. Se guarda por dos razones: porque el AGN
    # puede preguntar con qué se produjo la descripción, y porque el revisor tiene que ser
    # de un proveedor DISTINTO. Un modelo revisando su propia redacción la encuentra
    # excelente; es la misma razón por la que aquí nadie aprueba su propio trabajo.
    redactada_por: Mapped[Optional[str]] = mapped_column(String(120))
    # Qué motor la revisó, si alguno. Sirve para no revisar dos veces lo mismo en el turno
    # de noche y para saber cuánto del fondo ya tuvo una segunda mirada.
    revisada_por_modelo: Mapped[Optional[str]] = mapped_column(String(120))
    aprobo: Mapped[Optional[str]] = mapped_column(String(150))
    fecha_aprobacion: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Hoja de control F-GDM-007
    # Quien diligenció la hoja. Se guarda para la bitácora, pero NO es el campo 15.
    responsable_hoja: Mapped[Optional[str]] = mapped_column(String(150))
    # Campo 15 del F-GDM-007: el responsable es quien REVISA la hoja y da fe de que lo
    # escrito corresponde al expediente. Va en blanco mientras nadie la haya revisado.
    reviso_hoja: Mapped[Optional[str]] = mapped_column(String(150))                     # campo 15
    fecha_revision: Mapped[Optional[date]] = mapped_column(Date)                        # campo 16
    fecha_diligenciamiento: Mapped[Optional[date]] = mapped_column(Date)               # campo 16
    archivo_origen: Mapped[Optional[str]] = mapped_column(String(255))

    # Retiro con papelera (paso nuevo)
    retirado_en: Mapped[Optional[datetime]] = mapped_column(DateTime)
    motivo_retiro: Mapped[Optional[str]] = mapped_column(Text)

    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    tramites: Mapped[list["Tramite"]] = relationship(
        back_populates="expediente", cascade="all, delete-orphan", order_by="Tramite.no_item")
    trazabilidad: Mapped[list["Trazabilidad"]] = relationship(
        back_populates="expediente", cascade="all, delete-orphan", order_by="Trazabilidad.fecha")


class Tramite(Base):
    """Un renglón de la hoja de control."""
    __tablename__ = "tramite"
    id: Mapped[int] = mapped_column(primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey("expediente.id"), index=True)
    no_item: Mapped[int] = mapped_column(Integer)
    fecha: Mapped[Optional[date]] = mapped_column(Date)
    fecha_texto: Mapped[Optional[str]] = mapped_column(String(20))    # conserva la fecha parcial
    # Sin tope de longitud, y a conciencia. El equipo escribe aquí el tipo documental junto
    # con las muestras, el yacimiento y el municipio, que es lo que de verdad identifica el
    # trámite en este fondo. Doscientos caracteres se quedaban cortos por tres, y la carga
    # entera se caía con un error de base de datos en vez de decir qué pasaba.
    tipo_documental: Mapped[Optional[str]] = mapped_column(Text)
    folio_desde: Mapped[Optional[int]] = mapped_column(Integer)
    folio_hasta: Mapped[Optional[int]] = mapped_column(Integer)
    no_radicado: Mapped[Optional[str]] = mapped_column(String(60))
    sistema_informacion: Mapped[Optional[str]] = mapped_column(String(120))
    expediente_sgdea: Mapped[Optional[str]] = mapped_column(String(120))
    enlace_acceso: Mapped[Optional[str]] = mapped_column(Text)
    observaciones: Mapped[Optional[str]] = mapped_column(Text)

    expediente: Mapped["Expediente"] = relationship(back_populates="tramites")

    __table_args__ = (UniqueConstraint("expediente_id", "no_item"),)
