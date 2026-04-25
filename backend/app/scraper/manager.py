"""
scraper/manager.py
───────────────────
Registro central e fábrica de adaptadores de scraping.

O AdapterManager mantém um registry de classes de adaptadores e oferece
uma interface única para instanciar e invocar qualquer um deles.

Uso pelo código cliente (tasks.py, main.py):

    from app.scraper.manager import AdapterManager

    resultado = AdapterManager.consultar(cpf="12345678901", banco="aki")

Registro de novo adaptador (dentro do próprio arquivo do adaptador):

    from app.scraper.manager import AdapterManager
    from app.scraper.base_adapter import BaseScraperAdapter

    @AdapterManager.registrar("meu_banco")
    class MeuBancoAdapter(BaseScraperAdapter):
        ...

Os adaptadores se auto-registram quando seus módulos são importados.
O import de todos os módulos acontece em scraper/__init__.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.scraper.base_adapter import BaseScraperAdapter

logger = logging.getLogger(__name__)


class AdapterManager:
    """
    Registry + fábrica de adaptadores de scraping.

    Atributos de classe:
        _registry: Mapeamento chave → classe do adaptador.
    """

    _registry: dict[str, type] = {}

    # ── Registro ──────────────────────────────────────────────────────────────

    @classmethod
    def registrar(cls, chave: str):
        """
        Decorador para registrar um adaptador com uma chave de string.

        Exemplo:
            @AdapterManager.registrar("aki")
            class AkiCapitalAdapter(BaseScraperAdapter):
                ...
        """
        def decorator(adapter_cls):
            cls._registry[chave] = adapter_cls
            logger.debug("Adaptador registrado: '%s' → %s", chave, adapter_cls.__name__)
            return adapter_cls
        return decorator

    @classmethod
    def registrar_classe(cls, chave: str, adapter_cls: type) -> None:
        """Registro imperativo (alternativa ao decorador)."""
        cls._registry[chave] = adapter_cls
        logger.debug("Adaptador registrado: '%s' → %s", chave, adapter_cls.__name__)

    # ── Fábrica ───────────────────────────────────────────────────────────────

    @classmethod
    def obter(cls, banco: str) -> "BaseScraperAdapter":
        """
        Instancia e retorna o adaptador correspondente à chave.

        Args:
            banco: Chave do adaptador (ex: "aki", "grid", "exemplo").

        Returns:
            Instância do adaptador.

        Raises:
            KeyError: se a chave não estiver registrada.
        """
        if banco not in cls._registry:
            disponiveis = ", ".join(sorted(cls._registry.keys()))
            raise KeyError(
                f"Adaptador '{banco}' não encontrado. "
                f"Disponíveis: {disponiveis}"
            )
        return cls._registry[banco]()

    @classmethod
    def listar(cls) -> list[str]:
        """Retorna lista de chaves de adaptadores disponíveis."""
        return sorted(cls._registry.keys())

    # ── Interface de alto nível ───────────────────────────────────────────────

    @classmethod
    def consultar(cls, cpf: str, banco: str = "exemplo") -> dict:
        """
        Instancia o adaptador correto e executa a consulta de margem.

        Args:
            cpf:   CPF com ou sem formatação.
            banco: Chave do adaptador (padrão: "exemplo").

        Returns:
            dict com resultado da consulta.
        """
        adapter = cls.obter(banco)
        logger.info(
            "Iniciando consulta | CPF: %s | portal: %s (%s)",
            cpf, banco, adapter.NOME_BANCO,
        )
        return adapter.consultar(cpf)
