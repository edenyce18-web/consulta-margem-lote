"""
scraper/browser_pool.py
────────────────────────
Gerenciador de browser por lote: abre UMA instância do Playwright + browser
para todo o lote, reutilizando login e contexto entre CPFs.

Uso (dentro de uma task Celery):

    from app.scraper.browser_pool import BrowserLote

    with BrowserLote(adapter) as bl:
        for cpf in cpfs:
            resultado = bl.consultar(cpf)

IMPORTANTE: Playwright sync_api NÃO é thread-safe.
Cada processo Celery tem seu próprio BrowserLote — nunca compartilhe entre workers.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class BrowserLote:
    """
    Context manager que mantém UM único browser/página abertos para o lote.

    Ciclo de vida:
      __enter__  → inicia playwright, lança browser, faz login se necessário
      consultar  → reutiliza a page já autenticada (sem abrir novo browser)
      __exit__   → fecha browser e para playwright
    """

    def __init__(self, adapter, cpfs_total: int = 0):
        self._adapter   = adapter
        self._cpfs_total = cpfs_total
        self._cpfs_ok   = 0
        self._cpfs_erro = 0
        self._t0        = time.time()

        # Playwright handles (preenchidos em __enter__)
        self._pw_ctx    = None
        self._pw        = None
        self._browser   = None
        self._context   = None
        self._page      = None

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "BrowserLote":
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        logger.info(
            "[BrowserLote] Iniciando lote de %d CPFs | portal: %s",
            self._cpfs_total, self._adapter.NOME_BANCO,
        )

        # Inicia Playwright uma única vez para todo o lote
        self._pw_ctx = sync_playwright()
        self._pw     = self._pw_ctx.__enter__()

        browser, context = self._adapter._carregar_contexto(self._pw)
        self._browser = browser
        self._context = context
        self._page    = context.new_page()
        self._page.on("console", lambda _: None)  # silencia logs do browser

        # Navegação inicial + login (uma única vez)
        try:
            self._page.goto(
                self._adapter.URL_LOGIN,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            _pausa(0.5, 1.5)

            if not self._adapter._esta_logado(self._page):
                logger.info("[BrowserLote] Sessão inativa — realizando login.")
                self._adapter._invalidar_sessao()
                self._adapter._fazer_login(self._page)
                self._adapter._salvar_sessao(self._context)
                logger.info("[BrowserLote] Login concluído.")
            else:
                logger.info("[BrowserLote] Sessão reutilizada do disco.")

        except PWTimeout as exc:
            logger.error("[BrowserLote] Timeout durante inicialização: %s", exc)
            self._fechar_recursos()
            raise

        except Exception as exc:
            logger.error("[BrowserLote] Erro ao inicializar browser: %s", exc)
            self._fechar_recursos()
            raise

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        elapsed = time.time() - self._t0
        total   = self._cpfs_ok + self._cpfs_erro
        taxa    = (self._cpfs_ok / max(total, 1) * 100)
        logger.info(
            "[BrowserLote] Encerrado em %.1fs | OK: %d | Erro: %d | Taxa: %.1f%%",
            elapsed, self._cpfs_ok, self._cpfs_erro, taxa,
        )
        self._fechar_recursos()
        return False  # não suprime exceções

    # ── Consulta ──────────────────────────────────────────────────────────────

    def consultar(self, cpf: str) -> dict:
        """
        Consulta um CPF reusando o browser/página já autenticados.
        Re-autentica automaticamente se a sessão expirar no meio do lote.
        """
        resultado = self._adapter.consultar_com_page(
            self._page, cpf, context=self._context
        )
        status = resultado.get("status_consulta", "?")
        if status == "sucesso":
            self._cpfs_ok += 1
        else:
            self._cpfs_erro += 1
        return resultado

    # ── Internos ──────────────────────────────────────────────────────────────

    def _fechar_recursos(self) -> None:
        try:
            if self._browser:
                self._browser.close()
        except Exception as exc:
            logger.warning("[BrowserLote] Erro ao fechar browser: %s", exc)
        try:
            if self._pw_ctx:
                self._pw_ctx.__exit__(None, None, None)
        except Exception as exc:
            logger.warning("[BrowserLote] Erro ao parar Playwright: %s", exc)


def _pausa(minimo: float = 0.5, maximo: float = 1.5) -> None:
    import random, time
    time.sleep(minimo + random.random() * (maximo - minimo))
