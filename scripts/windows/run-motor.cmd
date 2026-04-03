@echo off
setlocal EnableExtensions
REM Entrada para serviço Windows (NSSM): motor de extração na raiz do repositório.

set "REPO=%~dp0..\.."
cd /d "%REPO%" || exit /b 1
if not exist logs mkdir logs

set "PYTHON_EXE="
if exist "%REPO%\venv\Scripts\python.exe" set "PYTHON_EXE=%REPO%\venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%REPO%\.venv\Scripts\python.exe" set "PYTHON_EXE=%REPO%\.venv\Scripts\python.exe"

if not defined PYTHON_EXE (
    echo [%date% %time%] ERRO: Nao encontrado venv\Scripts\python.exe nem .venv\Scripts\python.exe em "%REPO%" >> logs\motor-service.err.log
    exit /b 1
)

"%PYTHON_EXE%" motor_extracao.py
exit /b %ERRORLEVEL%
