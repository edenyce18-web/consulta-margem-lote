"""
scraper/__init__.py
────────────────────
Ponto de entrada do pacote de scrapers.

Importar este pacote garante que todos os adaptadores se auto-registrem
no AdapterManager. Basta adicionar novos adaptadores aqui para que
estejam disponíveis em toda a aplicação.

Uso:
    from app.scraper import consultar_margem, listar_adaptadores
    from app.scraper.manager import AdapterManager
"""

# Importa o manager primeiro (sem dependência circular)
from app.scraper.manager import AdapterManager  # noqa: F401

# Auto-registro: cada import abaixo executa o decorador @AdapterManager.registrar(...)
from app.scraper.exemplo_adapter import PortalExemploAdapter        # noqa: F401
from app.scraper.akicapital_adapter import AkiCapitalAdapter        # noqa: F401
from app.scraper.gridsoftware_adapter import GridSoftwareAdapter    # noqa: F401


def consultar_margem(cpf: str, banco: str = "exemplo") -> dict:
    """
    Interface pública — equivalente a AdapterManager.consultar().

    Args:
        cpf:   CPF com ou sem formatação.
        banco: Chave do adaptador (exemplo | aki | grid | ...).

    Returns:
        dict com resultado da consulta de margem.
    """
    return AdapterManager.consultar(cpf=cpf, banco=banco)


def listar_adaptadores() -> list[str]:
    """Retorna lista de chaves de adaptadores disponíveis."""
    return AdapterManager.listar()
