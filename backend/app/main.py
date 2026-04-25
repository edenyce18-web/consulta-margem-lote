"""
main.py — Aplicação FastAPI principal.
"""

import io
import uuid
import logging
from typing import Optional, List
from fastapi import (
    FastAPI, Depends, HTTPException, UploadFile, File,
    status, Query
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import pandas as pd

from app.database import get_db, create_tables
from app import crud, models, schemas
from app.auth import (
    hash_senha, verificar_senha, criar_token,
    get_usuario_atual, exigir_autenticacao,
)
from app.tasks import processar_lote
from app.scraper import listar_adaptadores

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Consulta Margem Consignada — API",
    description="Sistema de consulta em lote de margem consignada via scraping/API de portais bancários.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Em produção: especifique domínios
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    create_tables()
    logger.info("Tabelas verificadas/criadas.")


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/auth/registrar", response_model=schemas.UsuarioResponse, tags=["Auth"])
def registrar(payload: schemas.UsuarioCreate, db: Session = Depends(get_db)):
    if db.query(models.Usuario).filter(models.Usuario.email == payload.email).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")
    usuario = models.Usuario(
        nome=payload.nome,
        email=payload.email,
        senha_hash=hash_senha(payload.senha),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@app.post("/auth/login", response_model=schemas.Token, tags=["Auth"])
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(models.Usuario.email == payload.email).first()
    if not usuario or not verificar_senha(payload.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")
    token = criar_token({"sub": usuario.email})
    return {"access_token": token}


@app.post("/auth/token", response_model=schemas.Token, tags=["Auth"], include_in_schema=False)
def login_form(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Compatibilidade com OAuth2PasswordBearer do Swagger UI."""
    usuario = db.query(models.Usuario).filter(models.Usuario.email == form.username).first()
    if not usuario or not verificar_senha(form.password, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")
    token = criar_token({"sub": usuario.email})
    return {"access_token": token}


@app.get("/auth/me", response_model=schemas.UsuarioResponse, tags=["Auth"])
def me(usuario: models.Usuario = Depends(exigir_autenticacao)):
    return usuario


# ── Lotes ──────────────────────────────────────────────────────────────────────

@app.post(
    "/upload-lote/",
    response_model=schemas.UploadLoteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Lotes"],
)
async def upload_lote(
    arquivo: UploadFile = File(..., description="Arquivo CSV com coluna 'cpf'"),
    banco: str = Query(default="exemplo", description="Adaptador: exemplo | bb | cef"),
    db: Session = Depends(get_db),
    usuario: Optional[models.Usuario] = Depends(get_usuario_atual),
):
    """
    Recebe CSV com coluna **cpf**, cria lote no banco e dispara processamento assíncrono.
    """
    if not arquivo.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Apenas arquivos .csv são aceitos.")

    conteudo = await arquivo.read()

    try:
        df = pd.read_csv(io.BytesIO(conteudo), dtype=str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler CSV: {e}")

    df.columns = [c.strip().lower() for c in df.columns]

    if "cpf" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail="O CSV deve conter a coluna 'cpf'. Colunas encontradas: " + ", ".join(df.columns),
        )

    cpfs = df["cpf"].dropna().str.strip().str.replace(r"\D", "", regex=True).tolist()
    cpfs = [c for c in cpfs if c]  # remove vazios

    if not cpfs:
        raise HTTPException(status_code=400, detail="Nenhum CPF válido encontrado no arquivo.")

    if len(cpfs) > 5000:
        raise HTTPException(status_code=400, detail="Limite de 5.000 CPFs por lote.")

    usuario_id = usuario.id if usuario else None
    lote = crud.criar_lote(db, arquivo.filename, len(cpfs), banco_portal=banco, usuario_id=usuario_id)
    crud.criar_consultas_em_lote(db, lote.id, cpfs)

    # Dispara tarefa Celery de forma assíncrona
    processar_lote.delay(str(lote.id), cpfs, banco)

    return schemas.UploadLoteResponse(
        lote_id=lote.id,
        mensagem=f"Lote aceito. {len(cpfs)} CPFs em processamento.",
        total_cpfs=len(cpfs),
    )


@app.get("/status-lote/{lote_id}", response_model=schemas.LoteDetalheResponse, tags=["Lotes"])
def status_lote(
    lote_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Retorna status atual do lote e resultados parciais/finais.
    Use `skip` e `limit` para paginar as consultas.
    """
    lote = crud.buscar_lote(db, lote_id)
    if not lote:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")

    consultas = crud.listar_consultas_lote(db, lote_id, skip=skip, limit=limit)

    progresso = (lote.processados / lote.total_cpfs * 100) if lote.total_cpfs else 0

    return schemas.LoteDetalheResponse(
        id=lote.id,
        arquivo_original=lote.arquivo_original,
        total_cpfs=lote.total_cpfs,
        processados=lote.processados,
        sucessos=lote.sucessos,
        erros=lote.erros,
        status=lote.status.value,
        mensagem_erro=lote.mensagem_erro,
        criado_em=lote.criado_em,
        atualizado_em=lote.atualizado_em,
        progresso_pct=round(progresso, 1),
        consultas=consultas,
    )


@app.get("/lotes/", response_model=List[schemas.LoteResponse], tags=["Lotes"])
def listar_lotes(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    usuario: Optional[models.Usuario] = Depends(get_usuario_atual),
):
    usuario_id = usuario.id if usuario else None
    lotes = crud.listar_lotes(db, usuario_id=usuario_id, skip=skip, limit=limit)
    resultado = []
    for lote in lotes:
        progresso = (lote.processados / lote.total_cpfs * 100) if lote.total_cpfs else 0
        resultado.append(
            schemas.LoteResponse(
                id=lote.id,
                arquivo_original=lote.arquivo_original,
                banco_portal=lote.banco_portal,
                total_cpfs=lote.total_cpfs,
                processados=lote.processados,
                sucessos=lote.sucessos,
                erros=lote.erros,
                status=lote.status.value,
                mensagem_erro=lote.mensagem_erro,
                criado_em=lote.criado_em,
                atualizado_em=lote.atualizado_em,
                progresso_pct=round(progresso, 1),
            )
        )
    return resultado


@app.get("/adaptadores/", tags=["Sistema"])
def listar_portais():
    """
    Retorna a lista de adaptadores de portal disponíveis.
    Use a chave retornada no parâmetro `banco` do endpoint `/upload-lote/`.
    """
    return {"adaptadores": listar_adaptadores()}


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok", "versao": "1.0.0"}
