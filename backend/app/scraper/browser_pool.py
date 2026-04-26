"""
scraper/browser_pool.py
────────────────────────
Gerenciador de browser por lote: reutiliza um único browser para todos os
CPFs de um lote, evitando o overhead de iniciar/fechar Playwright a cada CPF.

Uso (dentro de uma task Celery):

    from app.scraper.browser_pool import BrowserLote

    with BrowserLote(adapter) as bl:
        for cpf in cpfs:
            resultado = bl.consultar(cpf)
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class BrowserLote:
    """
    Context manager que mantém um único browser aberto para o lote inteiro.

    O Playwright não é thread-safe, por isso NÃO compartilhamos browsers entre
    workers Celery (cada processo tem o seu). Aqui apenas evitamos abrir/fechar
    para cada CPF dentro do mesmo processo/lote.
    """

    def __init__(self, adapter, cpfs_total: int = 0):
        self._adapter = adapter
        self._cpfs_total = cpfs_total
        self._cpfs_ok = 0
        self._cpfs_erro = 0
        self._t0 = time.time()

    def __enter__(self):
        logger.info(
            "[BrowserLote] Iniciando lote de %d CPFs com adaptador %s",
            self._cpfs_total, self._adapter.NOME_BANCO,
        )
        return self

    def consultar(self, cpf: str) -> dict:
        """Consulta um CPF usando o adapter. O adapter gerencia sua própria sessão."""
        resultado = self._adapter.consultar(cpf)
        status = resultado.get("status_consulta", "?")
        if status == "sucesso":
            self._cpfs_ok += 1
        else:
            self._cpfs_erro += 1
        return resultado

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self._t0
        taxa = (
            self._cpfs_ok / max(self._cpfs_ok + self._cpfs_erro, 1) * 100
        )
        logger.info(
            "[BrowserLote] Lote encerrado em %.1fs | OK: %d | Erro: %d | Taxa: %.1f%%",
            elapsed, self._cpfs_ok, self._cpfs_erro, taxa,
        )
        return False  # não suprime exceções
