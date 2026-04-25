@echo off
chcp 65001 >nul
title Corrigindo Docker — Executando como Administrador

:: Verifica se está rodando como admin
net session >nul 2>&1
if errorlevel 1 (
    echo Solicitando permissao de administrador...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║        ATIVANDO RECURSOS PARA O DOCKER          ║
echo ╚══════════════════════════════════════════════════╝
echo.

echo [1/4] Ativando WSL (Subsistema Linux do Windows)...
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
echo.

echo [2/4] Ativando Virtual Machine Platform...
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
echo.

echo [3/4] Baixando e instalando kernel do WSL 2...
powershell -Command "Invoke-WebRequest -Uri 'https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi' -OutFile '%TEMP%\wsl_update.msi' -UseBasicParsing"
msiexec /i "%TEMP%\wsl_update.msi" /quiet /norestart
echo.

echo [4/4] Definindo WSL 2 como versao padrao...
wsl --set-default-version 2
echo.

echo ╔══════════════════════════════════════════════════╗
echo ║                  PRONTO!                        ║
echo ╠══════════════════════════════════════════════════╣
echo ║                                                  ║
echo ║  REINICIE O COMPUTADOR agora.                   ║
echo ║                                                  ║
echo ║  Depois de reiniciar:                           ║
echo ║  1. Abra o Docker Desktop Installer.exe         ║
echo ║     (esta na pasta Downloads)                   ║
echo ║  2. Instale normalmente                         ║
echo ║  3. Clique em INICIAR.bat na pasta do projeto   ║
echo ║                                                  ║
echo ╚══════════════════════════════════════════════════╝
echo.

set /p reiniciar=Deseja reiniciar agora? (S/N):
if /i "%reiniciar%"=="S" shutdown /r /t 5 /c "Reiniciando para ativar WSL 2..."

pause
