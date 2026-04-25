from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
import uuid


# ── Auth ──────────────────────────────────────────────────────────────────────

class UsuarioCreate(BaseModel):
    nome: str
    email: EmailStr
    senha: str


class UsuarioResponse(BaseModel):
    id: uuid.UUID
    nome: str
    email: str
    criado_em: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str


# ── Consulta ──────────────────────────────────────────────────────────────────

class ConsultaResponse(BaseModel):
    id: uuid.UUID
    cpf: str

    # Dados do servidor
    nome_titular: Optional[str]
    orgao: Optional[str]
    tipo_vinculo: Optional[str]
    matricula: Optional[str]

    # Margens em R$ (quando disponíveis)
    margem_disponivel: Optional[Decimal]
    margem_cartao: Optional[Decimal]
    margem_beneficio: Optional[Decimal]

    # Situação de autorização (Aki Capital)
    emprestimo_situacao: Optional[str]
    cartao_credito_situacao: Optional[str]
    cartao_beneficio_situacao: Optional[str]

    # Metadados
    banco: Optional[str]
    status_consulta: str
    mensagem_erro: Optional[str]
    consultado_em: Optional[datetime]

    class Config:
        from_attributes = True


# ── Lote ──────────────────────────────────────────────────────────────────────

class LoteResponse(BaseModel):
    id: uuid.UUID
    arquivo_original: Optional[str]
    banco_portal: Optional[str]
    total_cpfs: int
    processados: int
    sucessos: int
    erros: int
    status: str
    mensagem_erro: Optional[str]
    criado_em: datetime
    atualizado_em: datetime
    progresso_pct: float = 0.0

    class Config:
        from_attributes = True


class LoteDetalheResponse(LoteResponse):
    consultas: List[ConsultaResponse] = []

    class Config:
        from_attributes = True


class UploadLoteResponse(BaseModel):
    lote_id: uuid.UUID
    mensagem: str
    total_cpfs: int
