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
echo [1/3] Entrando na pasta do projeto...
cd /d "%~dp0"

echo [2/3] Construindo e subindo os containers...
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
echo [3/3] Aguardando servicos ficarem prontos...
timeout /t 10 /nobreak >nul

:: Abre o navegador automaticamente
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║              SISTEMA NO AR!                     ║
echo ╠══════════════════════════════════════════════════╣
echo ║                                                  ║
echo ║  Interface Web:   http://localhost               ║
echo ║  API Swagger:     http://localhost:8000/docs     ║
echo ║  Monitor Celery:  http://localhost:5555          ║
echo ║                                                  ║
echo ║  Abrindo navegador...                            ║
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
