def test_health_y_request_id(client):
    r = client.get("/health")
    assert r.status_code == 200
    datos = r.json()
    assert datos["ok"] is True and datos["db"] == "up" and "version" in datos
    assert "x-request-id" in {k.lower(): v for k, v in r.headers.items()}
    # CSP presente
    assert "content-security-policy" in {k.lower(): v for k, v in r.headers.items()}
