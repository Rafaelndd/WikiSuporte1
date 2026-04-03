@echo off
REM Entrada para serviço Windows (NSSM): motor de extração (bot) na raiz do repositório.
pushd "%~dp0..\.."
if not exist logs mkdir logs
call venv\Scripts\activate.bat
python motor_extracao.py
set EXITCODE=%ERRORLEVEL%
popd
exit /b %EXITCODE%
