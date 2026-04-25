import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, ForeignKey,
    Numeric, Integer, Text, Enum as SAEnum, Boolean,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
import enum


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


class Usuario(Base):
    __tablename__ = "usuarios"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome        = Column(String(150), nullable=False)
    email       = Column(String(200), unique=True, nullable=False, index=True)
    senha_hash  = Column(String(255), nullable=False)
    ativo       = Column(Integer, default=1)
    criado_em   = Column(DateTime, default=datetime.utcnow)

    lotes = relationship("Lote", back_populates="usuario")


class Lote(Base):
    __tablename__ = "lotes"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id       = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    arquivo_original = Column(String(255))
    banco_portal     = Column(String(50), nullable=True)   # aki | grid | exemplo
    total_cpfs       = Column(Integer, default=0)
    processados      = Column(Integer, default=0)
    sucessos         = Column(Integer, default=0)
    erros            = Column(Integer, default=0)
    status           = Column(SAEnum(StatusLote), default=StatusLote.pendente, nullable=False)
    mensagem_erro    = Column(Text, nullable=True)
    criado_em        = Column(DateTime, default=datetime.utcnow)
    atualizado_em    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usuario  = relationship("Usuario", back_populates="lotes")
    consultas = relationship("Consulta", back_populates="lote", cascade="all, delete-orphan")


class Consulta(Base):
    __tablename__ = "consultas"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lote_id      = Column(UUID(as_uuid=True), ForeignKey("lotes.id"), nullable=False, index=True)
    cpf          = Column(String(14), nullable=False, index=True)

    # ── Dados do servidor ─────────────────────────────────────────────────────
    nome_titular  = Column(String(200), nullable=True)
    orgao         = Column(String(200), nullable=True)
    tipo_vinculo  = Column(String(100), nullable=True)   # Servidor / Pensionista
    matricula     = Column(String(50),  nullable=True)

    # ── Margens numéricas (quando o portal expõe o valor) ────────────────────
    margem_disponivel = Column(Numeric(12, 2), nullable=True)  # Empréstimo em R$
    margem_cartao     = Column(Numeric(12, 2), nullable=True)  # Cartão Crédito em R$
    margem_beneficio  = Column(Numeric(12, 2), nullable=True)  # Cartão Benefício em R$

    # ── Situação de autorização (Aki Capital e similares) ─────────────────────
    emprestimo_situacao       = Column(String(30), nullable=True)  # Autorizado / Não Autorizado
    cartao_credito_situacao   = Column(String(30), nullable=True)
    cartao_beneficio_situacao = Column(String(30), nullable=True)

    # ── Metadados ─────────────────────────────────────────────────────────────
    banco         = Column(String(100), nullable=True)
    status_consulta = Column(
        SAEnum(StatusConsulta), default=StatusConsulta.aguardando, nullable=False
    )
    mensagem_erro  = Column(Text, nullable=True)
    dados_brutos   = Column(Text, nullable=True)  # JSON completo do portal
    consultado_em  = Column(DateTime, nullable=True)
    criado_em      = Column(DateTime, default=datetime.utcnow)

    lote = relationship("Lote", back_populates="consultas")
