from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers
from starlette.responses import Response

from backend.database import Base
from backend.models import User, VirtualPortfolio
from backend.security import hash_password
from backend import models  # noqa: F401 - register all mapped tables


@pytest.fixture
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'paper-test.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def use_development_simulation_for_service_tests(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("UPSTOX_ANALYTICS_TOKEN", "")
    monkeypatch.setenv("UPSTOX_DATA_DISPLAY_AUTHORIZED", "false")
    monkeypatch.setenv("TWELVEDATA_API_KEY", "")
    monkeypatch.setenv("TWELVEDATA_DISPLAY_LICENSE_AUTHORIZED", "false")


def make_user(db, email="user@example.com", starting_cash=100_000):
    user = User(email=email, password_hash=hash_password("correct-horse-battery-staple"))
    db.add(user)
    db.flush()
    db.add(VirtualPortfolio(user_id=user.id, starting_cash=starting_cash, cash=starting_cash))
    db.commit()
    return user


def fake_request(*, cookies=None, headers=None):
    return SimpleNamespace(
        cookies=cookies or {},
        headers=Headers(headers or {}),
        client=SimpleNamespace(host=f"test-{uuid.uuid4()}"),
        state=SimpleNamespace(),
    )


def fake_response():
    return Response()
