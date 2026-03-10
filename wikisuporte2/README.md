# WikiSuporte 2.0

> Plataforma profissional de CRM, gestão de tarefas e métricas de suporte.

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-blue)](https://postgresql.org)

---

## O que é o WikiSuporte 2.0?

O WikiSuporte 2.0 é uma evolução do WikiSuporte 1.0 (Streamlit), reescrito do zero com uma arquitetura profissional:

- **Backend:** FastAPI + SQLAlchemy 2.0 + PostgreSQL
- **Frontend:** SPA HTML/CSS/JS (sem frameworks externos)
- **Autenticação:** JWT com refresh token
- **RBAC:** Controle de acesso hierárquico (CEO → Gestor → Analista → Viewer)

---

## Funcionalidades Principais

### ✅ Gestão de Tarefas (ClickUp-like)
- Hierarquia: Espaço → Pasta → Lista → Tarefa → Subtarefa
- Board Kanban com drag-and-drop
- Múltiplos responsáveis, prioridades, datas, checklists
- Dependências entre tarefas
- Automações configuráveis

### 🤝 CRM / Técnico Consultor
- Cadastro de clientes com validação de CNPJ
- Pipeline de prospecções com alerta de duplicidade entre analistas
- Pedidos de venda: módulos, treinamentos, serviços
- Visão estratégica por setor/role

### 🎧 Central de Suporte
- Registro de atendimentos (manual, GoTo API, CSV Multi360)
- Gestão de chamados com SLA
- Controle de plantões
- Log de importações automáticas (bots noturnos)

### 📊 Dashboards e Métricas
- KPIs com filtro hierárquico automático (RBAC)
- Atendimentos por analista
- Funil de prospecções
- Chamados por status e prioridade

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Backend API | FastAPI 0.115+ |
| ORM | SQLAlchemy 2.0 |
| Banco de Dados | PostgreSQL 16 |
| Autenticação | JWT (python-jose) + bcrypt |
| Migrations | Alembic |
| Frontend | HTML5 + CSS3 + Vanilla JS |
| Web Scraping | Selenium |
| IA | Google Gemini |
| Agendamento | APScheduler |

---

## Início Rápido

### 1. Clone e entre na pasta

```bash
git clone https://github.com/Rafaelndd/WikiSuporte
cd WikiSuporte/wikisuporte2/backend
```

### 2. Configure o banco e o `.env`

```bash
# Criar banco
psql -U postgres -c "CREATE DATABASE wikisuporte2;"

# Configurar variáveis
copy .env.example .env
# Edite o .env com suas credenciais
```

### 3. Instale as dependências e inicie

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 4. Crie as tabelas e dados iniciais

```bash
psql -U postgres -d wikisuporte2 -f ..\database\init_schema.sql
psql -U postgres -d wikisuporte2 -f ..\database\seed_data.sql
```

### 5. Abra o frontend

- Abra `frontend/index.html` com **Live Server** no VS Code
- Ou acesse `http://localhost:8000/docs` para a API

**Login padrão:** `admin@wikisuporte.com` / `admin123`

---

## Estrutura do Projeto

```
wikisuporte2/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── config.py            # Settings
│   │   ├── database.py          # SQLAlchemy engine
│   │   ├── dependencies.py      # Injeção de dependências
│   │   ├── models/              # ORM models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── api/                 # Routers / endpoints
│   │   ├── services/            # Lógica de negócio
│   │   └── middleware/          # Audit middleware
│   ├── alembic/                 # Migrations
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html               # SPA shell
│   ├── login.html               # Tela de login
│   ├── css/                     # Estilos
│   ├── js/                      # Scripts
│   │   ├── app.js               # Router SPA
│   │   ├── api.js               # Wrapper fetch
│   │   ├── auth.js              # Auth / JWT
│   │   ├── components/          # Sidebar, Kanban, Modal, Table
│   │   ├── pages/               # Dashboard, Tarefas, CRM, Suporte
│   │   └── utils/               # Dates, Permissions
│   └── assets/                  # Logo, ícones
├── database/
│   ├── init_schema.sql          # Schema completo
│   └── seed_data.sql            # Dados iniciais
└── docs/
    ├── SETUP.md                 # Guia de instalação
    ├── ARCHITECTURE.md          # Arquitetura
    └── API.md                   # Documentação dos endpoints
```

---

## Coexistência com o WikiSuporte 1.0

O WikiSuporte 2.0 está na pasta `wikisuporte2/` e **não modifica nenhum arquivo** da versão 1.0.
Ambas as versões podem rodar em paralelo:

| Versão | Tecnologia | Porta |
|--------|-----------|-------|
| 1.0 | Streamlit | 8501 |
| 2.0 Backend | FastAPI | 8000 |
| 2.0 Frontend | Live Server | 5500 |

---

## Documentação

- [Guia de Instalação](docs/SETUP.md)
- [Arquitetura](docs/ARCHITECTURE.md)
- [Documentação da API](docs/API.md)
- [Swagger UI](http://localhost:8000/docs) (com backend rodando)
