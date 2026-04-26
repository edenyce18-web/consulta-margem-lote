"""
tasks.py — Tarefas Celery para processamento assíncrono de lotes.
"""

from __future__ import annotations

import uuid
import logging
from typing import List, Optional

from app.celery_app import celery_app
from app.database import SessionLocal
from app import crud, models
from app.scraper import consultar_margem

logger = logging.getLogger(__name__)


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

    try:
        crud.atualizar_status_lote(db, lote_uuid, models.StatusLote.processando)
        logger.info(
            "Lote %s iniciado | %d CPFs | portal: %s | credencial: %s",
            lote_id, len(cpfs), banco, credencial_id or "padrão",
        )

        # Carrega credencial uma vez para todo o lote
        credencial = _carregar_credencial(db, credencial_id)

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

            try:
                resultado = consultar_margem(cpf=cpf, banco=banco, credencial=credencial)
            except Exception as exc:
                logger.exception("Erro ao consultar CPF %s: %s", cpf, exc)
                resultado = {
                    "cpf":               cpf,
                    "status_consulta":   "erro",
                    "mensagem_erro":     str(exc),
                    "margem_disponivel": None,
                    "margem_cartao":     None,
                    "margem_beneficio":  None,
                    "nome_titular":      None,
                    "banco":             banco,
                    "orgao":             None,
                    "dados_brutos":      None,
                }

            crud.atualizar_consulta(db, lote_uuid, cpf, resultado)
            sucesso = resultado.get("status_consulta") == "sucesso"
            crud.incrementar_processado(db, lote_uuid, sucesso=sucesso)

            logger.info(
                "[%d/%d] CPF %s → %s",
                idx, len(cpfs), cpf, resultado.get("status_consulta"),
            )

        crud.atualizar_status_lote(db, lote_uuid, models.StatusLote.concluido)
        logger.info("Lote %s concluído.", lote_id)

    except Exception as exc:
        logger.exception("Falha crítica no lote %s: %s", lote_id, exc)
        crud.atualizar_status_lote(
            db, lote_uuid,
            models.StatusLote.erro,
            mensagem_erro=str(exc),
        )
        raise self.retry(exc=exc)

    finally:
        db.close()
