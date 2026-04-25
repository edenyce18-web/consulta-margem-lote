"""
tasks.py — Tarefas Celery para processamento assíncrono de lotes.

Cada tarefa recebe um lote_id e a lista de CPFs, itera sobre eles,
chama o adaptador de scraping correto via AdapterManager e persiste
os resultados individuais no PostgreSQL.
"""

from __future__ import annotations

import uuid
import logging
from typing import List

from app.celery_app import celery_app
from app.database import SessionLocal
from app import crud, models
from app.scraper import consultar_margem   # usa o novo pacote modular

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.processar_lote",
    max_retries=2,
    default_retry_delay=30,
)
def processar_lote(self, lote_id: str, cpfs: List[str], banco: str = "exemplo"):
    """
    Tarefa Celery principal.

    Processa cada CPF do lote sequencialmente, atualizando o banco de
    dados após cada consulta para permitir polling em tempo real pelo
    frontend.

    Args:
        lote_id: UUID do lote (string).
        cpfs:    Lista de CPFs a consultar.
        banco:   Chave do adaptador (exemplo | aki | grid | ...).
    """
    db = SessionLocal()
    lote_uuid = uuid.UUID(lote_id)

    try:
        crud.atualizar_status_lote(db, lote_uuid, models.StatusLote.processando)
        logger.info(
            "Lote %s iniciado | %d CPFs | portal: %s",
            lote_id, len(cpfs), banco,
        )

        for idx, cpf in enumerate(cpfs, start=1):
            # Publica progresso no backend Celery (visível via Flower)
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
                resultado = consultar_margem(cpf=cpf, banco=banco)
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

            # Persiste resultado no banco
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
