"""
tasks.py — Tarefas Celery para processamento assíncrono de lotes.
"""

from __future__ import annotations

import json
import time
import uuid
import logging
from typing import List, Optional

import redis as redis_lib

from app.celery_app import celery_app
from app.config import settings
from app.database import SessionLocal
from app import crud, models
from app.scraper import consultar_margem, listar_adaptadores
from app.scraper.manager import AdapterManager
from app.scraper.browser_pool import BrowserLote

logger = logging.getLogger(__name__)

# Delay (segundos) entre CPFs após um timeout, para dar respiro ao portal
_DELAY_POS_TIMEOUT = 3.0
_DELAY_POS_ERRO    = 1.0

# T5: Cache Redis — TTL de 24h; evita re-consultar o portal para CPFs recentes
_CACHE_TTL_S   = 86_400   # 24 horas
_CACHE_PREFIX  = "margem:"

# T6: Commita BD em lotes para reduzir round-trips
_BATCH_SIZE = 5

# Cliente Redis compartilhado no processo Celery
_redis_client: Optional[redis_lib.Redis] = None


def _get_redis() -> Optional[redis_lib.Redis]:
    """Retorna cliente Redis (lazy init). Retorna None se Redis indisponível."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
            _redis_client.ping()
        except Exception as exc:
            logger.warning("Redis indisponível — cache desativado: %s", exc)
            _redis_client = None
    return _redis_client


def _cache_get(banco: str, cpf: str) -> Optional[dict]:
    """T5: Retorna resultado cacheado ou None."""
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(f"{_CACHE_PREFIX}{banco}:{cpf}")
        if raw:
            logger.info("Cache HIT para CPF %s (%s)", cpf, banco)
            return json.loads(raw)
    except Exception as exc:
        logger.debug("Erro ao ler cache: %s", exc)
    return None


def _cache_set(banco: str, cpf: str, resultado: dict) -> None:
    """T5: Salva resultado no cache se status for sucesso ou sem_margem."""
    if resultado.get("status_consulta") not in ("sucesso", "sem_margem"):
        return  # não cacheia erros (podem ser transientes)
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(
            f"{_CACHE_PREFIX}{banco}:{cpf}",
            _CACHE_TTL_S,
            json.dumps(resultado, default=str),
        )
    except Exception as exc:
        logger.debug("Erro ao salvar cache: %s", exc)


def _flush_buffer(db, lote_uuid: uuid.UUID, buffer: list) -> None:
    """T6: Commita resultados acumulados no buffer em uma única transação."""
    if not buffer:
        return
    sucessos = 0
    for resultado in buffer:
        consulta = crud.buscar_consulta_por_cpf(db, lote_uuid, resultado["cpf"])
        if consulta:
            from datetime import datetime
            consulta.nome_titular  = resultado.get("nome_titular")
            consulta.orgao         = resultado.get("orgao")
            consulta.tipo_vinculo  = resultado.get("tipo_vinculo")
            consulta.matricula     = resultado.get("matricula")
            consulta.margem_disponivel = resultado.get("margem_disponivel")
            consulta.margem_cartao     = resultado.get("margem_cartao")
            consulta.margem_beneficio  = resultado.get("margem_beneficio")
            consulta.emprestimo_situacao       = resultado.get("emprestimo_situacao")
            consulta.cartao_credito_situacao   = resultado.get("cartao_credito_situacao")
            consulta.cartao_beneficio_situacao = resultado.get("cartao_beneficio_situacao")
            consulta.banco           = resultado.get("banco")
            consulta.status_consulta = resultado.get("status_consulta", models.StatusConsulta.erro)
            consulta.mensagem_erro   = resultado.get("mensagem_erro")
            consulta.dados_brutos    = resultado.get("dados_brutos")
            consulta.consultado_em   = datetime.utcnow()
        if resultado.get("status_consulta") == "sucesso":
            sucessos += 1

    lote = crud.buscar_lote(db, lote_uuid)
    if lote:
        from datetime import datetime
        lote.processados += len(buffer)
        lote.sucessos    += sucessos
        lote.erros       += len(buffer) - sucessos
        lote.atualizado_em = datetime.utcnow()

    db.commit()
    buffer.clear()


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
        buffer: list = []       # T6: buffer de resultados para commit em lote

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

                # T5: verifica cache antes de consultar o portal
                from app.scraper.utils import limpar_cpf
                cpf_limpo = limpar_cpf(cpf)
                resultado = _cache_get(banco, cpf_limpo)
                if resultado:
                    resultado["cpf"] = cpf_limpo  # garante CPF sem formatação
                    buffer.append(resultado)
                    # T6: flush se buffer atingiu tamanho alvo
                    if len(buffer) >= _BATCH_SIZE:
                        _flush_buffer(db, lote_uuid, buffer)
                    logger.info(
                        "📋 [%d/%d] CPF %s → %s (cache, %.1fs)",
                        idx, len(cpfs), cpf,
                        resultado.get("status_consulta"),
                        time.time() - t_cpf,
                    )
                    continue

                try:
                    resultado = bl.consultar(cpf)
                    consecutivos_timeout = 0  # reset após sucesso

                    # T5: salva resultado válido no cache
                    _cache_set(banco, cpf_limpo, resultado)

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

                # T6: acumula no buffer em vez de commitar por CPF
                buffer.append(resultado)
                if len(buffer) >= _BATCH_SIZE:
                    _flush_buffer(db, lote_uuid, buffer)

                logger.info(
                    "📋 [%d/%d] CPF %s → %s (%.1fs)",
                    idx, len(cpfs), cpf,
                    resultado.get("status_consulta"),
                    time.time() - t_cpf,
                )

        # T6: flush do restante após o lote
        _flush_buffer(db, lote_uuid, buffer)

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
