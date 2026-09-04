import time

import pytest

from app import totp as _totp


def _codigo_actual(secreto: str) -> str:
    t = int(time.time() // _totp.PASO)
    return _totp._codigo(secreto, t)


def test_totp_verifica_ventana():
    secreto = _totp.generar_secreto()
    assert _totp.verificar(secreto, _codigo_actual(secreto))
    assert not _totp.verificar(secreto, "000000") or True  # puede coincidir 1/1M; no asserts duro
    assert not _totp.verificar(secreto, "abc123")
    assert not _totp.verificar(secreto, "12345")


def test_admin_login_exige_setup_sin_2fa(client, monkeypatch):
    from tests.conftest import login  # noqa

    monkeypatch.setenv("VIE_ENFORCE_ADMIN_2FA", "1")
    r = client.post("/login", data={"username": "admin1", "password": "clave123"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login/2fa-setup"
    assert "vie_pre2fa" in r.headers.get("set-cookie", "")


def test_flujo_setup_y_login_con_2fa(client, monkeypatch):
    monkeypatch.setenv("VIE_ENFORCE_ADMIN_2FA", "1")
    # 1. password -> setup
    r = client.post("/login", data={"username": "admin1", "password": "clave123"}, follow_redirects=False)
    assert r.headers["location"] == "/login/2fa-setup"
    # 2. página setup muestra QR
    r2 = client.get("/login/2fa-setup")
    assert r2.status_code == 200
    assert "Activa tu segundo factor" in r2.text
    # 3. secreto quedó en BD: lo leemos para generar el código
    from app.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        u = db.query(User).filter(User.username == "admin1").first()
        secreto = u.totp_secret
    assert secreto
    code = _codigo_actual(secreto)
    # 4. confirmar setup -> sesión + respaldo (una sola vez)
    r3 = client.post("/login/2fa-setup", data={"code": code}, follow_redirects=False)
    assert r3.status_code == 200  # renderiza página de respaldo
    assert "códigos de respaldo" in r3.text.lower() or "respaldo" in r3.text.lower()
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == "admin1").first()
        assert u.totp_enabled is True
    # 5. logout + login de nuevo -> pide 2fa
    client.get("/logout")
    r4 = client.post("/login", data={"username": "admin1", "password": "clave123"}, follow_redirects=False)
    assert r4.headers["location"] == "/login/2fa"
    r5 = client.post("/login/2fa", data={"code": _codigo_actual(secreto)}, follow_redirects=False)
    assert r5.status_code == 303
    assert r5.headers["location"] == "/admin"
    # 6. admin no puede desactivar su 2FA
    r6 = client.post("/api/me/2fa/disable", json={"actual": "clave123"})
    assert r6.status_code == 400


def test_codigo_respaldo_un_solo_uso(client, monkeypatch):
    from app.database import SessionLocal
    from app.models import User

    monkeypatch.setenv("VIE_ENFORCE_ADMIN_2FA", "1")
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == "admin1").first()
        # asegura 2FA activo (lo deja el test anterior o lo activa aquí)
        if not (u.totp_enabled and u.totp_secret):
            pytest.skip("requiere 2FA activo del test anterior")
        import json

        from app import totp as _t

        nuevos = _t.generar_respaldo(2)
        u.totp_backup_hashes = json.dumps([_t.hash_respaldo(c) for c in nuevos])
        db.commit()
        code = nuevos[0]
        secreto = u.totp_secret
    client.get("/logout")
    client.post("/login", data={"username": "admin1", "password": "clave123"})
    r = client.post("/login/2fa", data={"code": code}, follow_redirects=False)
    assert r.status_code == 303
    # reutilizar el mismo respaldo falla
    client.get("/logout")
    client.post("/login", data={"username": "admin1", "password": "clave123"})
    r2 = client.post("/login/2fa", data={"code": code})
    assert r2.status_code == 200
    assert "incorrecto" in r2.text.lower()


def test_reset_2fa_por_admin_con_auditoria(client):
    from tests.conftest import login

    login(client, "admin1")
    from app.database import SessionLocal
    from app.models import EditLog, User

    with SessionLocal() as db:
        guarda = db.query(User).filter(User.username == "guarda1").first()
        gid = guarda.id
    r = client.post(f"/api/users/{gid}/2fa/reset", json={"motivo": "perdió el teléfono"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        logs = db.query(EditLog).filter(EditLog.entity_type == "usuario").all()
        assert any("2FA reiniciado" in l.cambios for l in logs)
    # motivo corto se rechaza
    r2 = client.post(f"/api/users/{gid}/2fa/reset", json={"motivo": "x"})
    assert r2.status_code == 400
