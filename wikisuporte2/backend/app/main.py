from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from .config import settings
from .database import engine
from .middleware.audit import AuditMiddleware
from .api import auth, usuarios, tarefas, crm, suporte, dashboards

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: testa conexão com o banco
    try:
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("✅ Conexão com o banco de dados estabelecida com sucesso.")
    except Exception as exc:
        logger.error(f"❌ Falha ao conectar ao banco de dados: {exc}")
    yield
    # Shutdown
    logger.info("Encerrando WikiSuporte 2.0 API...")


app = FastAPI(
    title="WikiSuporte 2.0 API",
    description=(
        "API backend do WikiSuporte 2.0 — plataforma de CRM, gestão de tarefas, "
        "métricas de suporte e módulo Técnico Consultor."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# --- CORS ---
# Em produção, substitua ["*"] pelos domínios específicos da sua aplicação.
# Exemplo: ["https://wikisuporte.empresa.com", "http://localhost:5500"]
_cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Middleware de Auditoria ---
app.add_middleware(AuditMiddleware)

# --- Routers ---
app.include_router(auth.router, prefix="/api/auth", tags=["Autenticação"])
app.include_router(usuarios.router, prefix="/api/usuarios", tags=["Usuários"])
app.include_router(tarefas.router, prefix="/api/tarefas", tags=["Tarefas"])
app.include_router(crm.router, prefix="/api/crm", tags=["CRM"])
app.include_router(suporte.router, prefix="/api/suporte", tags=["Suporte"])
app.include_router(dashboards.router, prefix="/api/dashboards", tags=["Dashboards"])


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "sistema": "WikiSuporte 2.0", "versao": "2.0.0"}


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}
