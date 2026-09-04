import os

os.environ["VIE_DATABASE_URL"] = "sqlite:///./test_vie.db"
os.environ["VIE_SECRET"] = "test-secret-vie"
os.environ["VIE_RATE_LIMIT"] = "0"  # los tests hacen muchos intentos seguidos
os.environ["VIE_ENFORCE_ADMIN_2FA"] = "0"  # los tests generales entran sin 2FA; test_2fa.py lo activa

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import User

DB_FILE = "test_vie.db"


@pytest.fixture(scope="session", autouse=True)
def database():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add_all(
        [
            User(username="admin1", password_hash=hash_password("clave123"), nombres="Administración", apellidos="General", role="admin"),
            User(username="guarda1", password_hash=hash_password("clave123"), nombres="Guarda", apellidos="de Turno", role="guarda"),
            User(username="residente1", password_hash=hash_password("clave123"), nombres="Residenta", apellidos="Uno", role="residente", tower="1", apartment="101"),
            User(username="residente2", password_hash=hash_password("clave123"), nombres="Residente", apellidos="Dos", role="residente", tower="2", apartment="202"),
        ]
    )
    db.commit()
    db.close()
    yield
    engine.dispose()
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)


@pytest.fixture
def client():
    return TestClient(app)


def login(client: TestClient, username: str, password: str = "clave123"):
    r = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code == 303, f"login de {username} falló con {r.status_code}"
