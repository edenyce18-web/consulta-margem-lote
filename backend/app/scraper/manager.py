"""
scraper/manager.py
───────────────────
Registro central e fábrica de adaptadores de scraping.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.scraper.base_adapter import BaseScraperAdapter

logger = logging.getLogger(__name__)


class AdapterManager:
    _registry: dict[str, type] = {}

    @classmethod
    def registrar(cls, chave: str):
        def decorator(adapter_cls):
            cls._registry[chave] = adapter_cls
            logger.debug("Adaptador registrado: '%s' → %s", chave, adapter_cls.__name__)
            return adapter_cls
        return decorator

    @classmethod
    def obter(
        cls,
        banco: str,
        credencial: Optional[dict] = None,
        usuario_id: Optional[str] = None,
    ) -> "BaseScraperAdapter":
        if banco not in cls._registry:
            disponiveis = ", ".join(sorted(cls._registry.keys()))
            raise KeyError(
                f"Adaptador '{banco}' não encontrado. Disponíveis: {disponiveis}"
            )
        return cls._registry[banco](credencial=credencial, usuario_id=usuario_id)

    @classmethod
    def listar(cls) -> list[str]:
        return sorted(cls._registry.keys())

    @classmethod
    def consultar(
        cls,
        cpf: str,
        banco: str = "exemplo",
        credencial: Optional[dict] = None,
    ) -> dict:
        adapter = cls.obter(banco, credencial=credencial)
        logger.info(
            "Iniciando consulta | CPF: %s | portal: %s (%s) | credencial: %s",
            cpf, banco, adapter.NOME_BANCO,
            credencial.get("id", "padrão") if credencial else "padrão",
        )
        return adapter.consultar(cpf)
