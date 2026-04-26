import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# ── Senha ─────────────────────────────────────────────────────────────────────

def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verificar_senha(senha: str, hash_: str) -> bool:
    return pwd_context.verify(senha, hash_)


# ── Access Token (JWT curto) ──────────────────────────────────────────────────

def criar_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decodificar_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


# ── Refresh Token ─────────────────────────────────────────────────────────────

def gerar_refresh_token() -> str:
    """Gera um token aleatório seguro (256 bits)."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Armazena apenas o hash SHA-256 do refresh token."""
    return hashlib.sha256(token.encode()).hexdigest()


def criar_refresh_token_db(
    db: Session, usuario_id
) -> str:
    from app import crud
    token_raw = gerar_refresh_token()
    token_hash = hash_refresh_token(token_raw)
    expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    crud.criar_refresh_token(db, usuario_id, token_hash, expires_at)
    return token_raw


# ── Usuário atual ─────────────────────────────────────────────────────────────

def get_usuario_atual(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[models.Usuario]:
    if not token:
        return None
    payload = decodificar_token(token)
    if not payload:
        return None
    email: str = payload.get("sub")
    if not email:
        return None
    return db.query(models.Usuario).filter(models.Usuario.email == email).first()


def exigir_autenticacao(
    usuario: Optional[models.Usuario] = Depends(get_usuario_atual),
) -> models.Usuario:
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado. Faça login para continuar.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not usuario.ativo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta desativada.",
        )
    return usuario


# ── Rate Limiting ─────────────────────────────────────────────────────────────

def verificar_rate_limit(db: Session, email: str, ip: str) -> None:
    """
    Lança HTTPException 429 se o email ou IP tiver muitas tentativas falhas recentes.
    """
    from app import crud
    falhas = crud.contar_falhas_recentes(db, email, ip)
    if falhas >= settings.LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Muitas tentativas de login falhas. "
                f"Tente novamente em {settings.LOGIN_LOCKOUT_MINUTES} minutos."
            ),
        )


def get_ip(request: Request) -> str:
    """Extrai IP real do request (suporte a proxy reverso)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
