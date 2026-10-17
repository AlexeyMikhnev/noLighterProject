import os
import sys
import tempfile
from pathlib import Path

# Настройки должны быть заданы ДО импорта приложения.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "admin12345"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:  # startup заново создаёт таблицы и организатора
        yield c


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin(client):
    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin12345"})
    assert r.status_code == 200
    return auth(r.json()["access_token"])


@pytest.fixture()
def make_user(client, admin):
    """Фабрика участников: создаёт инвайт и регистрирует по нему."""

    def _make(nick: str) -> dict:
        token = client.post("/api/admin/invites", json={"count": 1}, headers=admin).json()[0]["token"]
        r = client.post(
            "/api/auth/register",
            json={
                "invite_token": token,
                "email": f"{nick}@example.com",
                "nickname": nick,
                "password": "password123",
            },
        )
        assert r.status_code == 200, r.text
        return auth(r.json()["access_token"])

    return _make
