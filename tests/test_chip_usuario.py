"""El chip del usuario en el header enlaza al inicio de su rol, para todos."""
from conftest import login


def test_chip_del_usuario_enlaza_al_inicio_por_rol(client):
    esperados = {"residente1": "/residente", "guarda1": "/guarda/paquetes", "admin1": "/admin"}
    for usuario, destino in esperados.items():
        login(client, usuario)
        page = client.get(destino).text
        assert f'<a class="chip role-' in page
        assert f'href="{destino}" title="Ir al inicio"' in page
        assert "Ir al inicio" in page
        # ya no es un span muerto
        assert '<span class="chip role-' not in page


def test_acerca_publica_sin_chip_de_usuario(client):
    page = client.get("/acerca")
    assert page.status_code == 200
    assert 'class="chip role-' not in page.text  # sin sesión no hay chip
