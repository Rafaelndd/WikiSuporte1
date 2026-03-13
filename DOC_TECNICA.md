# WikiSuporte — Documentação Técnica (Manual do Desenvolvedor)

## 1. Visão geral da arquitetura (Streamlit)

O **WikiSuporte** é uma aplicação **multi-página** construída com **Streamlit**. O ponto de entrada é `app.py`, que:

- Define **login** na própria home (sem multipage até autenticar).
- Após autenticação, exibe a **home** com sidebar (usuário, saída, ajuda).
- As demais funcionalidades residem em **`pages/`**, seguindo a convenção do Streamlit (`N_emoji_Nome.py`), que gera o menu de navegação superior automático.

**Fluxo de dados:**

1. **PostgreSQL** — fonte de verdade (chamados, tickets, atendimentos, usuários, base de conhecimento, pgvector, etc.).
2. **Scripts em segundo plano** — `motor_extracao.py`, `modules/selenium_raspagem.py` — leem/escrevem `robo_state.json` e alimentam o banco.
3. **Streamlit** — lê o banco via SQLAlchemy (`modules/database.py`), exibe dashboards e formulários; alguns fluxos gravam de volta (importação, configurações, releases manuais).

**Arquitetura lógica:**

```
[Usuário] → Streamlit (app.py + pages/*)
                ↓
         SQLAlchemy / psycopg2 → PostgreSQL (+ extensão vector)
                ↑
    [Bots] motor_extracao.py / selenium_raspagem.py
                ↑
         APIs externas (Tecnuv Helpdesk, GoTo, Gemini, Open-Meteo)
```

---

## 2. Stack e bibliotecas Python (principais)

| Camada | Tecnologia |
|--------|------------|
| UI | Streamlit |
| Banco | PostgreSQL, SQLAlchemy, psycopg2 |
| Vetores / RAG | pgvector, embeddings Gemini (`google-genai`) |
| Scraping | Selenium, BeautifulSoup |
| Dados | pandas, numpy |
| Gráficos | Plotly |
| Config | python-dotenv (`config.py` + `.env`) |
| HTTP | requests, retry_requests |
| Outros | openmeteo_requests, openai (opcional) |

Instalação típica (exemplo):

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install streamlit sqlalchemy psycopg2-binary pandas plotly python-dotenv selenium beautifulsoup4 google-genai requests pypdf
```

Há um **`requirements.txt`** na raiz do projeto. Para espelhar exatamente o ambiente local, use também `pip freeze > requirements_frozen.txt`.

---

## 3. Estrutura de pastas e arquivos principais

```
WikiSuporte1/
├── app.py                 # Login, home, sidebar pós-login
├── config.py              # Variáveis de ambiente (DB, Tecnuv, LGPD)
├── .env                   # Segredos (não commitar)
├── motor_extracao.py      # Bot: releases, tickets, manuais, wikis (Helpdesk)
├── main_oraculo.py        # Entrada alternativa do bot de chamados
├── modules/
│   ├── database.py        # Engine SQLAlchemy
│   ├── OraculoLogistica.py# Parse HTML → plantões, manuais, tickets, releases
│   ├── selenium_raspagem.py # OraculoBot (chamados Tecnuv)
│   ├── processador_csv.py # GoTo / Multi360
│   ├── auditoria.py
│   └── models.py          # ORM (ChamadoTecnuv, etc.)
├── pages/
│   ├── 1_📊_Dashboard_Atendimentos.py
│   ├── 2_📁_Importacao_Dados.py
│   ├── 3_📊_Dashboard_Chamados.py
│   ├── 4_⚙️_Configuracoes.py
│   ├── 5_📊_Dashboard_Tickets_EPSY.py
│   ├── 6_🤝_Contribuicoes_Suporte.py
│   ├── 7_💬_Feedbaack.py
│   ├── 8_📝_Registro_Atendimentos.py
│   ├── 9_📊_DashboardGestao.py
│   ├── 10_📅_Atendimentos_Diarios.py
│   ├── 11_🧩_Releases_Tecnuv_Manual.py
│   └── ...
├── services/
│   ├── bot_control.py     # robo_state.json, raspagens
│   ├── vector_db.py       # base_conhecimento_embeddings, RAG
│   ├── classificacao_chamados.py
│   ├── db_homologacao.py  # releases, chamados, ciclos_homologacao
│   ├── clientes_service.py
│   └── ...
├── database/
│   ├── init_database.sql
│   ├── migracao_*.sql
│   └── migracao_vector_chamados.sql
├── scripts/
│   ├── start_motor.bat
│   ├── classificar_chamados_antigos.py
│   ├── extrair_texto_manuais_pdf.py
│   └── indexar_base_conhecimento.py
├── robo_state.json        # Estado dos bots (UI + motores)
├── DOC_TECNICA.md
├── DOC_COMERCIAL.md
└── MANUAL_USUARIO.md
```

---

## 4. Ambiente local e execução

### Pré-requisitos

- Python 3.10+ (recomendado)
- PostgreSQL com extensões necessárias (`vector`, `pgcrypto`, etc., conforme scripts em `database/`)
- Chrome/Chromium para Selenium (bots)

### Configuração

1. Copiar `.env` com: `DB_*`, `TECNUV_*`, `LGPD_SECRET_KEY`, `GEMINI_API_KEY`, opcionalmente `GOTO_*`.
2. Aplicar migrações SQL na ordem indicada nos comentários dos arquivos.

### Comandos

```bash
cd C:\WikiSuporte1
.\.venv\Scripts\activate
streamlit run app.py
```

**Motor de raspagem** (necessário para botões em Configurações):

```bash
python motor_extracao.py
```

---

## 5. Estado da sessão (`st.session_state`) e fluxo de dados

Chaves usadas de forma transversal:

| Chave | Uso |
|-------|-----|
| `autenticado` | Boolean — gate de acesso |
| `usuario_id` | FK em auditoria e queries filtradas |
| `usuario_nome` | Exibição |
| `perfil` | dev / coordenador / analista — controle de páginas |
| `notificacoes_lidas` | UX de alertas na home |
| `ultimo_acesso` | (opcional) timeout de sessão |

Páginas em `pages/` costumam:

1. Chamar `st.set_page_config` e `require_profile` ou checar `st.session_state["autenticado"]`.
2. Usar `st.session_state` para importações longas (ex.: `import_df_processado` na Page 2).
3. Invalidar cache com `st.cache_data.clear()` após gravações críticas.

**Fluxo típico de dados:**

- **Leitura:** `get_connection()` → `pd.read_sql` ou `conn.execute(text(...))`.
- **Escrita:** `with engine.begin() as conn:` — transações explícitas.
- **Bots:** leem/escrevem `robo_state.json`; não compartilham `session_state` com o Streamlit.

---

## 6. Segurança e boas práticas

- Senhas: validação via `crypt()` no PostgreSQL (app não armazena senha em claro).
- LGPD: hashes de telefone em importações; segredos apenas no `.env`.
- Não commitar `.env` nem chaves de API.

---

## 7. Referências rápidas

- **Documentação comercial:** `DOC_COMERCIAL.md`
- **Manual do usuário:** `MANUAL_USUARIO.md`
- **Onboarding na UI:** sidebar “💡 Ajuda rápida” após login
