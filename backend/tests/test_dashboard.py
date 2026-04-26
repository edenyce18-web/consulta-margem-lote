"""
test_dashboard.py — Testes de integração para os endpoints de Dashboard e Catálogo.
"""
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _registrar_e_logar(client, email="dash@test.com", senha="Senha@123"):
    client.post("/auth/registrar", json={"nome": "Dash", "email": email, "senha": senha})
    resp = client.post("/auth/login", json={"email": email, "senha": senha})
    return resp.json()["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── /dashboard/ ───────────────────────────────────────────────────────────────

def test_dashboard_requer_autenticacao(client):
    resp = client.get("/dashboard/")
    assert resp.status_code == 401


def test_dashboard_usuario_sem_lotes(client):
    token = _registrar_e_logar(client)
    resp = client.get("/dashboard/", headers=_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_lotes"] == 0
    assert body["total_cpfs"] == 0
    assert body["total_sucessos"] == 0
    assert body["total_erros"] == 0
    assert body["taxa_sucesso_pct"] == 0.0
    assert body["lotes_recentes"] == []
    assert body["consultas_por_dia"] == []
    assert body["margens_por_banco"] == []


def test_dashboard_campos_obrigatorios(client):
    token = _registrar_e_logar(client)
    resp = client.get("/dashboard/", headers=_headers(token))
    body = resp.json()
    for campo in ("total_lotes", "total_cpfs", "total_sucessos", "total_erros",
                  "taxa_sucesso_pct", "lotes_recentes", "consultas_por_dia", "margens_por_banco"):
        assert campo in body, f"Campo '{campo}' ausente na resposta do dashboard"


# ── /catalogo/bancos ──────────────────────────────────────────────────────────

def test_catalogo_bancos_publico(client):
    """Catálogo não requer autenticação."""
    resp = client.get("/catalogo/bancos")
    assert resp.status_code == 200
    bancos = resp.json()
    assert isinstance(bancos, list)
    assert len(bancos) >= 1


def test_catalogo_bancos_estrutura(client):
    resp = client.get("/catalogo/bancos")
    for banco in resp.json():
        for campo in ("id", "nome", "descricao", "status", "margem_maxima", "taxa_media"):
            assert campo in banco, f"Campo '{campo}' ausente no banco '{banco.get('id')}'"


def test_catalogo_bancos_contem_aki(client):
    resp = client.get("/catalogo/bancos")
    ids = [b["id"] for b in resp.json()]
    assert "aki" in ids
