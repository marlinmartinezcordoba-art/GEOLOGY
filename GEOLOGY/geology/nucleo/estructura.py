"""
Ajustes de estructura que la creación automática de tablas no puede hacer sola.

create_all crea lo que falta, pero nunca modifica una tabla que ya existe. Cuando una
columna se queda corta o hace falta una nueva, sin esto habría que borrar la base y volver a
cargarlo todo, que es justo lo que no se puede pedir con producción en marcha.

Cada ajuste es idempotente: se puede correr todos los días sin que pase nada. Se ejecutan al
arrancar la aplicación y ninguno borra datos.
"""
from __future__ import annotations

from sqlalchemy import text

from geology.nucleo.bd import motor

# (descripción, sentencia). Solo ampliaciones y adiciones; nada que quite información.
AJUSTES: list[tuple[str, str]] = [
    ("La columna de consumo guarda ahora proveedor/modelo y necesita más espacio",
     "ALTER TABLE consumo_lector ALTER COLUMN proveedor TYPE VARCHAR(120)"),
    ("El expediente guarda su extensión en metros lineales (elemento 3.1.5)",
     "ALTER TABLE unidad_documental ADD COLUMN IF NOT EXISTS metros_lineales DOUBLE PRECISION"),
    ("El campo 7 de la hoja de control tiene columna propia y deja de pisar el título ISAD(G)",
     "ALTER TABLE unidad_documental ADD COLUMN IF NOT EXISTS nombre_expediente TEXT"),
    ("Queda registrado qué motor redactó la descripción, para que la revise otro distinto",
     "ALTER TABLE unidad_documental ADD COLUMN IF NOT EXISTS redactada_por VARCHAR(120)"),
    ("Y cuál la revisó, para no revisar dos veces lo mismo",
     "ALTER TABLE unidad_documental ADD COLUMN IF NOT EXISTS revisada_por_modelo VARCHAR(120)"),
    ("El tipo documental se queda sin tope: el equipo escribe ahí muestras, yacimiento y "
     "municipio, y doscientos caracteres se quedaban cortos",
     "ALTER TABLE asiento_hoja ALTER COLUMN tipo_documental TYPE TEXT"),
    ("El expediente registra si es un libro empastado",
     "ALTER TABLE unidad_documental ADD COLUMN IF NOT EXISTS encuadernada BOOLEAN"),
    ("Queda registrado quién decidió si es libro",
     "ALTER TABLE unidad_documental ADD COLUMN IF NOT EXISTS encuadernacion_por VARCHAR(150)"),
    ("El campo 15 de la hoja de control es quien la revisa, no quien la diligencia",
     "ALTER TABLE unidad_documental "
     "ADD COLUMN IF NOT EXISTS reviso_hoja VARCHAR(150), "
     "ADD COLUMN IF NOT EXISTS fecha_revision DATE"),
    ("El archivo guarda su ficha técnica de digitalización",
     "ALTER TABLE archivo_digital "
     "ADD COLUMN IF NOT EXISTS paginas INTEGER, "
     "ADD COLUMN IF NOT EXISTS dpi_minimo INTEGER, "
     "ADD COLUMN IF NOT EXISTS dpi_medio INTEGER, "
     "ADD COLUMN IF NOT EXISTS bits_por_color INTEGER, "
     "ADD COLUMN IF NOT EXISTS tiene_capa_de_texto BOOLEAN, "
     "ADD COLUMN IF NOT EXISTS avisos_tecnicos TEXT"),
    ("El expediente guarda la diferencia de folios contra el inventario de origen",
     "ALTER TABLE unidad_documental ADD COLUMN IF NOT EXISTS diferencia_folios TEXT"),
    ("El archivo guarda su matriz de preservación y su copia de consulta",
     "ALTER TABLE archivo_digital "
     "ADD COLUMN IF NOT EXISTS ruta_matriz VARCHAR(500), "
     "ADD COLUMN IF NOT EXISTS ruta_consulta VARCHAR(500), "
     "ADD COLUMN IF NOT EXISTS ruta_texto VARCHAR(500), "
     "ADD COLUMN IF NOT EXISTS procesado_en TIMESTAMP, "
     "ADD COLUMN IF NOT EXISTS error_proceso TEXT"),
    ("La cuenta guarda qué tiene habilitado el perfil de consulta de la entidad",
     "ALTER TABLE cuenta "
     "ADD COLUMN IF NOT EXISTS ve_hojas_control BOOLEAN NOT NULL DEFAULT TRUE, "
     "ADD COLUMN IF NOT EXISTS ve_isadg BOOLEAN NOT NULL DEFAULT TRUE, "
     "ADD COLUMN IF NOT EXISTS ve_fuid BOOLEAN NOT NULL DEFAULT TRUE, "
     "ADD COLUMN IF NOT EXISTS ve_imagenes BOOLEAN NOT NULL DEFAULT FALSE"),
    ("El archivo digital registra el rango de páginas de cada parte cuando el sistema dividió "
     "un documento de gran volumen",
     "ALTER TABLE archivo_digital "
     "ADD COLUMN IF NOT EXISTS pagina_inicial INTEGER, "
     "ADD COLUMN IF NOT EXISTS pagina_final INTEGER, "
     "ADD COLUMN IF NOT EXISTS dividido_por_sistema BOOLEAN, "
     "ADD COLUMN IF NOT EXISTS sha256_origen VARCHAR(64)"),
]


def aplicar() -> list[str]:
    """Aplica los ajustes pendientes y devuelve lo que hizo, para dejarlo en el arranque."""
    hechos: list[str] = []
    with motor.begin() as conexion:
        for descripcion, sentencia in AJUSTES:
            try:
                conexion.execute(text(sentencia))
                hechos.append(descripcion)
            except Exception as e:
                # Si la tabla todavía no existe o el ajuste ya estaba puesto, no es un error.
                hechos.append(f"(sin efecto) {descripcion}: {type(e).__name__}")
    return hechos
