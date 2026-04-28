"""
main.py — Aplicação FastAPI principal.
"""

import io
import uuid
import logging
from typing import Optional, List

import pandas as pd
from fastapi import (
    FastAPI, Depends, HTTPException, UploadFile, File,
    status, Query, Request, Response
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db, create_tables, ensure_indexes
from app import crud, models, schemas
from app.auth import (
    hash_senha, verificar_senha,
    criar_access_token, criar_refresh_token_db,
    hash_refresh_token,
    get_usuario_atual, exigir_autenticacao,
    verificar_rate_limit, get_ip,
)
from app.crypto import encrypt, decrypt
from app.config import settings
from app.tasks import processar_lote
from app.scraper import listar_adaptadores

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ConsultaMargem — API",
    description="Sistema multi-usuário de consulta em lote de margem consignada.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

_ALLOWED_ORIGINS = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=3600,
)


@app.on_event("startup")
def on_startup():
    import time as _time
    from sqlalchemy import inspect as sa_inspect
    from app.database import engine

    # Avisa sobre configurações padrão inseguras
    if "TROQUE" in settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        logger.warning(
            "SECRET_KEY parece ser o valor padrão. "
            "Gere uma chave segura: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    if "TROQUE" in settings.ENCRYPTION_KEY:
        logger.warning(
            "ENCRYPTION_KEY parece ser o valor padrão. "
            "Gere com: python -c \"import os, base64; print(base64.b64encode(os.urandom(32)).decode())\""
        )

    max_tentativas = 10
    for tentativa in range(1, max_tentativas + 1):
        try:
            logger.info("Verificando schema do banco de dados... (tentativa %d/%d)", tentativa, max_tentativas)
            create_tables()
            ensure_indexes()

            inspector = sa_inspect(engine)
            tabelas_existentes = set(inspector.get_table_names())
            tabelas_necessarias = {
                "usuarios", "lotes", "consultas",
                "refresh_tokens", "login_attempts", "audit_logs", "credenciais",
            }
            faltando = tabelas_necessarias - tabelas_existentes
            if faltando:
                logger.warning("Tabelas faltando (execute alembic upgrade head): %s", faltando)
            else:
                logger.info("Todas as tabelas verificadas com sucesso.")
            return
        except Exception as e:
            if tentativa < max_tentativas:
                logger.warning(
                    "Banco não disponível (tentativa %d/%d): %s. Aguardando 3s...",
                    tentativa, max_tentativas, e,
                )
                _time.sleep(3)
            else:
                logger.error(
                    "Não foi possível conectar ao banco após %d tentativas. "
                    "Verifique DATABASE_URL e se o PostgreSQL está rodando.",
                    max_tentativas,
                )


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
def login(payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = get_ip(request)
    logger.info("Tentativa de login: email=%s ip=%s", payload.email, ip)

    try:
        # Rate limiting
        verificar_rate_limit(db, payload.email, ip)

        usuario = db.query(models.Usuario).filter(models.Usuario.email == payload.email).first()
        sucesso = bool(usuario and verificar_senha(payload.senha, usuario.senha_hash))

        crud.registrar_tentativa_login(
            db,
            email=payload.email,
            ip_address=ip,
            sucesso=sucesso,
            usuario_id=usuario.id if usuario else None,
        )

        if not sucesso:
            logger.warning("Login falhou (credenciais inválidas): email=%s", payload.email)
            raise HTTPException(status_code=401, detail="Credenciais inválidas.")

        if not usuario.ativo:
            logger.warning("Login bloqueado (conta inativa): email=%s", payload.email)
            raise HTTPException(status_code=403, detail="Conta desativada.")

        access_token = criar_access_token({"sub": usuario.email})
        refresh_token = criar_refresh_token_db(db, usuario.id)

        crud.registrar_auditoria(
            db, usuario.id, "login",
            ip_address=ip,
            user_agent=request.headers.get("user-agent"),
        )

        logger.info("Login bem-sucedido: email=%s id=%s", usuario.email, usuario.id)
        return {"access_token": access_token, "refresh_token": refresh_token}

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Erro interno no login para '%s': %s\n"
            "Verifique: 1) Banco inicializado (python init_db.py) "
            "2) SECRET_KEY configurada no .env "
            "3) ENCRYPTION_KEY com 32 bytes válidos",
            payload.email, exc,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "Erro interno no servidor. Verifique os logs do backend. "
                "Causas comuns: banco não inicializado, SECRET_KEY ou ENCRYPTION_KEY inválidos."
            ),
        )


@app.post("/auth/refresh", response_model=schemas.Token, tags=["Auth"])
def refresh_token(payload: schemas.RefreshRequest, db: Session = Depends(get_db)):
    token_hash = hash_refresh_token(payload.refresh_token)
    rt = crud.buscar_refresh_token(db, token_hash)
    if not rt:
        raise HTTPException(status_code=401, detail="Refresh token inválido ou expirado.")

    usuario = db.query(models.Usuario).filter(models.Usuario.id == rt.usuario_id).first()
    if not usuario or not usuario.ativo:
        raise HTTPException(status_code=401, detail="Usuário não encontrado.")

    # Rotação completa: revoga o antigo e emite novo refresh token
    crud.revogar_refresh_token(db, token_hash)
    novo_refresh = criar_refresh_token_db(db, usuario.id)
    access_token = criar_access_token({"sub": usuario.email})

    return {"access_token": access_token, "refresh_token": novo_refresh}


@app.post("/auth/logout", tags=["Auth"])
def logout(
    payload: schemas.RefreshRequest,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(exigir_autenticacao),
):
    token_hash = hash_refresh_token(payload.refresh_token)
    crud.revogar_refresh_token(db, token_hash)
    return {"mensagem": "Logout realizado com sucesso."}


@app.get("/auth/me", response_model=schemas.UsuarioResponse, tags=["Auth"])
def me(usuario: models.Usuario = Depends(exigir_autenticacao)):
    return usuario


# ── Credenciais ───────────────────────────────────────────────────────────────

@app.get("/credenciais/", response_model=List[schemas.CredencialResponse], tags=["Credenciais"])
def listar_credenciais(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(exigir_autenticacao),
):
    return crud.listar_credenciais(db, usuario.id)


@app.post("/credenciais/", response_model=schemas.CredencialResponse, status_code=201, tags=["Credenciais"])
def criar_credencial(
    payload: schemas.CredencialCreate,
    request: Request,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(exigir_autenticacao),
):
    if payload.tipo_instituicao not in listar_adaptadores():
        raise HTTPException(
            status_code=400,
            detail=f"Tipo inválido. Disponíveis: {', '.join(listar_adaptadores())}",
        )

    login_enc = encrypt(payload.login, settings.ENCRYPTION_KEY)
    senha_enc = encrypt(payload.senha, settings.ENCRYPTION_KEY)
    url_enc   = encrypt(payload.url, settings.ENCRYPTION_KEY) if payload.url else None

    cred = crud.criar_credencial(
        db,
        usuario_id=usuario.id,
        nome=payload.nome,
        tipo_instituicao=payload.tipo_instituicao,
        login_enc=login_enc,
        senha_enc=senha_enc,
        url_enc=url_enc,
    )

    crud.registrar_auditoria(
        db, usuario.id, "credential_create",
        tipo_entidade="credencial", id_entidade=cred.id,
        detalhes={"nome": payload.nome, "tipo": payload.tipo_instituicao},
        ip_address=get_ip(request),
    )

    return cred


@app.put("/credenciais/{credencial_id}", response_model=schemas.CredencialResponse, tags=["Credenciais"])
def atualizar_credencial(
    credencial_id: uuid.UUID,
    payload: schemas.CredencialUpdate,
    request: Request,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(exigir_autenticacao),
):
    dados = {}
    if payload.nome is not None:
        dados["nome"] = payload.nome
    if payload.login is not None:
        dados["login_enc"] = encrypt(payload.login, settings.ENCRYPTION_KEY)
    if payload.senha is not None:
        dados["senha_enc"] = encrypt(payload.senha, settings.ENCRYPTION_KEY)
    if payload.url is not None:
        dados["url_enc"] = encrypt(payload.url, settings.ENCRYPTION_KEY)

    cred = crud.atualizar_credencial(db, credencial_id, usuario.id, dados)
    if not cred:
        raise HTTPException(status_code=404, detail="Credencial não encontrada.")

    crud.registrar_auditoria(
        db, usuario.id, "credential_update",
        tipo_entidade="credencial", id_entidade=credencial_id,
        ip_address=get_ip(request),
    )

    return cred


@app.delete("/credenciais/{credencial_id}", tags=["Credenciais"])
def deletar_credencial(
    credencial_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(exigir_autenticacao),
):
    ok = crud.deletar_credencial(db, credencial_id, usuario.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Credencial não encontrada.")

    crud.registrar_auditoria(
        db, usuario.id, "credential_delete",
        tipo_entidade="credencial", id_entidade=credencial_id,
        ip_address=get_ip(request),
    )

    return {"mensagem": "Credencial removida com sucesso."}


# ── Lotes ──────────────────────────────────────────────────────────────────────

@app.post(
    "/upload-lote/",
    response_model=schemas.UploadLoteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Lotes"],
)
async def upload_lote(
    arquivo: UploadFile = File(..., description="Arquivo CSV com coluna 'cpf'"),
    banco: str = Query(default="aki", description="Adaptador: aki | grid | exemplo"),
    credencial_id: Optional[uuid.UUID] = Query(default=None, description="ID da credencial a usar"),
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(exigir_autenticacao),
):
    if not arquivo.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Apenas arquivos .csv são aceitos.")

    # Valida credencial se informada
    if credencial_id:
        cred = crud.buscar_credencial_por_id(db, credencial_id)
        if not cred or cred.usuario_id != usuario.id:
            raise HTTPException(status_code=403, detail="Credencial não encontrada ou não pertence a você.")
        banco = cred.tipo_instituicao

    conteudo = await arquivo.read()
    try:
        # Auto-detecta separador: testa ; e , na primeira linha
        primeira_linha = conteudo.split(b"\n")[0].decode("utf-8", errors="replace")
        sep = ";" if primeira_linha.count(";") >= primeira_linha.count(",") else ","
        df = pd.read_csv(
            io.BytesIO(conteudo),
            dtype=str,
            sep=sep,
            on_bad_lines="skip",
            engine="python",
            encoding_errors="replace",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler CSV: {e}")

    df.columns = [c.strip().lower() for c in df.columns]

    # Aceita coluna 'cpf' ou primeira coluna se contiver CPFs sem cabeçalho padrão
    if "cpf" not in df.columns:
        primeira = df.columns[0]
        amostra = df[primeira].dropna().str.strip().str.replace(r"\D", "", regex=True)
        if amostra.str.len().between(10, 11).mean() > 0.5:
            df = df.rename(columns={primeira: "cpf"})
        else:
            raise HTTPException(
                status_code=400,
                detail="O CSV deve conter a coluna 'cpf'. Colunas encontradas: " + ", ".join(df.columns),
            )

    cpfs = df["cpf"].dropna().str.strip().str.replace(r"\D", "", regex=True).tolist()
    cpfs = [c for c in cpfs if c]

    if not cpfs:
        raise HTTPException(status_code=400, detail="Nenhum CPF válido encontrado no arquivo.")
    if len(cpfs) > 5000:
        raise HTTPException(status_code=400, detail="Limite de 5.000 CPFs por lote.")

    lote = crud.criar_lote(
        db,
        arquivo.filename,
        len(cpfs),
        banco_portal=banco,
        usuario_id=usuario.id,
        credencial_id=credencial_id,
    )
    crud.criar_consultas_em_lote(db, lote.id, cpfs)

    processar_lote.delay(
        str(lote.id),
        cpfs,
        banco,
        str(credencial_id) if credencial_id else None,
        str(usuario.id),
    )

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
    usuario: models.Usuario = Depends(exigir_autenticacao),
):
    lote = crud.buscar_lote(db, lote_id)
    if not lote:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    if lote.usuario_id and lote.usuario_id != usuario.id:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    consultas = crud.listar_consultas_lote(db, lote_id, skip=skip, limit=limit)
    progresso = (lote.processados / lote.total_cpfs * 100) if lote.total_cpfs else 0

    return schemas.LoteDetalheResponse(
        id=lote.id,
        arquivo_original=lote.arquivo_original,
        banco_portal=lote.banco_portal,
        credencial_id=lote.credencial_id,
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
    usuario: models.Usuario = Depends(exigir_autenticacao),
):
    lotes = crud.listar_lotes(db, usuario_id=usuario.id, skip=skip, limit=limit)
    resultado = []
    for lote in lotes:
        progresso = (lote.processados / lote.total_cpfs * 100) if lote.total_cpfs else 0
        resultado.append(
            schemas.LoteResponse(
                id=lote.id,
                arquivo_original=lote.arquivo_original,
                banco_portal=lote.banco_portal,
                credencial_id=lote.credencial_id,
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


# ── Exportação ────────────────────────────────────────────────────────────────

@app.get("/lotes/{lote_id}/exportar", tags=["Lotes"])
def exportar_lote(
    lote_id: uuid.UUID,
    formato: str = Query(default="csv", description="csv | xlsx"),
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(exigir_autenticacao),
):
    lote = crud.buscar_lote(db, lote_id)
    if not lote:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    if lote.usuario_id and lote.usuario_id != usuario.id:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    consultas = crud.listar_consultas_lote(db, lote_id, limit=10000)

    rows = []
    for c in consultas:
        rows.append({
            "CPF": c.cpf,
            "Nome": c.nome_titular or "",
            "Órgão": c.orgao or "",
            "Matrícula": c.matricula or "",
            "Tipo Vínculo": c.tipo_vinculo or "",
            "Margem Disponível (R$)": float(c.margem_disponivel) if c.margem_disponivel else "",
            "Margem Cartão (R$)": float(c.margem_cartao) if c.margem_cartao else "",
            "Margem Benefício (R$)": float(c.margem_beneficio) if c.margem_beneficio else "",
            "Empréstimo": c.emprestimo_situacao or "",
            "Cartão Crédito": c.cartao_credito_situacao or "",
            "Cartão Benefício": c.cartao_beneficio_situacao or "",
            "Banco": c.banco or "",
            "Status": c.status_consulta.value if c.status_consulta else "",
            "Erro": c.mensagem_erro or "",
            "Data Consulta": c.consultado_em.strftime("%Y-%m-%d %H:%M:%S") if c.consultado_em else "",
        })

    df = pd.DataFrame(rows)

    if formato == "xlsx":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Resultados")
        buf.seek(0)
        filename = f"lote_{lote_id}_resultados.xlsx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    else:
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        buf.seek(0)
        filename = f"lote_{lote_id}_resultados.csv"
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/dashboard/", response_model=schemas.DashboardStats, tags=["Dashboard"])
def dashboard(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(exigir_autenticacao),
):
    stats = crud.stats_usuario(db, usuario.id)
    lotes_recentes = crud.listar_lotes(db, usuario_id=usuario.id, limit=5)
    lotes_response = []
    for lote in lotes_recentes:
        progresso = (lote.processados / lote.total_cpfs * 100) if lote.total_cpfs else 0
        lotes_response.append(
            schemas.LoteResponse(
                id=lote.id,
                arquivo_original=lote.arquivo_original,
                banco_portal=lote.banco_portal,
                credencial_id=lote.credencial_id,
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
    return schemas.DashboardStats(
        **stats,
        lotes_recentes=lotes_response,
    )


# ── Catálogo ──────────────────────────────────────────────────────────────────

_BANCOS_CATALOGO = [
    {
        "id": "aki",
        "nome": "AkiCapital",
        "descricao": "Plataforma AkiCapital para consulta de margem consignada via WebAutorizador.",
        "status": "ativo",
        "margem_maxima": "R$ 5.000,00",
        "taxa_media": "1,89% a.m.",
    },
    {
        "id": "grid",
        "nome": "GridSoftware",
        "descricao": "Portal GridSoftware para consulta de margem consignada.",
        "status": "ativo",
        "margem_maxima": "R$ 4.500,00",
        "taxa_media": "2,05% a.m.",
    },
    {
        "id": "exemplo",
        "nome": "Exemplo (Demo)",
        "descricao": "Adaptador de demonstração com dados simulados para testes.",
        "status": "demo",
        "margem_maxima": "—",
        "taxa_media": "—",
    },
]


@app.get("/catalogo/bancos", tags=["Catálogo"])
def catalogo_bancos():
    return _BANCOS_CATALOGO


# ── Sistema ───────────────────────────────────────────────────────────────────

@app.get("/adaptadores/", tags=["Sistema"])
def listar_portais():
    return {"adaptadores": listar_adaptadores()}


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok", "versao": "2.0.0"}


@app.get("/health/db", tags=["Sistema"])
def health_db(db: Session = Depends(get_db)):
    """Diagnóstico: testa conectividade com o banco de dados."""
    try:
        from sqlalchemy import text, inspect
        db.execute(text("SELECT 1"))
        tabelas = [
            "usuarios", "credenciais", "lotes",
            "consultas", "refresh_tokens", "login_attempts", "audit_logs",
        ]
        existentes = []
        faltando = []
        insp = inspect(db.bind)
        for tabela in tabelas:
            if insp.has_table(tabela):
                existentes.append(tabela)
            else:
                faltando.append(tabela)

        ok = len(faltando) == 0
        return {
            "status": "ok" if ok else "degradado",
            "banco": "conectado",
            "tabelas_existentes": existentes,
            "tabelas_faltando": faltando,
            "acao": (
                None if ok
                else "Execute: docker exec -it margem_backend python init_db.py"
            ),
        }
    except Exception as exc:
        logger.exception("Falha no health check do banco: %s", exc)
        return {
            "status": "erro",
            "banco": "desconectado",
            "detalhe": str(exc),
            "acao": "Verifique DATABASE_URL no .env e se o PostgreSQL está rodando.",
        }
