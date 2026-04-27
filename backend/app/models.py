import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, ForeignKey,
    Numeric, Integer, BigInteger, Text, Boolean,
    Enum as SAEnum, JSON, Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
import enum


# ── Enums ──────────────────────────────────────────────────────────────────────

class StatusLote(str, enum.Enum):
    pendente    = "pendente"
    processando = "processando"
    concluido   = "concluido"
    erro        = "erro"


class StatusConsulta(str, enum.Enum):
    aguardando   = "aguardando"
    processando  = "processando"
    sucesso      = "sucesso"
    erro         = "erro"
    cpf_invalido = "cpf_invalido"
    sem_margem   = "sem_margem"


class StatusCredencial(str, enum.Enum):
    ativa   = "ativa"
    inativa = "inativa"
    erro    = "erro"


# ── Usuário ────────────────────────────────────────────────────────────────────

class Usuario(Base):
    __tablename__ = "usuarios"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome       = Column(String(150), nullable=False)
    email      = Column(String(200), unique=True, nullable=False, index=True)
    senha_hash = Column(String(255), nullable=False)
    ativo      = Column(Boolean, default=True)
    criado_em  = Column(DateTime, default=datetime.utcnow)

    credenciais    = relationship("Credencial", back_populates="usuario")
    lotes          = relationship("Lote", back_populates="usuario")
    refresh_tokens = relationship("RefreshToken", back_populates="usuario", cascade="all, delete-orphan")
    audit_logs     = relationship("AuditLog", back_populates="usuario")


# ── Credenciais por usuário ────────────────────────────────────────────────────

class Credencial(Base):
    __tablename__ = "credenciais"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id   = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True)

    nome             = Column(String(255), nullable=False)          # "NyCred - Consultor 1"
    tipo_instituicao = Column(String(64),  nullable=False)          # "aki" | "grid" | "exemplo"

    login_enc  = Column(Text, nullable=False)   # AES-256-GCM
    senha_enc  = Column(Text, nullable=False)   # AES-256-GCM
    url_enc    = Column(Text, nullable=True)    # URL personalizada (opcional)

    status        = Column(SAEnum(StatusCredencial), default=StatusCredencial.ativa, nullable=False)
    mensagem_erro = Column(Text, nullable=True)
    testada_em    = Column(DateTime, nullable=True)

    criado_em     = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deletado_em   = Column(DateTime, nullable=True)    # soft delete

    usuario = relationship("Usuario", back_populates="credenciais")
    lotes   = relationship("Lote", back_populates="credencial")


# ── Lote ───────────────────────────────────────────────────────────────────────

class Lote(Base):
    __tablename__ = "lotes"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id       = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True, index=True)
    credencial_id    = Column(UUID(as_uuid=True), ForeignKey("credenciais.id"), nullable=True)
    arquivo_original = Column(String(255))
    banco_portal     = Column(String(50), nullable=True)
    total_cpfs       = Column(Integer, default=0)
    processados      = Column(Integer, default=0)
    sucessos         = Column(Integer, default=0)
    erros            = Column(Integer, default=0)
    status           = Column(SAEnum(StatusLote), default=StatusLote.pendente, nullable=False)
    mensagem_erro    = Column(Text, nullable=True)
    criado_em        = Column(DateTime, default=datetime.utcnow)
    atualizado_em    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usuario    = relationship("Usuario", back_populates="lotes")
    credencial = relationship("Credencial", back_populates="lotes")
    consultas  = relationship("Consulta", back_populates="lote", cascade="all, delete-orphan")


# ── Consulta ───────────────────────────────────────────────────────────────────

class Consulta(Base):
    __tablename__ = "consultas"

    id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lote_id = Column(UUID(as_uuid=True), ForeignKey("lotes.id"), nullable=False, index=True)
    cpf     = Column(String(14), nullable=False, index=True)

    nome_titular  = Column(String(200), nullable=True)
    orgao         = Column(String(200), nullable=True)
    tipo_vinculo  = Column(String(100), nullable=True)
    matricula     = Column(String(50),  nullable=True)

    margem_disponivel = Column(Numeric(12, 2), nullable=True)
    margem_cartao     = Column(Numeric(12, 2), nullable=True)
    margem_beneficio  = Column(Numeric(12, 2), nullable=True)

    emprestimo_situacao       = Column(String(30), nullable=True)
    cartao_credito_situacao   = Column(String(30), nullable=True)
    cartao_beneficio_situacao = Column(String(30), nullable=True)

    banco           = Column(String(100), nullable=True)
    status_consulta = Column(SAEnum(StatusConsulta), default=StatusConsulta.aguardando, nullable=False)
    mensagem_erro   = Column(Text, nullable=True)
    dados_brutos    = Column(Text, nullable=True)
    consultado_em   = Column(DateTime, nullable=True, index=True)
    criado_em       = Column(DateTime, default=datetime.utcnow)

    lote = relationship("Lote", back_populates="consultas")

    # T4: índice composto para busca eficiente por (lote, cpf) — padrão mais frequente
    __table_args__ = (
        Index("ix_consultas_lote_cpf", "lote_id", "cpf"),
    )


# ── Refresh Tokens ─────────────────────────────────────────────────────────────

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True)
    token_hash = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    criado_em  = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario", back_populates="refresh_tokens")


# ── Login Attempts (rate limiting) ─────────────────────────────────────────────

class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    email      = Column(String(200), nullable=True, index=True)
    ip_address = Column(String(45), nullable=False, index=True)
    sucesso    = Column(Boolean, nullable=False)
    criado_em  = Column(DateTime, default=datetime.utcnow, index=True)


# ── Audit Log ─────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id   = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True)
    acao         = Column(String(64), nullable=False, index=True)
    tipo_entidade = Column(String(64), nullable=True)
    id_entidade  = Column(UUID(as_uuid=True), nullable=True)
    detalhes     = Column(JSON, nullable=True)
    ip_address   = Column(String(45), nullable=True)
    user_agent   = Column(Text, nullable=True)
    criado_em    = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario", back_populates="audit_logs")
