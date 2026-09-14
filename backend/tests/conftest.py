import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    # AlphaVantageClient and VoyageEmbeddingClient throttle real requests to
    # respect each API's rate limit; tests never make real requests, so
    # skip the wait.
    monkeypatch.setattr("app.financials.alpha_vantage_client.time.sleep", lambda seconds: None)
    monkeypatch.setattr("app.filings.voyage_client.time.sleep", lambda seconds: None)


@pytest.fixture()
def db_session():
    # StaticPool shares one connection across threads, so the worker thread
    # TestClient runs sync path operations on sees the same in-memory
    # database the fixture just created tables on.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
