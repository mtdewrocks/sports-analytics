from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
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
