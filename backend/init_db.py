"""
init_db.py — Script de inicialização do banco de dados.

Uso:
    # Apenas criar tabelas:
    python init_db.py

    # Criar tabelas + usuário admin:
    python init_db.py --admin-email admin@empresa.com --admin-senha MinhaS3nha!

    # Forçar recriação de todas as tabelas (APAGA DADOS):
    python init_db.py --drop-all

Executar dentro do container:
    docker exec -it margem_backend python init_db.py --admin-email admin@empresa.com --admin-senha MinhaS3nha!
"""

import argparse
import logging
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def aguardar_banco(engine, max_tentativas: int = 10, intervalo_s: int = 3) -> None:
    """Aguarda o banco de dados ficar disponível com retry."""
    from sqlalchemy import text

    logger.info("Aguardando banco de dados...")
    for tentativa in range(1, max_tentativas + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Banco de dados disponível.")
            return
        except Exception as exc:
            if tentativa < max_tentativas:
                logger.warning(
                    "Tentativa %d/%d falhou: %s. Aguardando %ds...",
                    tentativa, max_tentativas, exc, intervalo_s,
                )
                time.sleep(intervalo_s)
            else:
                logger.critical(
                    "Banco de dados não ficou disponível após %d tentativas.", max_tentativas
                )
                raise


def criar_tabelas(engine, drop_all: bool = False) -> None:
    """Cria todas as tabelas. Se drop_all=True, apaga e recria tudo."""
    from app.database import Base
    import app.models  # noqa: F401 — garante registro dos models

    if drop_all:
        logger.warning("DROP ALL ativado — todas as tabelas serão apagadas!")
        Base.metadata.drop_all(bind=engine)
        logger.info("Tabelas removidas.")

    Base.metadata.create_all(bind=engine)
    logger.info("Tabelas criadas/verificadas com sucesso.")


def criar_usuario_admin(db, email: str, senha: str, nome: str = "Admin") -> None:
    """Cria um usuário admin se não existir."""
    from app import models
    from app.auth import hash_senha

    existente = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if existente:
        logger.info("Usuário '%s' já existe — pulando criação.", email)
        return

    usuario = models.Usuario(
        nome=nome,
        email=email,
        senha_hash=hash_senha(senha),
        ativo=True,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    logger.info("Usuário admin criado: %s (ID: %s)", email, usuario.id)


def validar_configuracoes() -> None:
    """Verifica se as variáveis críticas foram trocadas dos valores padrão."""
    from app.config import settings

    avisos = []

    if "TROQUE" in settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        avisos.append(
            "SECRET_KEY parece ser o valor padrão ou muito curta. "
            "Gere com: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    if "TROQUE" in settings.ENCRYPTION_KEY:
        avisos.append(
            "ENCRYPTION_KEY parece ser o valor padrão. "
            "Gere com: python -c \"import os, base64; print(base64.b64encode(os.urandom(32)).decode())\""
        )

    if avisos:
        logger.warning("=" * 60)
        logger.warning("ATENÇÃO — Configurações inseguras detectadas:")
        for aviso in avisos:
            logger.warning("  • %s", aviso)
        logger.warning("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Inicializa o banco de dados do ConsultaMargem.")
    parser.add_argument("--admin-email", help="E-mail do usuário admin a criar")
    parser.add_argument("--admin-senha", help="Senha do usuário admin")
    parser.add_argument("--admin-nome", default="Admin", help="Nome do usuário admin (padrão: Admin)")
    parser.add_argument(
        "--drop-all",
        action="store_true",
        help="PERIGO: apaga e recria todas as tabelas",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ConsultaMargem — Inicialização do Banco de Dados")
    logger.info("=" * 60)

    # Valida configurações
    validar_configuracoes()

    # Importa e cria engine
    from app.database import engine, SessionLocal

    # Aguarda banco ficar disponível
    aguardar_banco(engine)

    # Cria tabelas
    criar_tabelas(engine, drop_all=args.drop_all)

    # Cria usuário admin se solicitado
    if args.admin_email:
        if not args.admin_senha:
            logger.error("--admin-senha é obrigatório quando --admin-email é fornecido.")
            sys.exit(1)

        db = SessionLocal()
        try:
            criar_usuario_admin(db, args.admin_email, args.admin_senha, args.admin_nome)
        finally:
            db.close()
    else:
        logger.info(
            "Nenhum usuário admin solicitado. Para criar, use:\n"
            "  python init_db.py --admin-email admin@empresa.com --admin-senha MinhaS3nha!"
        )

    logger.info("=" * 60)
    logger.info("Inicialização concluída com sucesso!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
