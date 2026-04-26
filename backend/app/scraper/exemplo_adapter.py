"""
scraper/exemplo_adapter.py
───────────────────────────
Adaptador simulado — não faz scraping real.
Usado para testar o fluxo completo do sistema sem credenciais de portal.

Comportamento:
  - ~10% de chance de erro de timeout simulado
  - ~5% de chance de sem margem
  - Demais: retorna dados aleatórios realistas
"""

from __future__ import annotations

import json
import random
import logging

from app.scraper.base_adapter import BaseScraperAdapter
from app.scraper.manager import AdapterManager
from app.scraper.utils import (
    limpar_cpf, validar_cpf, pausa_humana,
    resultado_erro, resultado_cpf_invalido, resultado_sem_margem,
)

logger = logging.getLogger(__name__)


@AdapterManager.registrar("exemplo")
class PortalExemploAdapter(BaseScraperAdapter):
    """
    Simulador de portal bancário para testes de integração.
    Não abre navegador — retorna dados fictícios instantaneamente.
    """

    NOME_BANCO   = "Portal Exemplo (Simulado)"
    CHAVE_SESSAO = "exemplo"
    URL_LOGIN    = ""

    def __init__(self, credencial=None, usuario_id=None):
        super().__init__(credencial, usuario_id=usuario_id)

    # Sobrescreve consultar() diretamente — sem Playwright
    def consultar(self, cpf: str) -> dict:
        cpf_limpo = limpar_cpf(cpf)

        if not validar_cpf(cpf_limpo):
            return resultado_cpf_invalido(cpf_limpo, self.NOME_BANCO)

        pausa_humana(0.3, 1.0)

        sorteio = random.random()
        if sorteio < 0.10:
            return resultado_erro("Timeout simulado", cpf_limpo, self.NOME_BANCO)
        if sorteio < 0.15:
            return resultado_sem_margem(cpf_limpo, self.NOME_BANCO)

        margem    = round(random.uniform(100, 3_500), 2)
        cartao    = round(margem * 0.3, 2)
        beneficio = round(random.uniform(500, 5_000), 2)

        return {
            "cpf":              cpf_limpo,
            "status_consulta":  "sucesso",
            "mensagem_erro":    None,
            "nome_titular":     f"TITULAR DO CPF {cpf_limpo[-4:]}",
            "margem_disponivel": margem,
            "margem_cartao":    cartao,
            "margem_beneficio": beneficio,
            "banco":            self.NOME_BANCO,
            "orgao":            random.choice(["INSS", "SIAPE", "MILITAR"]),
            "dados_brutos":     json.dumps({
                "competencia": "04/2026",
                "especie":     "41",
                "situacao":    "ATIVO",
            }),
        }

    # BrowserLote chama consultar_com_page — redireciona para consultar() simulado
    def consultar_com_page(self, page, cpf: str, context=None) -> dict:
        return self.consultar(cpf)

    # Métodos abstratos (não usados neste adaptador)
    def _esta_logado(self, page) -> bool:
        return True

    def _fazer_login(self, page) -> None:
        pass

    def _extrair_margem(self, page, cpf: str) -> dict:
        return {}
