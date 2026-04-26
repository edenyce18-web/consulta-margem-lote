"""
scraper/base_adapter.py
────────────────────────
Classe base abstrata para todos os adaptadores de portal.

Suporte a credenciais dinâmicas por usuário:
  - Recebe `credencial` dict no construtor com chaves: login, senha, url, id
  - Sessão Playwright é isolada por credencial (arquivo separado por credencial_id)
  - Fallback para settings globais se credencial não fornecida
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

_SESSION_DIR = Path(settings.SESSION_DIR)
_SESSION_DIR.mkdir(parents=True, exist_ok=True)

TIMEOUT_NAV  = 30_000
TIMEOUT_EL   = 20_000
TIMEOUT_CONS = 45_000

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class BaseScraperAdapter(ABC):
    """
    Interface e comportamento comum a todos os adaptadores de portal.

    Para credenciais por usuário, passe o dict `credencial` no construtor:
        adapter = AkiCapitalAdapter(credencial={"id": "...", "login": "...", "senha": "..."})
    """

    NOME_BANCO:   str = "Portal Genérico"
    CHAVE_SESSAO: str = "sessao_generica"
    URL_LOGIN:    str = ""

    ARGS_BROWSER: list[str] = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
    ]

    def __init__(self, credencial: Optional[dict] = None):
        """
        Args:
            credencial: Dict com chaves 'id', 'login', 'senha', 'url' (todos opcionais).
                        Se None, usa as configurações globais do settings.
        """
        self._credencial = credencial or {}
        # Isola sessão por credencial para evitar conflito entre usuários
        cred_id = self._credencial.get("id")
        if cred_id:
            # Usa sufixo curto do UUID para não tornar o nome muito longo
            sufixo = cred_id.replace("-", "")[:8]
            self.CHAVE_SESSAO = f"{self.CHAVE_SESSAO}_{sufixo}"

    # ── Sessão persistente ────────────────────────────────────────────────────

    @property
    def _caminho_sessao(self) -> Path:
        return _SESSION_DIR / f"{self.CHAVE_SESSAO}.json"

    def _carregar_contexto(self, playwright):
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
        try:
            context.storage_state(path=str(self._caminho_sessao))
            logger.debug("[%s] Sessão salva em disco.", self.NOME_BANCO)
        except Exception as exc:
            logger.warning("[%s] Não foi possível salvar sessão: %s", self.NOME_BANCO, exc)

    def _invalidar_sessao(self) -> None:
        if self._caminho_sessao.exists():
            self._caminho_sessao.unlink()
            logger.info("[%s] Sessão invalidada.", self.NOME_BANCO)

    # ── Métodos abstratos ─────────────────────────────────────────────────────

    @abstractmethod
    def _esta_logado(self, page) -> bool:
        ...

    @abstractmethod
    def _fazer_login(self, page) -> None:
        ...

    @abstractmethod
    def _extrair_margem(self, page, cpf: str) -> dict:
        ...

    # ── Método público ────────────────────────────────────────────────────────

    def consultar(self, cpf: str) -> dict:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        cpf_limpo = limpar_cpf(cpf)

        if not validar_cpf(cpf_limpo):
            logger.warning("[%s] CPF inválido: %s", self.NOME_BANCO, cpf_limpo)
            return resultado_cpf_invalido(cpf_limpo, self.NOME_BANCO)

        try:
            with sync_playwright() as p:
                browser, context = self._carregar_contexto(p)
                page = context.new_page()
                page.on("console", lambda _: None)

                try:
                    page.goto(
                        self.URL_LOGIN,
                        wait_until="domcontentloaded",
                        timeout=TIMEOUT_NAV,
                    )
                    pausa_humana(0.5, 1.5)

                    if not self._esta_logado(page):
                        logger.info(
                            "[%s] Sessão inativa para CPF %s — realizando login.",
                            self.NOME_BANCO, cpf_limpo,
                        )
                        self._invalidar_sessao()
                        self._fazer_login(page)
                        self._salvar_sessao(context)

                    resultado = self._extrair_margem(page, cpf_limpo)
                    return resultado

                except PWTimeout as exc:
                    salvar_screenshot(page, f"timeout_{self.CHAVE_SESSAO}", _SESSION_DIR)
                    self._invalidar_sessao()
                    return resultado_erro(f"Timeout: {exc}", cpf_limpo, self.NOME_BANCO)

                except Exception:
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
        for sel in seletores:
            try:
                if page.locator(sel).count() > 0:
                    return sel
            except Exception:
                continue
        return None

    @staticmethod
    def _texto_seletor(page, seletores: list[str]) -> Optional[str]:
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
