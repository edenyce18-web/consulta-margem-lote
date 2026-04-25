@echo off
chcp 65001 >nul
title ConsultaMargem — Parando Sistema

echo.
echo Parando todos os containers...
cd /d "%~dp0"
docker compose down

echo.
echo Sistema parado com sucesso.
pause
