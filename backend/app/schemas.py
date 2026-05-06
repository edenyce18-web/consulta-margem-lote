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
    ativo: bool = True
    is_admin: bool = False

    class Config:
        from_attributes = True


class AdminUsuarioResponse(BaseModel):
    id: uuid.UUID
    nome: str
    email: str
    criado_em: datetime
    ativo: bool
    is_admin: bool = False
    total_lotes: int = 0
    total_cpfs: int = 0

    class Config:
        from_attributes = True


class AdminStatsResponse(BaseModel):
    total_usuarios: int
    total_cpfs_processados: int
    total_lotes: int
    usuarios_ativos: int


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str


# ── Credenciais ───────────────────────────────────────────────────────────────

class CredencialCreate(BaseModel):
    nome: str
    tipo_instituicao: str   # "aki" | "grid" | "exemplo"
    login: str
    senha: str
    url: Optional[str] = None


class CredencialUpdate(BaseModel):
    nome: Optional[str] = None
    login: Optional[str] = None
    senha: Optional[str] = None
    url: Optional[str] = None
    status: Optional[str] = None


class CredencialResponse(BaseModel):
    id: uuid.UUID
    nome: str
    tipo_instituicao: str
    status: str
    mensagem_erro: Optional[str]
    testada_em: Optional[datetime]
    criado_em: datetime
    # login e senha NUNCA retornados

    class Config:
        from_attributes = True


# ── Consulta ──────────────────────────────────────────────────────────────────

class ConsultaResponse(BaseModel):
    id: uuid.UUID
    cpf: str
    nome_titular: Optional[str]
    orgao: Optional[str]
    tipo_vinculo: Optional[str]
    matricula: Optional[str]
    margem_disponivel: Optional[Decimal]
    margem_cartao: Optional[Decimal]
    margem_beneficio: Optional[Decimal]
    emprestimo_situacao: Optional[str]
    cartao_credito_situacao: Optional[str]
    cartao_beneficio_situacao: Optional[str]
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
    credencial_id: Optional[uuid.UUID]
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


# ── Dashboard ─────────────────────────────────────────────────────────────────

class ConsultasDia(BaseModel):
    dia: str
    total: int


class MargemBanco(BaseModel):
    banco: str
    cpfs: int
    sucessos: int


class DashboardStats(BaseModel):
    total_lotes: int
    total_cpfs: int
    total_sucessos: int
    total_erros: int
    taxa_sucesso_pct: float
    lotes_recentes: List[LoteResponse] = []
    consultas_por_dia: List[ConsultasDia] = []
    margens_por_banco: List[MargemBanco] = []
