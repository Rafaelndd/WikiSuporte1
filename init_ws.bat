@echo off
title WikiSuporte - Inicializador

cd /d %~dp0

echo ========================================
echo   INICIANDO WIKISUPORTE
echo ========================================

REM Ambiente virtual
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate
) else (
    python -m venv venv
    call venv\Scripts\activate
)

python -m pip install --upgrade pip

if exist requirements.txt (
    pip install -r requirements.txt
)

echo.
echo Iniciando Motor de Extracao...
echo.

start "Motor Extracao WikiSuporte" cmd /k python motor_extracao.py

echo.
echo Iniciando Streamlit...
echo.

start http://localhost:8501

streamlit run app.py