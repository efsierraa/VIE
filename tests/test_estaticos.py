"""Estáticos a prueba de cachés: URLs versionadas por contenido (?v=hash) y
Cache-Control explícito, para que ningún navegador (ni celular) quede con JS viejo."""
from conftest import login


def test_estaticos_con_cache_control(client):
    r = client.get("/static/js/piscina.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=86400"


def test_paginas_con_urls_versionadas(client):
    """Las plantillas referencian JS/CSS con ?v=<hash>: cambia el archivo, cambia la URL."""
    page = client.get("/login").text
    assert "style.css?v=" in page
    assert "app.js?v=" in page
    assert 'href="/static/style.css"' not in page

    login(client, "admin1")
    page = client.get("/admin/cuentas").text
    assert "admin.js?v=" in page
