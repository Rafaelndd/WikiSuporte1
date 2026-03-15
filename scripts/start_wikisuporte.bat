@echo off
title Inicializador do WikiSuporte (Streamlit)

:: 1. Navega até à pasta raiz do projeto (pasta pai do scripts)
cd /d "%~dp0.."

:: 2. Regista a data e hora exatas da tentativa de arranque 
:: O operador ">" na primeira linha garante que o ficheiro antigo seja limpo
echo ====================================================== > boot_log.txt
echo [%date% %time%] Tentativa de arranque do WikiSuporte >> boot_log.txt
echo ====================================================== >> boot_log.txt

:: 3. Inicia o Streamlit apontando diretamente para o ambiente virtual
:: A sintaxe ">> boot_log.txt 2>&1" redireciona tanto a saida padrao (1) quanto os erros criticos (2)
".\.venv\Scripts\streamlit.exe" run app.py --server.port 8501 --server.headless=true >> boot_log.txt 2>&1

exit