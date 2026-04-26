"""
tasks.py — Tarefas Celery para processamento assíncrono de lotes.
"""

from __future__ import annotations

import time
import uuid
import logging
from typing import List, Optional

from app.celery_app import celery_app
from app.database import SessionLocal
from app import crud, models
from app.scraper import consultar_margem, listar_adaptadores
from app.scraper.manager import AdapterManager
from app.scraper.browser_pool import BrowserLote

logger = logging.getLogger(__name__)

# Delay (segundos) entre CPFs após um timeout, para dar respiro ao portal
_DELAY_POS_TIMEOUT = 3.0
_DELAY_POS_ERRO    = 1.0


def _carregar_credencial(db, credencial_id: Optional[str]) -> Optional[dict]:
    """Carrega e descriptografa credencial do banco de dados."""
    if not credencial_id:
        return None
    try:
        from app.config import settings
        from app.crypto import decrypt

        cred = crud.buscar_credencial_por_id(db, uuid.UUID(credencial_id))
        if not cred or cred.deletado_em:
            logger.warning("Credencial %s não encontrada ou deletada.", credencial_id)
            return None

        return {
            "id": str(cred.id),
            "login": decrypt(cred.login_enc, settings.ENCRYPTION_KEY),
            "senha": decrypt(cred.senha_enc, settings.ENCRYPTION_KEY),
            "url":   decrypt(cred.url_enc, settings.ENCRYPTION_KEY) if cred.url_enc else None,
        }
    except Exception as exc:
        logger.exception("Erro ao carregar credencial %s: %s", credencial_id, exc)
        return None


@celery_app.task(
    bind=True,
    name="app.tasks.processar_lote",
    max_retries=2,
    default_retry_delay=30,
)
def processar_lote(
    self,
    lote_id: str,
    cpfs: List[str],
    banco: str = "exemplo",
    credencial_id: Optional[str] = None,
    usuario_id: Optional[str] = None,
):
    """
    Tarefa Celery principal.

    Args:
        lote_id:       UUID do lote (string).
        cpfs:          Lista de CPFs a consultar.
        banco:         Chave do adaptador (aki | grid | exemplo).
        credencial_id: UUID da credencial do usuário (opcional).
    """
    db = SessionLocal()
    lote_uuid = uuid.UUID(lote_id)
    t_lote = time.time()

    try:
        crud.atualizar_status_lote(db, lote_uuid, models.StatusLote.processando)
        logger.info(
            "🚀 Lote %s iniciado | %d CPFs | portal: %s | credencial: %s",
            lote_id, len(cpfs), banco, credencial_id or "padrão",
        )

        # Carrega credencial uma vez para todo o lote
        credencial = _carregar_credencial(db, credencial_id)

        # Cria o adapter com credencial e usuario_id (isola sessão por usuário)
        adapter = AdapterManager.obter(banco, credencial=credencial, usuario_id=usuario_id)

        consecutivos_timeout = 0  # rastreia timeouts seguidos para dar mais pausa

        with BrowserLote(adapter, cpfs_total=len(cpfs)) as bl:
            for idx, cpf in enumerate(cpfs, start=1):
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "atual":     idx,
                        "total":     len(cpfs),
                        "cpf_atual": cpf,
                        "banco":     banco,
                    },
                )

                t_cpf = time.time()
                try:
                    resultado = bl.consultar(cpf)
                    consecutivos_timeout = 0  # reset após sucesso

                except Exception as exc:
                    msg = str(exc)
                    is_timeout = "timeout" in msg.lower() or "Timeout" in msg
                    consecutivos_timeout += 1 if is_timeout else 0

                    logger.warning(
                        "⚠  CPF %s — %s após %.1fs (consecutivos: %d)",
                        cpf, "TIMEOUT" if is_timeout else "ERRO",
                        time.time() - t_cpf, consecutivos_timeout,
                    )

                    resultado = {
                        "cpf":               cpf,
                        "status_consulta":   "erro",
                        "mensagem_erro":     msg,
                        "margem_disponivel": None,
                        "margem_cartao":     None,
                        "margem_beneficio":  None,
                        "nome_titular":      None,
                        "banco":             banco,
                        "orgao":             None,
                        "dados_brutos":      None,
                    }

                    # Delay entre CPFs para não sobrecarregar o portal
                    pausa = _DELAY_POS_TIMEOUT * consecutivos_timeout if is_timeout else _DELAY_POS_ERRO
                    pausa = min(pausa, 30)  # máximo 30s de pausa
                    if pausa > 0:
                        logger.info("⏳ Aguardando %.0fs antes do próximo CPF...", pausa)
                        time.sleep(pausa)

                crud.atualizar_consulta(db, lote_uuid, cpf, resultado)
                sucesso = resultado.get("status_consulta") == "sucesso"
                crud.incrementar_processado(db, lote_uuid, sucesso=sucesso)

                logger.info(
                    "📋 [%d/%d] CPF %s → %s (%.1fs)",
                    idx, len(cpfs), cpf,
                    resultado.get("status_consulta"),
                    time.time() - t_cpf,
                )

        crud.atualizar_status_lote(db, lote_uuid, models.StatusLote.concluido)
        logger.info(
            "✅ Lote %s concluído em %.1fs | %d CPFs",
            lote_id, time.time() - t_lote, len(cpfs),
        )

    except Exception as exc:
        logger.exception("❌ Falha crítica no lote %s: %s", lote_id, exc)
        crud.atualizar_status_lote(
            db, lote_uuid,
            models.StatusLote.erro,
            mensagem_erro=str(exc),
        )
        raise self.retry(exc=exc)

    finally:
        db.close()
