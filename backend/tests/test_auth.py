"""
test_auth.py — Testes de autenticação: registro, login, refresh token, rate limiting.
"""
import pytest
from fastapi.testclient import TestClient


USUARIO = {"nome": "Teste", "email": "teste@teste.com", "senha": "Teste1234"}


def _registrar(client):
    return client.post("/auth/registrar", json=USUARIO)


def _login(client):
    return client.post("/auth/login", json={"email": USUARIO["email"], "senha": USUARIO["senha"]})


class TestRegistro:
    def test_registrar_usuario_novo(self, client):
        r = _registrar(client)
        assert r.status_code == 200
        assert r.json()["email"] == USUARIO["email"]

    def test_email_duplicado_retorna_400(self, client):
        _registrar(client)
        r = _registrar(client)
        assert r.status_code == 400
        assert "cadastrado" in r.json()["detail"].lower()

    def test_email_invalido_retorna_422(self, client):
        r = client.post("/auth/registrar", json={"nome": "X", "email": "nao-e-email", "senha": "abc"})
        assert r.status_code == 422


class TestLogin:
    def test_login_correto_retorna_tokens(self, client):
        _registrar(client)
        r = _login(client)
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_senha_errada_retorna_401(self, client):
        _registrar(client)
        r = client.post("/auth/login", json={"email": USUARIO["email"], "senha": "errada"})
        assert r.status_code == 401

    def test_email_inexistente_retorna_401(self, client):
        r = client.post("/auth/login", json={"email": "nao@existe.com", "senha": "qualquer"})
        assert r.status_code == 401


class TestRefreshToken:
    def test_refresh_gera_novo_access_token(self, client):
        _registrar(client)
        login_r = _login(client)
        refresh_token = login_r.json()["refresh_token"]

        r = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_refresh_invalido_retorna_401(self, client):
        r = client.post("/auth/refresh", json={"refresh_token": "token_invalido"})
        assert r.status_code == 401


class TestRateLimiting:
    def test_excesso_tentativas_retorna_429(self, client):
        _registrar(client)
        # Faz tentativas com senha errada até exceder o limite (5)
        for _ in range(5):
            client.post("/auth/login", json={"email": USUARIO["email"], "senha": "errada"})
        # A próxima deve ser bloqueada
        r = client.post("/auth/login", json={"email": USUARIO["email"], "senha": "errada"})
        assert r.status_code == 429


class TestEndpointsProtegidos:
    def test_dashboard_sem_token_retorna_401(self, client):
        r = client.get("/dashboard/")
        assert r.status_code == 401

    def test_credenciais_sem_token_retorna_401(self, client):
        r = client.get("/credenciais/")
        assert r.status_code == 401

    def test_dashboard_com_token_retorna_200(self, client):
        _registrar(client)
        token = _login(client).json()["access_token"]
        r = client.get("/dashboard/", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
