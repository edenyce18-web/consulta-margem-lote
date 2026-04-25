@echo off
chcp 65001 >nul
title Corrigindo permissao Docker

:: Garante execucao como admin
net session >nul 2>&1
if errorlevel 1 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo [1/4] Removendo pasta com permissao errada...
rmdir /s /q "C:\ProgramData\DockerDesktop" 2>nul

echo [2/4] Recriando pasta com dono correto...
mkdir "C:\ProgramData\DockerDesktop"
takeown /f "C:\ProgramData\DockerDesktop" /r /d s
icacls "C:\ProgramData\DockerDesktop" /grant Administrators:(OI)(CI)F /t
icacls "C:\ProgramData\DockerDesktop" /grant SYSTEM:(OI)(CI)F /t

echo [3/4] Corrigindo WSL...
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart >nul 2>&1
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart >nul 2>&1

echo [4/4] Abrindo instalador do Docker...
start "" "C:\Users\edeny\Downloads\Docker Desktop Installer.exe"

echo.
echo Pronto! O instalador do Docker foi aberto.
echo Clique em OK / Install e aguarde.
echo.
pause
