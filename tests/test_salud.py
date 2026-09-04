def test_health_y_request_id(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "db": "up"}
    assert "x-request-id" in {k.lower(): v for k, v in r.headers.items()}
    # CSP presente
    assert "content-security-policy" in {k.lower(): v for k, v in r.headers.items()}
