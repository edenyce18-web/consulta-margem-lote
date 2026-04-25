"""
scraper/base_adapter.py
────────────────────────
Classe base abstrata para todos os adaptadores de portal.

Responsabilidades da base:
  - Validação de CPF antes de qualquer I/O
  - Gerenciamento do ciclo de vida do browser (Playwright)
  - Persistência de sessão em disco para reutilização entre CPFs
  - Auto-relogin quando sessão expirar
  - Captura de screenshot em caso de erro
  - Logging padronizado

Para criar um novo adaptador:

    from app.scraper.base_adapter import BaseScraperAdapter
    from app.scraper.manager import AdapterManager

    @AdapterManager.registrar("meu_banco")
    class MeuBancoAdapter(BaseScraperAdapter):
        NOME_BANCO   = "Meu Banco"
        CHAVE_SESSAO = "meu_banco"
        URL_LOGIN    = "https://portal.meubanco.com.br/login"

        def _esta_logado(self, page) -> bool:
            return "login" not in page.url.lower()

        def _fazer_login(self, page) -> None:
            page.fill("#usuario", "meu_login")
            page.fill("#senha",   "minha_senha")
            page.click("#entrar")
            page.wait_for_url("**/home**")

        def _extrair_margem(self, page, cpf: str) -> dict:
            # navegar + extrair → retornar dict
            ...
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.config import settings
from app.scraper.utils import (
    limpar_cpf, validar_cpf, pausa_humana,
    resultado_erro, resultado_cpf_invalido, salvar_screenshot,
)

logger = logging.getLogger(__name__)

# Diretório onde as sessões são persistidas
_SESSION_DIR = Path(settings.SESSION_DIR)
_SESSION_DIR.mkdir(parents=True, exist_ok=True)

# Timeouts padrão (ms)
TIMEOUT_NAV  = 30_000   # navegação entre páginas
TIMEOUT_EL   = 20_000   # aparecer de elementos
TIMEOUT_CONS = 45_000   # resultado de consulta

# User-Agent padrão (evita detecção de headless)
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class BaseScraperAdapter(ABC):
    """
    Interface e comportamento comum a todos os adaptadores de portal.

    Subclasses obrigatoriamente implementam:
        NOME_BANCO   : str   — nome legível do portal
        CHAVE_SESSAO : str   — identificador de arquivo de sessão
        URL_LOGIN    : str   — URL da página de login

        _esta_logado(page) -> bool
        _fazer_login(page) -> None
        _extrair_margem(page, cpf: str) -> dict
    """

    # ── Atributos de classe (sobrescrever em subclasses) ──────────────────────
    NOME_BANCO:   str = "Portal Genérico"
    CHAVE_SESSAO: str = "sessao_generica"
    URL_LOGIN:    str = ""

    # Argumentos extras para chromium.launch()
    ARGS_BROWSER: list[str] = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
    ]

    # ── Sessão persistente ────────────────────────────────────────────────────

    @property
    def _caminho_sessao(self) -> Path:
        return _SESSION_DIR / f"{self.CHAVE_SESSAO}.json"

    def _carregar_contexto(self, playwright):
        """
        Cria browser e context Playwright.
        Se existir sessão salva em disco, ela é carregada automaticamente.
        """
        browser = playwright.chromium.launch(
            headless=True,
            args=self.ARGS_BROWSER,
        )
        kwargs: dict = dict(
            user_agent=_USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="pt-BR",
        )
        if self._caminho_sessao.exists():
            kwargs["storage_state"] = str(self._caminho_sessao)
            logger.debug("[%s] Sessão carregada do disco.", self.NOME_BANCO)
        return browser, browser.new_context(**kwargs)

    def _salvar_sessao(self, context) -> None:
        """Persiste cookies e localStorage no disco."""
        try:
            context.storage_state(path=str(self._caminho_sessao))
            logger.debug("[%s] Sessão salva em disco.", self.NOME_BANCO)
        except Exception as exc:
            logger.warning("[%s] Não foi possível salvar sessão: %s", self.NOME_BANCO, exc)

    def _invalidar_sessao(self) -> None:
        """Remove sessão do disco, forçando novo login na próxima chamada."""
        if self._caminho_sessao.exists():
            self._caminho_sessao.unlink()
            logger.info("[%s] Sessão invalidada — próximo CPF fará novo login.", self.NOME_BANCO)

    # ── Métodos abstratos (implementar nas subclasses) ────────────────────────

    @abstractmethod
    def _esta_logado(self, page) -> bool:
        """Retorna True se a página atual indica sessão autenticada."""
        ...

    @abstractmethod
    def _fazer_login(self, page) -> None:
        """
        Executa o fluxo completo de autenticação no portal.
        Deve aguardar até estar na área logada antes de retornar.
        """
        ...

    @abstractmethod
    def _extrair_margem(self, page, cpf: str) -> dict:
        """
        Navega até a consulta de margem, insere o CPF e extrai os dados.

        Returns:
            dict com as chaves:
              cpf, status_consulta, mensagem_erro,
              nome_titular, margem_disponivel, margem_cartao,
              margem_beneficio, banco, orgao, dados_brutos
        """
        ...

    # ── Método público ────────────────────────────────────────────────────────

    def consultar(self, cpf: str) -> dict:
        """
        Ponto de entrada chamado pelo worker Celery.

        Fluxo:
          1. Valida CPF
          2. Abre browser e carrega sessão (se disponível)
          3. Verifica se sessão é válida; se não, faz login
          4. Delega extração ao _extrair_margem()
          5. Trata erros de timeout e genéricos

        Returns:
            dict padronizado com resultado da consulta.
        """
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        cpf_limpo = limpar_cpf(cpf)

        if not validar_cpf(cpf_limpo):
            logger.warning("[%s] CPF inválido: %s", self.NOME_BANCO, cpf_limpo)
            return resultado_cpf_invalido(cpf_limpo, self.NOME_BANCO)

        try:
            with sync_playwright() as p:
                browser, context = self._carregar_contexto(p)
                page = context.new_page()

                # Silencia logs de console do browser em produção
                page.on("console", lambda _: None)

                try:
                    # Navega ao login para verificar estado da sessão
                    page.goto(
                        self.URL_LOGIN,
                        wait_until="domcontentloaded",
                        timeout=TIMEOUT_NAV,
                    )
                    pausa_humana(0.5, 1.5)

                    # Login apenas se necessário
                    if not self._esta_logado(page):
                        logger.info(
                            "[%s] Sessão inativa para CPF %s — realizando login.",
                            self.NOME_BANCO, cpf_limpo,
                        )
                        self._invalidar_sessao()
                        self._fazer_login(page)
                        self._salvar_sessao(context)
                        logger.info("[%s] Login concluído.", self.NOME_BANCO)

                    # Extrai dados de margem
                    resultado = self._extrair_margem(page, cpf_limpo)
                    logger.info(
                        "[%s] CPF %s → status=%s margem=R$%s cartão=R$%s",
                        self.NOME_BANCO,
                        cpf_limpo,
                        resultado.get("status_consulta"),
                        resultado.get("margem_disponivel"),
                        resultado.get("margem_cartao"),
                    )
                    return resultado

                except PWTimeout as exc:
                    salvar_screenshot(page, f"timeout_{self.CHAVE_SESSAO}", _SESSION_DIR)
                    self._invalidar_sessao()
                    return resultado_erro(f"Timeout: {exc}", cpf_limpo, self.NOME_BANCO)

                except Exception as exc:
                    salvar_screenshot(page, f"erro_{self.CHAVE_SESSAO}", _SESSION_DIR)
                    self._invalidar_sessao()
                    raise

                finally:
                    browser.close()

        except Exception as exc:
            logger.exception(
                "[%s] Erro inesperado ao consultar CPF %s: %s",
                self.NOME_BANCO, cpf_limpo, exc,
            )
            return resultado_erro(str(exc), cpf_limpo, self.NOME_BANCO)

    # ── Helpers para subclasses ───────────────────────────────────────────────

    @staticmethod
    def _primeiro_seletor(page, seletores: list[str]) -> Optional[str]:
        """
        Retorna o primeiro seletor CSS da lista que tenha elementos na página.
        Útil para lidar com variações de layout entre portais.
        """
        for sel in seletores:
            try:
                if page.locator(sel).count() > 0:
                    return sel
            except Exception:
                continue
        return None

    @staticmethod
    def _texto_seletor(page, seletores: list[str]) -> Optional[str]:
        """
        Retorna o text_content do primeiro seletor encontrado na página.
        """
        for sel in seletores:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    texto = loc.first.text_content()
                    if texto and texto.strip():
                        return texto.strip()
            except Exception:
                continue
        return None
