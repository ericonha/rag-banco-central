import os

from alembic import context
from sqlalchemy import create_engine, pool


def get_url() -> str:
    # The app uses a plain postgresql:// URL; SQLAlchemy needs the psycopg (v3) driver name.
    return os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)


def run_migrations_online() -> None:
    engine = create_engine(get_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported")
run_migrations_online()
