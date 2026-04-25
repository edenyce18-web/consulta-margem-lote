import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from app import models


# ── Lotes ──────────────────────────────────────────────────────────────────────

def criar_lote(
    db: Session,
    arquivo_original: str,
    total_cpfs: int,
    banco_portal: str = "aki",
    usuario_id: Optional[uuid.UUID] = None,
) -> models.Lote:
    lote = models.Lote(
        arquivo_original=arquivo_original,
        total_cpfs=total_cpfs,
        banco_portal=banco_portal,
        usuario_id=usuario_id,
        status=models.StatusLote.pendente,
    )
    db.add(lote)
    db.commit()
    db.refresh(lote)
    return lote


def buscar_lote(db: Session, lote_id: uuid.UUID) -> Optional[models.Lote]:
    return db.query(models.Lote).filter(models.Lote.id == lote_id).first()


def listar_lotes(
    db: Session,
    usuario_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[models.Lote]:
    q = db.query(models.Lote)
    if usuario_id:
        q = q.filter(models.Lote.usuario_id == usuario_id)
    return q.order_by(models.Lote.criado_em.desc()).offset(skip).limit(limit).all()


def atualizar_status_lote(
    db: Session,
    lote_id: uuid.UUID,
    status: models.StatusLote,
    mensagem_erro: Optional[str] = None,
) -> Optional[models.Lote]:
    lote = buscar_lote(db, lote_id)
    if not lote:
        return None
    lote.status = status
    lote.atualizado_em = datetime.utcnow()
    if mensagem_erro:
        lote.mensagem_erro = mensagem_erro
    db.commit()
    db.refresh(lote)
    return lote


def incrementar_processado(
    db: Session, lote_id: uuid.UUID, sucesso: bool
) -> None:
    lote = buscar_lote(db, lote_id)
    if not lote:
        return
    lote.processados += 1
    if sucesso:
        lote.sucessos += 1
    else:
        lote.erros += 1
    lote.atualizado_em = datetime.utcnow()
    db.commit()


# ── Consultas ──────────────────────────────────────────────────────────────────

def criar_consultas_em_lote(
    db: Session, lote_id: uuid.UUID, cpfs: List[str]
) -> None:
    consultas = [
        models.Consulta(
            lote_id=lote_id,
            cpf=cpf,
            status_consulta=models.StatusConsulta.aguardando,
        )
        for cpf in cpfs
    ]
    db.bulk_save_objects(consultas)
    db.commit()


def buscar_consulta_por_cpf(
    db: Session, lote_id: uuid.UUID, cpf: str
) -> Optional[models.Consulta]:
    return (
        db.query(models.Consulta)
        .filter(models.Consulta.lote_id == lote_id, models.Consulta.cpf == cpf)
        .first()
    )


def atualizar_consulta(
    db: Session,
    lote_id: uuid.UUID,
    cpf: str,
    resultado: dict,
) -> Optional[models.Consulta]:
    consulta = buscar_consulta_por_cpf(db, lote_id, cpf)
    if not consulta:
        return None

    # Dados do servidor
    consulta.nome_titular  = resultado.get("nome_titular")
    consulta.orgao         = resultado.get("orgao")
    consulta.tipo_vinculo  = resultado.get("tipo_vinculo")
    consulta.matricula     = resultado.get("matricula")

    # Margens em R$
    consulta.margem_disponivel = resultado.get("margem_disponivel")
    consulta.margem_cartao     = resultado.get("margem_cartao")
    consulta.margem_beneficio  = resultado.get("margem_beneficio")

    # Situação de autorização (Aki Capital e similares)
    consulta.emprestimo_situacao       = resultado.get("emprestimo_situacao")
    consulta.cartao_credito_situacao   = resultado.get("cartao_credito_situacao")
    consulta.cartao_beneficio_situacao = resultado.get("cartao_beneficio_situacao")

    # Metadados
    consulta.banco           = resultado.get("banco")
    consulta.status_consulta = resultado.get("status_consulta", models.StatusConsulta.erro)
    consulta.mensagem_erro   = resultado.get("mensagem_erro")
    consulta.dados_brutos    = resultado.get("dados_brutos")
    consulta.consultado_em   = datetime.utcnow()

    db.commit()
    db.refresh(consulta)
    return consulta


def listar_consultas_lote(
    db: Session, lote_id: uuid.UUID, skip: int = 0, limit: int = 300
) -> List[models.Consulta]:
    return (
        db.query(models.Consulta)
        .filter(models.Consulta.lote_id == lote_id)
        .offset(skip)
        .limit(limit)
        .all()
    )
