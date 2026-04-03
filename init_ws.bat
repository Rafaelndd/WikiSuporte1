@echo off
REM Arranque manual / legado. Para produção com Servicos Windows, ver scripts\windows\README.md (NSSM).
title WikiSuporte - Inicializador de Producao

cd /d %~dp0

echo ========================================
echo   INICIANDO WIKISUPORTE (MODO SERVICO)
echo ========================================

REM Ambiente virtual
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate
) else (
    python -m venv venv
    call venv\Scripts\activate
)

if not exist logs mkdir logs

echo.
echo Iniciando Motor de Extracao em background...
echo.

start "" /B python motor_extracao.py >> logs\motor_extracao.log 2>&1

echo.
echo Iniciando Streamlit em modo headless...
echo.

start "" /B python -m streamlit run app.py ^
    --server.headless=true ^
    --server.address=0.0.0.0 ^
    --server.port=8501 ^
    >> logs\streamlit.log 2>&1

echo.
echo Servicos iniciados. Fechando janela...
exit