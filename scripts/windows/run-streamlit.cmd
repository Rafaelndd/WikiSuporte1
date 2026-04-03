@echo off
setlocal EnableExtensions
REM Entrada para serviço Windows (NSSM): Streamlit headless na raiz do repositório.
REM Usa python.exe do venv diretamente (mais fiável que activate.bat com conta LocalSystem).

set "REPO=%~dp0..\.."
cd /d "%REPO%" || exit /b 1
if not exist logs mkdir logs

set "PYTHON_EXE="
if exist "%REPO%\venv\Scripts\python.exe" set "PYTHON_EXE=%REPO%\venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%REPO%\.venv\Scripts\python.exe" set "PYTHON_EXE=%REPO%\.venv\Scripts\python.exe"

if not defined PYTHON_EXE (
    echo [%date% %time%] ERRO: Nao encontrado venv\Scripts\python.exe nem .venv\Scripts\python.exe em "%REPO%" >> logs\streamlit-service.err.log
    exit /b 1
)

"%PYTHON_EXE%" -m streamlit run app.py --server.headless=true --server.address=0.0.0.0 --server.port=8502
exit /b %ERRORLEVEL%
