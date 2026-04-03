@echo off
setlocal EnableExtensions
REM Corrige venv quando Streamlit falha com:
REM   ImportError: cannot import name '__version__' from 'urllib3'
REM (urllib3-future / resolucao pip quebrada). Executar na pasta scripts\windows.

set "REPO=%~dp0..\.."
cd /d "%REPO%" || exit /b 1

set "PYTHON_EXE="
if exist "%REPO%\venv\Scripts\python.exe" set "PYTHON_EXE=%REPO%\venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%REPO%\.venv\Scripts\python.exe" set "PYTHON_EXE=%REPO%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE (
    echo Nenhum venv encontrado em venv\ nem .venv\
    exit /b 1
)

echo Usando: "%PYTHON_EXE%"
"%PYTHON_EXE%" -m pip uninstall -y urllib3-future 2>nul
"%PYTHON_EXE%" -m pip install --upgrade --force-reinstall "urllib3>=2.2.2,<2.6" "requests>=2.31.0,<3"
echo.
echo Concluido. Teste: streamlit run app.py
exit /b 0
