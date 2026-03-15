# WikiSuporte — Deploy em produção

Checklist para subir o projeto no servidor da empresa e remover da máquina local.

## 1. Pré-requisitos no servidor

- **Python 3.10+** (recomendado 3.11 ou 3.12)
- **PostgreSQL 14+** com extensão **pgvector**
- Navegador/Chromium (para motor de extração com Selenium, se for usar)

## 2. Variáveis de ambiente

1. Copie o exemplo e crie o `.env` na raiz do projeto:
   ```bash
   cp .env.example .env
   ```
2. Preencha **obrigatoriamente** no `.env`:
   - `TECNUV_USER`, `TECNUV_PASS` — credenciais Tecnuv
   - `LGPD_SECRET_KEY` — chave para dados sensíveis
   - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` — conexão PostgreSQL

3. Opcionais (conforme uso): GoTo, Gemini/DeepSeek/OpenAI, e-mail, `MODO_HEADLESS=True` (recomendado no servidor).

## 3. Instalação

```bash
cd /caminho/do/WikiSuporte1
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux
pip install -r requirements.txt
```

## 4. Banco de dados

- Crie o banco (ex.: `central_chamados`) e aplique as migrations/scripts em `database/` (e `pg_vector` se usar embeddings).
- Confirme que a extensão pgvector está instalada: `CREATE EXTENSION IF NOT EXISTS vector;`

## 5. Execução

- **Apenas interface (Streamlit):**
  ```bash
  streamlit run app.py --server.port 8501 --server.headless=true
  ```
- **Com motor de extração** (Windows): use `init_ws.bat` na raiz.
- **Script alternativo:** `scripts\start_wikisuporte.bat` — usa a pasta do projeto automaticamente (`%~dp0..`).

## 6. Produção (servidor)

- Use **HTTPS** e um proxy reverso (nginx/IIS) na frente do Streamlit.
- Defina `MODO_HEADLESS=True` no `.env` se o motor de extração rodar no servidor.
- Logs: pasta `logs/` e `sistema.log`; redirecione saída do Streamlit se necessário (ex.: `>> boot_log.txt 2>&1`).
- Não commite `.env` (já está no `.gitignore`).

## 7. Correções aplicadas (revisão para produção)

- **config.py:** `MODO_HEADLESS` corrigido — `True` no .env agora ativa headless corretamente.
- **modules/database.py:** porta padrão alinhada a 5432; remoção de função `get_connection` duplicada.
- **scripts/start_wikisuporte.bat:** passa a usar pasta do projeto por `%~dp0..` em vez de `C:\WikiSuporte` fixo.
- **requirements.txt:** `reportlab` com versão mínima (`>=4.0.0`) para reprodutibilidade.

## 8. Validação pós-deploy

1. Acessar a URL do Streamlit e fazer login.
2. Verificar uma página que use banco (ex.: Dashboard).
3. Se usar motor de extração: rodar uma vez e checar logs.
4. Confirmar que não há erro de variável obrigatória (TECNUV_*, LGPD_SECRET_KEY) no arranque.
