@echo off
chcp 65001 >nul

:: Auto-elevação para Administrador
net session >nul 2>&1
if errorlevel 1 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

title ConsultaMargem — Iniciando Sistema

echo.
echo ============================================
echo   SISTEMA DE CONSULTA DE MARGEM EM LOTE
echo ============================================
echo.

:: 1) Inicia o serviço do Docker Engine
echo [1/4] Iniciando servico Docker Engine...
net start com.docker.service >nul 2>&1
if errorlevel 1 (
    echo     Servico ja rodando ou nao encontrado, continuando...
)
echo     OK!

:: 2) Aguarda o Docker Desktop subir
echo [2/4] Aguardando Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
timeout /t 20 /nobreak >nul

:aguarda_docker
docker info >nul 2>&1
if errorlevel 1 (
    echo     Ainda aguardando Docker Engine...
    timeout /t 5 /nobreak >nul
    goto aguarda_docker
)
echo     Docker pronto!

:: 3) Sobe os containers
echo [3/4] Subindo containers (pode demorar na 1a vez)...
cd /d "C:\Users\edeny\consulta-margem-lote"
docker compose up --build -d

if errorlevel 1 (
    echo ERRO ao subir containers!
    pause
    exit /b 1
)

echo     Containers no ar!

:: 4) Aguarda backend ficar pronto
echo [4/4] Aguardando backend (15s)...
timeout /t 15 /nobreak >nul

echo.
echo ============================================
echo   SISTEMA NO AR!
echo   http://localhost         - Interface
echo   http://localhost:8000/docs - API
echo   http://localhost:5555    - Celery Monitor
echo ============================================
echo.

start "" http://localhost
timeout /t 2 /nobreak >nul
start "" http://localhost:8000/docs

pause
