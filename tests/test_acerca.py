"""Página Acerca de: pública, con eslogan y enlace al repositorio."""
from conftest import login


def test_acerca_es_publica_y_completa(client):
    r = client.get("/acerca")
    assert r.status_code == 200
    assert "Hecho con amor en" in r.text
    assert "bandera-co.svg" in r.text  # el emoji de bandera no se ve en Windows: va como imagen
    assert "github.com/efsierraa/VIE" in r.text
    assert "pull requests" in r.text.lower()
    assert "software libre" in r.text
    # sin sesión no hay menú flotante, pero el pie enlaza a Acerca de
    assert 'href="/acerca"' in r.text
    assert 'class="fab"' not in r.text


def test_menu_flotante_por_rol(client):
    login(client, "guarda1")
    page = client.get("/guarda")
    assert 'class="fab"' in page.text
    assert "/guarda/paquetes" in page.text
    assert "/acerca" in page.text

    login(client, "admin1")
    page = client.get("/admin")
    assert 'class="fab"' in page.text
    assert "/admin/cuentas" in page.text
    assert "/admin/historial" in page.text
    assert "/acerca" in page.text
