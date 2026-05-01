# WikiSuporte – Migração GoTo + Multi360

Migração da lógica Streamlit/Python para **FastAPI (backend)** + **JavaScript/HTML5/CSS3 (frontend)**.

## Estrutura

```
migration/
├── backend/
│   ├── main.py          # API REST FastAPI
│   ├── processador.py   # Lógica de processamento (CSV/XLSX/ZIP)
│   └── requirements.txt
└── frontend/
    ├── index.html       # Interface responsiva HTML5
    ├── style.css        # Estilos CSS3
    └── app.js           # Lógica JavaScript
```

---

## Backend (FastAPI)

### Pré-requisitos

- Python 3.11+

### Instalação

```bash
cd migration/backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Variáveis de ambiente

Crie um arquivo `.env` (opcional):

```env
APP_SALT_KEY=sua_chave_secreta_aqui
MAX_BYTES_UPLOAD_IMPORTACAO=10485760   # 10 MB
```

### Executar

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Acesse a documentação automática em: http://localhost:8000/docs

---

## Frontend

### Servir localmente

Qualquer servidor HTTP estático funciona:

```bash
# Python
cd migration/frontend
python -m http.server 3000

# Node.js (npx)
npx serve migration/frontend -p 3000
```

Abra http://localhost:3000 no browser.

> **Nota:** O frontend precisa conseguir acessar a API no endereço `http://localhost:8000`.  
> Se quiser alterar o endereço da API, defina a variável global `window.API_BASE` antes de carregar `app.js`,  
> ou use um servidor reverso (ex.: Nginx) para servir ambos no mesmo host.

### Servir via FastAPI (modo embutido)

O backend detecta automaticamente o diretório `../frontend` e o serve em `/`.  
Nesse caso, acesse http://localhost:8000 para o frontend e http://localhost:8000/docs para a API.

---

## Endpoints da API

| Método | Rota             | Descrição                                           |
|--------|-----------------|-----------------------------------------------------|
| GET    | `/health`        | Healthcheck                                         |
| POST   | `/importar`      | Upload de CSV/XLSX/ZIP — detecção e processamento automático |
| GET    | `/relatorio`     | Consulta filtrada (analista, período, plantão)     |
| GET    | `/exportar/csv`  | Download dos dados em CSV                          |
| GET    | `/exportar/xlsx` | Download dos dados em Excel (.xlsx)                |
| GET    | `/exportar/pdf`  | Download dos dados em PDF (requer `weasyprint`)    |

### Parâmetros de filtro (query string)

Disponíveis em `/relatorio`, `/exportar/csv`, `/exportar/xlsx`, `/exportar/pdf`:

| Parâmetro     | Tipo   | Descrição                        |
|--------------|--------|----------------------------------|
| `analista`   | string | Filtra por nome do analista/atendente |
| `data_inicio`| date   | Data inicial `AAAA-MM-DD`       |
| `data_fim`   | date   | Data final `AAAA-MM-DD`         |
| `plantao`    | string | Filtra por plantão/fila          |

### Exemplo de resposta – POST `/importar`

```json
{
  "status": "ok",
  "tipo": "goto_agent_calls",
  "total_registros": 312,
  "colunas": ["contact_id", "queue_name", "agent_name", "contact_resolution", "..."],
  "preview": [
    { "contact_id": "abc123", "agent_name": "João Silva", "..." }
  ]
}
```

### Exemplo de resposta – Erro de validação

```json
{
  "detail": "Arquivo GoTo Agent Calls inválido. Colunas ausentes: Contact ID, Agent Name"
}
```

---

## Tipos de arquivo suportados

| Tipo detectado      | Coluna chave de detecção                        |
|--------------------|-------------------------------------------------|
| `goto_agent_calls` | `Contact ID` + `Contact Resolution` + `Agent Name` |
| `goto_conversations`| `Data [America/Sao_Paulo]` + `Resultado da chamada` |
| `multi360`         | `PROTOCOLO`                                     |

---

## LGPD

- **Telefones**: hasheados com SHA-256 (salt via `APP_SALT_KEY`) e mascarados na exibição.
- **Nomes de contato** (Multi360): substituídos por `CLIENTE_CONFIDENCIAL`.
- Os dados processados ficam apenas em memória do processo durante a sessão — sem persistência automática em disco.

---

## Exportação PDF

A exportação PDF utiliza a biblioteca `weasyprint`, que possui dependências nativas (GTK/Pango).  
No Windows, instale as dependências conforme [documentação oficial do WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).  
Em ambientes Linux/Docker, instale com:

```bash
apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0
```
