from app.security import sign_visit, verify_token


def test_token_valido():
    token = sign_visit("abc-123")
    assert verify_token(token) == "abc-123"


def test_token_alterado():
    token = sign_visit("abc-123")
    # alterar un carácter del medio: el último puede decodificar igual en base64
    alterado = token[:2] + ("X" if token[2] != "X" else "Y") + token[3:]
    assert verify_token(alterado) is None
    assert verify_token("garbage") is None


def test_token_basura():
    assert verify_token("garbage") is None
    assert verify_token("") is None
