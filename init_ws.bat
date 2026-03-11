@echo off
title Inicializador Streamlit

REM Vai para a pasta onde está o .bat
cd /d %~dp0

echo ========================================
echo   INICIANDO APLICACAO STREAMLIT
echo ========================================

REM Verifica se existe ambiente virtual
if exist venv\Scripts\activate.bat (
echo Ativando ambiente virtual...
call venv\Scripts\activate
) else (
echo Ambiente virtual nao encontrado.
echo Criando ambiente virtual...
python -m venv venv
call venv\Scripts\activate
)

REM Atualiza pip
echo Atualizando PIP...
python -m pip install --upgrade pip

REM Instala dependencias se existir requirements.txt
if exist requirements.txt (
echo Instalando dependencias...
pip install -r requirements.txt
)

echo.
echo Iniciando servidor Streamlit...
echo.

start http://localhost:8501

streamlit run app.py

echo.
echo Aplicacao finalizada.
pause
