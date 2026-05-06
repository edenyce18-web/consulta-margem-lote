@echo off
chcp 65001 >nul
title ConsultaMargem — Iniciando apos reinicio

echo Aguardando Docker Desktop carregar...

:aguarda_docker
timeout /t 5 /nobreak >nul
docker info >nul 2>&1
if errorlevel 1 goto aguarda_docker

echo Docker pronto!

REM ── Verifica se .env existe ───────────────────────────────────────────────
set ENV_FILE=%~dp0backend\.env
if not exist "%ENV_FILE%" (
    echo.
    echo [AVISO] Arquivo .env nao encontrado em backend\.env
    echo Copiando .env.example para .env...
    copy "%~dp0backend\.env.example" "%ENV_FILE%" >nul
    echo.
    echo [IMPORTANTE] Edite o arquivo backend\.env e configure:
    echo   - SECRET_KEY (gere com: python -c "import secrets; print(secrets.token_hex(32))")
    echo   - ENCRYPTION_KEY (gere com: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())")
    echo   - AKICAPITAL_LOGIN, AKICAPITAL_SENHA (credenciais do portal)
    echo   - GRID_LOGIN, GRID_SENHA (credenciais Grid/Roraima)
    echo.
    pause
)

echo Subindo o sistema...
cd /d "%~dp0"
docker compose up --build -d

echo Aguardando banco de dados inicializar...
timeout /t 15 /nobreak >nul

echo Inicializando banco de dados...
docker exec margem_backend python init_db.py

echo.
echo Verificando saude do sistema...
timeout /t 5 /nobreak >nul
start "" http://localhost:8000/health/db
start "" http://localhost
start "" http://localhost:8000/docs

echo.
echo Sistema no ar!
echo   Frontend: http://localhost
echo   API Docs: http://localhost:8000/docs
echo   Health:   http://localhost:8000/health/db
echo   Flower:   http://localhost:5555
echo.
echo Para criar usuario admin:
echo   docker exec -it margem_backend python init_db.py --admin-email admin@empresa.com --admin-senha MinhaS3nha!
echo.
pause
