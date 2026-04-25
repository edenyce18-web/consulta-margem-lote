@echo off
chcp 65001 >nul

:: Solicita elevação para administrador automaticamente
net session >nul 2>&1
if errorlevel 1 (
    echo Solicitando permissao de Administrador...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

title ConsultaMargem — Sistema Iniciando (Admin)

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║     SISTEMA DE CONSULTA DE MARGEM EM LOTE       ║
echo ╚══════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: Verifica se Docker Desktop está rodando
docker info >nul 2>&1
if errorlevel 1 (
    echo [1/3] Docker nao esta rodando. Iniciando Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

    echo     Aguardando Docker Engine ficar pronto...
    :aguarda
    timeout /t 5 /nobreak >nul
    docker info >nul 2>&1
    if errorlevel 1 goto aguarda

    echo [OK] Docker Engine pronto!
    echo.
)

echo [2/3] Docker esta rodando!
echo.
echo [3/3] Construindo e subindo os containers...
echo       (primeira vez pode demorar 5-10 minutos)
echo.

docker compose up --build -d

if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao subir os containers.
    echo Verifique os logs com: docker compose logs
    pause
    exit /b 1
)

echo.
echo Aguardando servicos ficarem prontos (15s)...
timeout /t 15 /nobreak >nul

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║              SISTEMA NO AR!                     ║
echo ╠══════════════════════════════════════════════════╣
echo ║                                                  ║
echo ║  Interface Web:   http://localhost               ║
echo ║  API Swagger:     http://localhost:8000/docs     ║
echo ║  Monitor Celery:  http://localhost:5555          ║
echo ║                                                  ║
echo ╚══════════════════════════════════════════════════╝
echo.

start "" http://localhost
timeout /t 2 /nobreak >nul
start "" http://localhost:8000/docs

echo  Para VER os logs: docker compose logs -f
echo  Para PARAR:       docker compose down
echo.
pause
