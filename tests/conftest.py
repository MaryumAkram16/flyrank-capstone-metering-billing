import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import app


@pytest.fixture()
def session():
    # StaticPool keeps ONE connection alive for the engine's lifetime, shared
    # across threads. Without it, FastAPI's threadpool (used for sync route
    # handlers) gets a DIFFERENT connection than this fixture set up — and
    # since "sqlite://" with no file means a fresh anonymous in-memory DB per
    # connection, the endpoint would see an empty database with no tables.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def client(session):
    """A TestClient wired to the same in-memory session as the `session` fixture,
    so API-level tests can set up data with `session` and assert on it too."""

    def _get_session_override():
        yield session

    app.dependency_overrides[get_session] = _get_session_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
