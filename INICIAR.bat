@echo off
chcp 65001 >nul
title ConsultaMargem — Iniciando Sistema

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║     SISTEMA DE CONSULTA DE MARGEM EM LOTE       ║
echo ╚══════════════════════════════════════════════════╝
echo.

:: Verifica se Docker está disponível
docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Docker não encontrado.
    echo.
    echo  Siga estes passos:
    echo  1. Va ate sua pasta Downloads
    echo  2. Execute o arquivo "Docker Desktop Installer.exe"
    echo  3. Siga a instalacao e REINICIE o computador
    echo  4. Abra o Docker Desktop e aguarde o icone verde
    echo  5. Execute este arquivo novamente
    echo.
    pause
    exit /b 1
)

:: Verifica se Docker Engine está rodando
docker info >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Docker instalado mas nao esta rodando.
    echo  Abrindo Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe" 2>nul
    echo.
    echo  Aguarde o Docker Desktop iniciar completamente
    echo  ^(icone na bandeja do sistema ficar verde^)
    echo  e execute este arquivo novamente.
    echo.
    pause
    exit /b 1
)

echo [OK] Docker esta rodando!
echo.
echo [1/4] Entrando na pasta do projeto...
cd /d "%~dp0"

:: Verifica se .env existe
if not exist "backend\.env" (
    echo.
    echo [AVISO] Arquivo backend\.env nao encontrado!
    echo Copiando .env.example para .env...
    copy "backend\.env.example" "backend\.env" >nul
    echo.
    echo ╔══════════════════════════════════════════════════════════════╗
    echo ║  CONFIGURACAO NECESSARIA — Edite o arquivo backend\.env     ║
    echo ╠══════════════════════════════════════════════════════════════╣
    echo ║                                                              ║
    echo ║  SECRET_KEY: gere com:                                       ║
    echo ║    python -c "import secrets; print(secrets.token_hex(32))" ║
    echo ║                                                              ║
    echo ║  ENCRYPTION_KEY: gere com:                                   ║
    echo ║    python -c "import os,base64;                              ║
    echo ║      print(base64.b64encode(os.urandom(32)).decode())"      ║
    echo ║                                                              ║
    echo ║  AKICAPITAL_LOGIN, AKICAPITAL_SENHA: credenciais AkiCapital ║
    echo ║  GRID_LOGIN, GRID_SENHA: credenciais GridSoftware/Roraima   ║
    echo ║                                                              ║
    echo ╚══════════════════════════════════════════════════════════════╝
    echo.
    notepad "backend\.env"
    echo Pressione qualquer tecla apos configurar o .env...
    pause >nul
)

echo [2/4] Construindo e subindo os containers...
echo       ^(primeira vez pode demorar 5-10 minutos^)
echo.
docker compose up --build -d

if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao subir os containers.
    echo  Verifique os logs com: docker compose logs
    pause
    exit /b 1
)

echo.
echo [3/4] Aguardando banco de dados ficar pronto...
timeout /t 15 /nobreak >nul

echo [4/4] Inicializando banco de dados...
docker exec margem_backend python init_db.py
if errorlevel 1 (
    echo [AVISO] init_db retornou erro - o banco pode ja estar inicializado.
)

:: Abre o navegador automaticamente
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║              SISTEMA NO AR!                     ║
echo ╠══════════════════════════════════════════════════╣
echo ║                                                  ║
echo ║  Interface Web:   http://localhost               ║
echo ║  API Swagger:     http://localhost:8000/docs     ║
echo ║  Monitor Celery:  http://localhost:5555          ║
echo ║  Saude do BD:     http://localhost:8000/health/db║
echo ║                                                  ║
echo ║  Para criar usuario admin:                       ║
echo ║  docker exec -it margem_backend python           ║
echo ║    init_db.py --admin-email x@y.com              ║
echo ║               --admin-senha SuaSenha123          ║
echo ║                                                  ║
echo ╚══════════════════════════════════════════════════╝
echo.

start "" http://localhost
timeout /t 2 /nobreak >nul
start "" http://localhost:8000/docs

echo  Para VER os logs em tempo real, execute:
echo    docker compose logs -f
echo.
echo  Para PARAR o sistema, execute:
echo    docker compose down
echo.
pause
