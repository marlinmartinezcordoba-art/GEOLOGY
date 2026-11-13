"""La migración escrita produce exactamente el esquema de los modelos, y se puede deshacer."""

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from alembic import command
from arca.modelos import Base


def test_migracion_coincide_con_los_modelos(tmp_path):
    url = f"sqlite:///{tmp_path / 'migracion.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    motor = create_engine(url)
    with motor.connect() as conexion:
        diferencias = compare_metadata(MigrationContext.configure(conexion, opts={"render_as_batch": True}), Base.metadata)
    assert diferencias == []
    command.downgrade(config, "base")
    assert set(inspect(motor).get_table_names()) <= {"alembic_version"}
    motor.dispose()
