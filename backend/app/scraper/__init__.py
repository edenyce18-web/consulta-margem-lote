"""
scraper/__init__.py
────────────────────
Ponto de entrada do pacote de scrapers.
"""

from app.scraper.manager import AdapterManager  # noqa: F401

# Auto-registro
from app.scraper.exemplo_adapter import PortalExemploAdapter        # noqa: F401
from app.scraper.akicapital_adapter import AkiCapitalAdapter        # noqa: F401
from app.scraper.gridsoftware_adapter import GridSoftwareAdapter    # noqa: F401


def consultar_margem(
    cpf: str,
    banco: str = "exemplo",
    credencial: dict = None,
) -> dict:
    """
    Interface pública para consulta de margem.

    Args:
        cpf:        CPF com ou sem formatação.
        banco:      Chave do adaptador (exemplo | aki | grid).
        credencial: Dict com chaves 'login', 'senha', 'url', 'id' (opcional).
                    Se None, usa configurações padrão do .env.
    """
    return AdapterManager.consultar(cpf=cpf, banco=banco, credencial=credencial)


def listar_adaptadores() -> list[str]:
    """Retorna lista de chaves de adaptadores disponíveis."""
    return AdapterManager.listar()
