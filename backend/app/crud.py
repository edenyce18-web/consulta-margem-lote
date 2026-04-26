import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from app import models
from app.config import settings


# ── Lotes ──────────────────────────────────────────────────────────────────────

def criar_lote(
    db: Session,
    arquivo_original: str,
    total_cpfs: int,
    banco_portal: str = "aki",
    usuario_id: Optional[uuid.UUID] = None,
    credencial_id: Optional[uuid.UUID] = None,
) -> models.Lote:
    lote = models.Lote(
        arquivo_original=arquivo_original,
        total_cpfs=total_cpfs,
        banco_portal=banco_portal,
        usuario_id=usuario_id,
        credencial_id=credencial_id,
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


# ── Credenciais ────────────────────────────────────────────────────────────────

def criar_credencial(
    db: Session,
    usuario_id: uuid.UUID,
    nome: str,
    tipo_instituicao: str,
    login_enc: str,
    senha_enc: str,
    url_enc: Optional[str] = None,
) -> models.Credencial:
    cred = models.Credencial(
        usuario_id=usuario_id,
        nome=nome,
        tipo_instituicao=tipo_instituicao,
        login_enc=login_enc,
        senha_enc=senha_enc,
        url_enc=url_enc,
        status=models.StatusCredencial.ativa,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


def listar_credenciais(
    db: Session, usuario_id: uuid.UUID
) -> List[models.Credencial]:
    return (
        db.query(models.Credencial)
        .filter(
            models.Credencial.usuario_id == usuario_id,
            models.Credencial.deletado_em.is_(None),
        )
        .order_by(models.Credencial.criado_em.desc())
        .all()
    )


def buscar_credencial(
    db: Session, credencial_id: uuid.UUID, usuario_id: uuid.UUID
) -> Optional[models.Credencial]:
    return (
        db.query(models.Credencial)
        .filter(
            models.Credencial.id == credencial_id,
            models.Credencial.usuario_id == usuario_id,
            models.Credencial.deletado_em.is_(None),
        )
        .first()
    )


def buscar_credencial_por_id(
    db: Session, credencial_id: uuid.UUID
) -> Optional[models.Credencial]:
    return (
        db.query(models.Credencial)
        .filter(
            models.Credencial.id == credencial_id,
            models.Credencial.deletado_em.is_(None),
        )
        .first()
    )


def atualizar_credencial(
    db: Session,
    credencial_id: uuid.UUID,
    usuario_id: uuid.UUID,
    dados: dict,
) -> Optional[models.Credencial]:
    cred = (
        db.query(models.Credencial)
        .filter(
            models.Credencial.id == credencial_id,
            models.Credencial.usuario_id == usuario_id,
            models.Credencial.deletado_em.is_(None),
        )
        .first()
    )
    if not cred:
        return None
    for campo, valor in dados.items():
        if valor is not None and hasattr(cred, campo):
            setattr(cred, campo, valor)
    cred.atualizado_em = datetime.utcnow()
    db.commit()
    db.refresh(cred)
    return cred


def deletar_credencial(
    db: Session, credencial_id: uuid.UUID, usuario_id: uuid.UUID
) -> bool:
    cred = (
        db.query(models.Credencial)
        .filter(
            models.Credencial.id == credencial_id,
            models.Credencial.usuario_id == usuario_id,
            models.Credencial.deletado_em.is_(None),
        )
        .first()
    )
    if not cred:
        return False
    cred.deletado_em = datetime.utcnow()
    db.commit()
    return True


def marcar_credencial_testada(
    db: Session,
    credencial_id: uuid.UUID,
    sucesso: bool,
    mensagem_erro: Optional[str] = None,
) -> None:
    cred = db.query(models.Credencial).filter(models.Credencial.id == credencial_id).first()
    if cred:
        cred.testada_em = datetime.utcnow()
        cred.status = models.StatusCredencial.ativa if sucesso else models.StatusCredencial.erro
        cred.mensagem_erro = mensagem_erro
        db.commit()


# ── Refresh Tokens ─────────────────────────────────────────────────────────────

def criar_refresh_token(
    db: Session, usuario_id: uuid.UUID, token_hash: str, expires_at: datetime
) -> models.RefreshToken:
    rt = models.RefreshToken(
        usuario_id=usuario_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(rt)
    db.commit()
    db.refresh(rt)
    return rt


def buscar_refresh_token(db: Session, token_hash: str) -> Optional[models.RefreshToken]:
    return (
        db.query(models.RefreshToken)
        .filter(
            models.RefreshToken.token_hash == token_hash,
            models.RefreshToken.expires_at > datetime.utcnow(),
        )
        .first()
    )


def revogar_refresh_token(db: Session, token_hash: str) -> None:
    rt = db.query(models.RefreshToken).filter(models.RefreshToken.token_hash == token_hash).first()
    if rt:
        db.delete(rt)
        db.commit()


def revogar_todos_refresh_tokens(db: Session, usuario_id: uuid.UUID) -> None:
    db.query(models.RefreshToken).filter(
        models.RefreshToken.usuario_id == usuario_id
    ).delete()
    db.commit()


# ── Rate Limiting ──────────────────────────────────────────────────────────────

def registrar_tentativa_login(
    db: Session,
    email: str,
    ip_address: str,
    sucesso: bool,
    usuario_id: Optional[uuid.UUID] = None,
) -> None:
    tentativa = models.LoginAttempt(
        usuario_id=usuario_id,
        email=email,
        ip_address=ip_address,
        sucesso=sucesso,
    )
    db.add(tentativa)
    db.commit()


def contar_falhas_recentes(
    db: Session,
    email: str,
    ip_address: str,
    janela_minutos: int = None,
) -> int:
    if janela_minutos is None:
        janela_minutos = settings.LOGIN_LOCKOUT_MINUTES
    desde = datetime.utcnow() - timedelta(minutes=janela_minutos)
    return (
        db.query(models.LoginAttempt)
        .filter(
            models.LoginAttempt.email == email,
            models.LoginAttempt.sucesso == False,   # noqa: E712
            models.LoginAttempt.criado_em >= desde,
        )
        .count()
    )


# ── Audit Logs ─────────────────────────────────────────────────────────────────

def registrar_auditoria(
    db: Session,
    usuario_id: uuid.UUID,
    acao: str,
    tipo_entidade: Optional[str] = None,
    id_entidade: Optional[uuid.UUID] = None,
    detalhes: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    log = models.AuditLog(
        usuario_id=usuario_id,
        acao=acao,
        tipo_entidade=tipo_entidade,
        id_entidade=id_entidade,
        detalhes=detalhes,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    db.commit()


# ── Dashboard Stats ────────────────────────────────────────────────────────────

def stats_usuario(db: Session, usuario_id: uuid.UUID) -> dict:
    lotes = listar_lotes(db, usuario_id=usuario_id, limit=1000)
    total_lotes = len(lotes)
    total_cpfs = sum(l.total_cpfs for l in lotes)
    total_sucessos = sum(l.sucessos for l in lotes)
    total_erros = sum(l.erros for l in lotes)
    taxa = round(total_sucessos / total_cpfs * 100, 1) if total_cpfs else 0.0
    return {
        "total_lotes": total_lotes,
        "total_cpfs": total_cpfs,
        "total_sucessos": total_sucessos,
        "total_erros": total_erros,
        "taxa_sucesso_pct": taxa,
    }
