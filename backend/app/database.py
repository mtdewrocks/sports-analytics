from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
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
