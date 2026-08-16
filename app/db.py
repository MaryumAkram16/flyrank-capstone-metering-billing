import os
from contextlib import contextmanager

from sqlmodel import SQLModel, Session, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./billing.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Create all tables. Safe to call repeatedly — no-op if tables exist."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency — yields a session per request."""
    with Session(engine) as session:
        yield session


@contextmanager
def get_session_direct():
    """Session for scripts (e.g. seed.py) outside a FastAPI request."""
    with Session(engine) as session:
        yield session
