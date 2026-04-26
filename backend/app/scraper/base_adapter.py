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
import time
from abc import ABC, abstractmethod
from functools import wraps
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

TIMEOUT_NAV  = 60_000   # 60s — portais lentos precisam de tempo
TIMEOUT_EL   = 50_000   # 50s
TIMEOUT_CONS = 120_000  # 120s — aguarda resultado da consulta

# ── Decoradores de resiliência ────────────────────────────────────────────────

def medir_tempo(func):
    """Decorator que loga o tempo de execução de cada método."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        t0 = time.time()
        nome = func.__qualname__
        logger.info("⏱  Iniciando %s", nome)
        try:
            resultado = func(*args, **kwargs)
            logger.info("✅ %s concluído em %.1fs", nome, time.time() - t0)
            return resultado
        except Exception as exc:
            logger.error("❌ %s falhou após %.1fs: %s", nome, time.time() - t0, exc)
            raise
    return wrapper


def retry_com_backoff(tentativas: int = 3, delay_inicial: float = 5.0):
    """
    Decorator para retry com backoff exponencial.
    Captura TimeoutError e Exception genérica, aguarda e tenta novamente.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = delay_inicial
            ultima_exc = None
            for tentativa in range(1, tentativas + 1):
                try:
                    if tentativa > 1:
                        logger.info(
                            "🔄 %s — tentativa %d/%d (aguardando %.0fs)",
                            func.__qualname__, tentativa, tentativas, delay,
                        )
                        time.sleep(delay)
                        delay = min(delay * 2, 60)  # máximo 60s entre tentativas
                    return func(*args, **kwargs)
                except Exception as exc:
                    ultima_exc = exc
                    logger.warning(
                        "⚠  %s — tentativa %d/%d falhou: %s",
                        func.__qualname__, tentativa, tentativas, exc,
                    )
            logger.error(
                "❌ %s — todas as %d tentativas falharam. Último erro: %s",
                func.__qualname__, tentativas, ultima_exc,
            )
            raise ultima_exc
        return wrapper
    return decorator

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

    def __init__(self, credencial: Optional[dict] = None, usuario_id: Optional[str] = None):
        """
        Args:
            credencial:  Dict com chaves 'id', 'login', 'senha', 'url' (todos opcionais).
                         Se None, usa as configurações globais do settings.
            usuario_id:  UUID do usuário dono do lote.
                         Usado para isolar sessões quando não há credencial específica.
        """
        self._credencial = credencial or {}

        # Isola sessão por credencial (preferencial) ou por usuário (fallback)
        # → impede que dois usuários diferentes compartilhem a mesma sessão do portal
        cred_id = self._credencial.get("id")
        if cred_id:
            sufixo = cred_id.replace("-", "")[:8]
            self.CHAVE_SESSAO = f"{self.CHAVE_SESSAO}_{sufixo}"
        elif usuario_id:
            sufixo = str(usuario_id).replace("-", "")[:8]
            self.CHAVE_SESSAO = f"{self.CHAVE_SESSAO}_u{sufixo}"

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

    @medir_tempo
    @retry_com_backoff(tentativas=3, delay_inicial=5.0)
    def consultar(self, cpf: str) -> dict:
        import time
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        cpf_limpo = limpar_cpf(cpf)

        if not validar_cpf(cpf_limpo):
            logger.warning("[%s] CPF inválido: %s", self.NOME_BANCO, cpf_limpo)
            return resultado_cpf_invalido(cpf_limpo, self.NOME_BANCO)

        t0 = time.time()
        try:
            with sync_playwright() as p:
                browser, context = self._carregar_contexto(p)
                page = context.new_page()
                page.on("console", lambda _: None)

                try:
                    t1 = time.time()
                    page.goto(
                        self.URL_LOGIN,
                        wait_until="domcontentloaded",
                        timeout=TIMEOUT_NAV,
                    )
                    pausa_humana(0.5, 1.5)
                    logger.debug("[%s] Navegação inicial: %.1fs", self.NOME_BANCO, time.time()-t1)

                    if not self._esta_logado(page):
                        logger.info(
                            "[%s] Sessão inativa para CPF %s — realizando login.",
                            self.NOME_BANCO, cpf_limpo,
                        )
                        self._invalidar_sessao()
                        t2 = time.time()
                        self._fazer_login(page)
                        logger.info("[%s] Login concluído em %.1fs", self.NOME_BANCO, time.time()-t2)
                        self._salvar_sessao(context)
                    else:
                        logger.info("[%s] Sessão reutilizada para CPF %s", self.NOME_BANCO, cpf_limpo)

                    t3 = time.time()
                    resultado = self._extrair_margem(page, cpf_limpo)
                    logger.info(
                        "[%s] CPF %s → %s (extração: %.1fs | total: %.1fs)",
                        self.NOME_BANCO, cpf_limpo,
                        resultado.get("status_consulta"), time.time()-t3, time.time()-t0,
                    )
                    return resultado

                except PWTimeout as exc:
                    salvar_screenshot(page, f"timeout_{self.CHAVE_SESSAO}", _SESSION_DIR)
                    logger.warning(
                        "[%s] TIMEOUT após %.1fs consultando CPF %s — URL: %s",
                        self.NOME_BANCO, time.time()-t0, cpf_limpo, page.url,
                    )
                    self._invalidar_sessao()
                    return resultado_erro(f"Timeout ({time.time()-t0:.0f}s): {exc}", cpf_limpo, self.NOME_BANCO)

                except Exception:
                    salvar_screenshot(page, f"erro_{self.CHAVE_SESSAO}", _SESSION_DIR)
                    self._invalidar_sessao()
                    raise

                finally:
                    browser.close()

        except Exception as exc:
            logger.exception(
                "[%s] Erro inesperado ao consultar CPF %s após %.1fs: %s",
                self.NOME_BANCO, cpf_limpo, time.time()-t0, exc,
            )
            return resultado_erro(str(exc), cpf_limpo, self.NOME_BANCO)

    def consultar_com_page(self, page, cpf: str, context=None) -> dict:
        """
        Consulta um CPF usando uma page já aberta e (supostamente) autenticada.
        Chamado pelo BrowserLote para reutilizar a sessão entre CPFs.

        Re-autentica automaticamente se detectar redirecionamento para login.
        """
        import time as _time
        from app.scraper.utils import limpar_cpf, validar_cpf, resultado_cpf_invalido

        cpf_limpo = limpar_cpf(cpf)
        if not validar_cpf(cpf_limpo):
            logger.warning("[%s] CPF inválido: %s", self.NOME_BANCO, cpf_limpo)
            return resultado_cpf_invalido(cpf_limpo, self.NOME_BANCO)

        t0 = _time.time()

        # Detecta sessão expirada antes de tentar extrair
        if not self._esta_logado(page):
            logger.info(
                "[%s] Sessão expirada (mid-lote) — re-autenticando para CPF %s",
                self.NOME_BANCO, cpf_limpo,
            )
            self._invalidar_sessao()
            self._fazer_login(page)
            if context:
                self._salvar_sessao(context)

        try:
            resultado = self._extrair_margem(page, cpf_limpo)

            # Se durante a extração fomos redirecionados para login, tenta re-auth + retry
            if "login" in page.url.lower():
                logger.warning(
                    "[%s] Redirecionado para login durante extração do CPF %s — re-autenticando.",
                    self.NOME_BANCO, cpf_limpo,
                )
                self._invalidar_sessao()
                self._fazer_login(page)
                if context:
                    self._salvar_sessao(context)
                resultado = self._extrair_margem(page, cpf_limpo)

            logger.info(
                "[%s] CPF %s → %s (%.1fs)",
                self.NOME_BANCO, cpf_limpo,
                resultado.get("status_consulta"), _time.time() - t0,
            )
            return resultado

        except Exception as exc:
            logger.error(
                "[%s] Erro ao consultar CPF %s: %s (%.1fs)",
                self.NOME_BANCO, cpf_limpo, exc, _time.time() - t0,
            )
            from app.scraper.utils import resultado_erro
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
