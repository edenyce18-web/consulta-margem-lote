@echo off
chcp 65001 >nul
title ConsultaMargem — Logs em tempo real
cd /d "%~dp0"
echo Mostrando logs (Ctrl+C para parar)...
echo.
docker compose logs -f --tail=50
pause
