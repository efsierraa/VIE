from app.security import sign_visit, verify_token


def test_token_valido():
    token = sign_visit("abc-123")
    assert verify_token(token) == "abc-123"


def test_token_alterado():
    token = sign_visit("abc-123")
    ultimo = token[-1]
    alterado = token[:-1] + ("A" if ultimo != "A" else "B")
    assert verify_token(alterado) is None


def test_token_basura():
    assert verify_token("garbage") is None
    assert verify_token("") is None
