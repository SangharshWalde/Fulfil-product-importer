import os
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{os.path.join(os.path.dirname(__file__), 'data.db')}"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

# SQLite needs check_same_thread=False for FastAPI
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=True, expire_on_commit=False, bind=engine)

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