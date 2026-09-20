def test_health_y_request_id(client):
    r = client.get("/health")
    assert r.status_code == 200
    datos = r.json()
    assert datos["ok"] is True and datos["db"] == "up" and "version" in datos
    assert "x-request-id" in {k.lower(): v for k, v in r.headers.items()}
    # CSP presente
    assert "content-security-policy" in {k.lower(): v for k, v in r.headers.items()}


def test_html_sin_cache(client):
    """Las páginas HTML dinámicas no se guardan en caché (sin HTML viejo con conteos pasados)."""
    r = client.get("/login")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
