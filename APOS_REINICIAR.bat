@echo off
chcp 65001 >nul
title ConsultaMargem — Iniciando apos reinicio

echo Aguardando Docker Desktop carregar...

:aguarda_docker
timeout /t 5 /nobreak >nul
docker info >nul 2>&1
if errorlevel 1 goto aguarda_docker

echo Docker pronto! Subindo o sistema...
cd /d "C:\Users\edeny\consulta-margem-lote"
docker compose up --build -d

timeout /t 8 /nobreak >nul
start "" http://localhost
start "" http://localhost:8000/docs

echo.
echo Sistema no ar! Abrindo navegador...
pause
