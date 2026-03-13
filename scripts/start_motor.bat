@echo off
title Motor de Raspagem WikiSuporte
cd /d "%~dp0.."
echo ========================================
echo   MOTOR DE RASPAGEM - Chamados, Releases, etc.
echo ========================================
echo.
echo Mantenha esta janela aberta. Os botoes na pagina Configuracoes
echo acionarao as varreduras automaticamente.
echo.
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate
) else if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate
)
python motor_extracao.py
pause
