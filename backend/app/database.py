from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 10}  # 10s lock timeout
    engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
else:
    # PostgreSQL — add connect_timeout so bad connections fail fast (5s) instead of hanging
    connect_args = {"connect_timeout": 5}
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,       # test connections before using them
        pool_timeout=10,          # give up waiting for a pool connection after 10s
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    import logging
    logger = logging.getLogger(__name__)
    from app.models import User, Subscription  # noqa
    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
        logger.info("Database tables ready.")
    except Exception as e:
        logger.warning("create_tables warning (safe to ignore if tables already exist): %s", e)
    _add_column_if_missing("users", "has_permanent_access", "BOOLEAN NOT NULL DEFAULT FALSE")


def _add_column_if_missing(table: str, column: str, ddl_type: str) -> None:
    """create_all() only creates tables that don't exist yet -- it never
    alters an existing table to add a new column, which matters here since
    `users` already has real rows in production. Checked via SQLAlchemy's
    inspector (works the same on SQLite and Postgres) rather than a raw
    dialect-specific "ADD COLUMN IF NOT EXISTS", which SQLite doesn't
    support the same way Postgres does."""
    import logging
    from sqlalchemy import inspect, text
    logger = logging.getLogger(__name__)
    try:
        existing = {c["name"] for c in inspect(engine).get_columns(table)}
        if column in existing:
            return
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
        logger.info(f"Added missing column {table}.{column}.")
    except Exception as e:
        logger.warning(f"_add_column_if_missing({table}.{column}) warning: {e}")
