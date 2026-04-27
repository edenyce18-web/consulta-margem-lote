from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    from app import models  # noqa: F401 — garante que models são importados
    Base.metadata.create_all(bind=engine)


def ensure_indexes():
    """
    T4: Cria índices de performance com IF NOT EXISTS — seguro para rodar a cada startup.
    Garante que índices existam mesmo em bancos criados antes desta versão.
    """
    from sqlalchemy import text
    stmts = [
        # Índice simples em consultado_em (para aggregation por dia no dashboard)
        "CREATE INDEX IF NOT EXISTS ix_consultas_consultado_em ON consultas (consultado_em)",
        # Índice composto (lote_id, cpf) — padrão de busca em buscar_consulta_por_cpf
        "CREATE INDEX IF NOT EXISTS ix_consultas_lote_cpf ON consultas (lote_id, cpf)",
        # Índice em lotes.usuario_id (já no model, mas garante para DBs antigos)
        "CREATE INDEX IF NOT EXISTS ix_lotes_usuario_id ON lotes (usuario_id)",
        # Índice em lotes.criado_em — ORDER BY em listar_lotes
        "CREATE INDEX IF NOT EXISTS ix_lotes_criado_em ON lotes (criado_em DESC)",
    ]
    with engine.connect() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass  # índice já existe ou tabela ainda não criada
        conn.commit()
