@echo off
REM Entrada para serviço Windows (NSSM): Streamlit em modo headless na raiz do repositório.
pushd "%~dp0..\.."
if not exist logs mkdir logs
call venv\Scripts\activate.bat
python -m streamlit run app.py --server.headless=true --server.address=0.0.0.0 --server.port=8501
set EXITCODE=%ERRORLEVEL%
popd
exit /b %EXITCODE%
