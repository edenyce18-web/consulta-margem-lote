"""Initial schema — multi-user system

Revision ID: 0001
Revises:
Create Date: 2026-04-26

Cria todas as tabelas do sistema v2.0 multi-usuário.
Se as tabelas já existem (criadas por create_all), as operações são seguras
pois usam checkfirst=True.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = inspector.get_table_names()

    # ── usuarios ──────────────────────────────────────────────────────────────
    if "usuarios" not in existing:
        op.create_table(
            "usuarios",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("nome", sa.String(150), nullable=False),
            sa.Column("email", sa.String(200), unique=True, nullable=False),
            sa.Column("senha_hash", sa.String(255), nullable=False),
            sa.Column("ativo", sa.Boolean(), default=True),
            sa.Column("criado_em", sa.DateTime(), default=sa.func.now()),
        )
        op.create_index("ix_usuarios_email", "usuarios", ["email"])
    else:
        # Adiciona coluna 'ativo' se não existir
        cols = [c["name"] for c in inspector.get_columns("usuarios")]
        if "ativo" not in cols:
            op.add_column("usuarios", sa.Column("ativo", sa.Boolean(), server_default="true"))

    # ── credenciais ───────────────────────────────────────────────────────────
    if "credenciais" not in existing:
        op.create_table(
            "credenciais",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("nome", sa.String(255), nullable=False),
            sa.Column("tipo_instituicao", sa.String(64), nullable=False),
            sa.Column("login_enc", sa.Text(), nullable=False),
            sa.Column("senha_enc", sa.Text(), nullable=False),
            sa.Column("url_enc", sa.Text()),
            sa.Column("status", sa.String(20), server_default="ativa"),
            sa.Column("mensagem_erro", sa.Text()),
            sa.Column("testada_em", sa.DateTime()),
            sa.Column("criado_em", sa.DateTime(), default=sa.func.now()),
            sa.Column("atualizado_em", sa.DateTime(), default=sa.func.now()),
            sa.Column("deletado_em", sa.DateTime()),
        )
        op.create_index("ix_credenciais_usuario_id", "credenciais", ["usuario_id"])

    # ── lotes ─────────────────────────────────────────────────────────────────
    if "lotes" not in existing:
        op.create_table(
            "lotes",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id")),
            sa.Column("credencial_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("credenciais.id")),
            sa.Column("arquivo_original", sa.String(255)),
            sa.Column("banco_portal", sa.String(50)),
            sa.Column("total_cpfs", sa.Integer(), default=0),
            sa.Column("processados", sa.Integer(), default=0),
            sa.Column("sucessos", sa.Integer(), default=0),
            sa.Column("erros", sa.Integer(), default=0),
            sa.Column("status", sa.String(20), server_default="pendente"),
            sa.Column("mensagem_erro", sa.Text()),
            sa.Column("criado_em", sa.DateTime(), default=sa.func.now()),
            sa.Column("atualizado_em", sa.DateTime(), default=sa.func.now()),
        )
        op.create_index("ix_lotes_usuario_id", "lotes", ["usuario_id"])
    else:
        cols = [c["name"] for c in inspector.get_columns("lotes")]
        if "credencial_id" not in cols:
            op.add_column("lotes", sa.Column("credencial_id", postgresql.UUID(as_uuid=True),
                          sa.ForeignKey("credenciais.id"), nullable=True))

    # ── consultas ─────────────────────────────────────────────────────────────
    if "consultas" not in existing:
        op.create_table(
            "consultas",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("lote_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lotes.id"), nullable=False),
            sa.Column("cpf", sa.String(14), nullable=False),
            sa.Column("nome_titular", sa.String(200)),
            sa.Column("orgao", sa.String(200)),
            sa.Column("tipo_vinculo", sa.String(100)),
            sa.Column("matricula", sa.String(50)),
            sa.Column("margem_disponivel", sa.Numeric(12, 2)),
            sa.Column("margem_cartao", sa.Numeric(12, 2)),
            sa.Column("margem_beneficio", sa.Numeric(12, 2)),
            sa.Column("emprestimo_situacao", sa.String(30)),
            sa.Column("cartao_credito_situacao", sa.String(30)),
            sa.Column("cartao_beneficio_situacao", sa.String(30)),
            sa.Column("banco", sa.String(100)),
            sa.Column("status_consulta", sa.String(20), server_default="aguardando"),
            sa.Column("mensagem_erro", sa.Text()),
            sa.Column("dados_brutos", sa.Text()),
            sa.Column("consultado_em", sa.DateTime()),
            sa.Column("criado_em", sa.DateTime(), default=sa.func.now()),
        )
        op.create_index("ix_consultas_lote_id", "consultas", ["lote_id"])
        op.create_index("ix_consultas_cpf", "consultas", ["cpf"])

    # ── refresh_tokens ────────────────────────────────────────────────────────
    if "refresh_tokens" not in existing:
        op.create_table(
            "refresh_tokens",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(255), unique=True, nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("criado_em", sa.DateTime(), default=sa.func.now()),
        )
        op.create_index("ix_refresh_tokens_usuario_id", "refresh_tokens", ["usuario_id"])

    # ── login_attempts ────────────────────────────────────────────────────────
    if "login_attempts" not in existing:
        op.create_table(
            "login_attempts",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("email", sa.String(200)),
            sa.Column("ip_address", sa.String(45), nullable=False),
            sa.Column("sucesso", sa.Boolean(), nullable=False),
            sa.Column("criado_em", sa.DateTime(), default=sa.func.now()),
        )
        op.create_index("ix_login_attempts_email", "login_attempts", ["email"])
        op.create_index("ix_login_attempts_ip", "login_attempts", ["ip_address"])
        op.create_index("ix_login_attempts_criado_em", "login_attempts", ["criado_em"])

    # ── audit_logs ────────────────────────────────────────────────────────────
    if "audit_logs" not in existing:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("acao", sa.String(64), nullable=False),
            sa.Column("tipo_entidade", sa.String(64)),
            sa.Column("id_entidade", postgresql.UUID(as_uuid=True)),
            sa.Column("detalhes", sa.JSON()),
            sa.Column("ip_address", sa.String(45)),
            sa.Column("user_agent", sa.Text()),
            sa.Column("criado_em", sa.DateTime(), default=sa.func.now()),
        )
        op.create_index("ix_audit_logs_usuario_id", "audit_logs", ["usuario_id"])
        op.create_index("ix_audit_logs_acao", "audit_logs", ["acao"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("login_attempts")
    op.drop_table("refresh_tokens")
    op.drop_table("consultas")
    op.drop_table("lotes")
    op.drop_table("credenciais")
    op.drop_table("usuarios")
