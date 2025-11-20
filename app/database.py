import os
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

_env_db = os.getenv("DATABASE_URL")
if _env_db:
    DATABASE_URL = _env_db
else:
    _default_sqlite = os.path.join(os.path.dirname(__file__), 'data.db')
    try:
        os.makedirs(os.path.dirname(_default_sqlite), exist_ok=True)
        with open(_default_sqlite, 'a'):
            pass
        DATABASE_URL = f"sqlite:///{_default_sqlite}"
    except Exception:
        DATABASE_URL = "sqlite:////tmp/data.db"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

# SQLite needs check_same_thread=False for FastAPI
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
    pool_size=5 if DATABASE_URL.startswith("postgresql") else None,
    max_overflow=10 if DATABASE_URL.startswith("postgresql") else None,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)

class Base(DeclarativeBase):
    pass

# Dependency

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logging.getLogger("app.database").error(str(e))
        raise
    finally:
        db.close()

# Initialize tables

def init_db():
    from . import models
    Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            conn.exec_driver_sql("PRAGMA synchronous=NORMAL")