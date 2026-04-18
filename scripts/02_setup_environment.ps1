<#
.SYNOPSIS
    WikiSuporte — Fase 2: validar estrutura, banco wikisuporte + vector, venv (.venv).
.DESCRIPTION
    Executar a partir da raiz do repositório OU de scripts\ (o script localiza a raiz).
    Se .env não existir, cria-o com Read-Host (ClickUp, GoTo, Gemini, DeepSeek, SMTP, DB, Tecnuv).
    psql pode pedir a senha do usuário postgres — será avisado antes de cada uso.
.NOTES
    Venv: python -m venv .venv, Activate.ps1, pip install -r ambientevirtual.txt.
    Falhas em BD, pgvector ou pip interrompem o script (exit 1).
    Depende de: PostgreSQL 18 (psql no PATH ou em Program Files), Python no PATH.
#>

$ErrorActionPreference = 'Stop'

function Write-Fail {
    param([string]$Message)
    Write-Host ""
    Write-Host "[ERRO] $Message" -ForegroundColor Red
    exit 1
}

# Raiz do projeto = pasta que contém scripts\ e este ficheiro
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
Set-Location -LiteralPath $root

Write-Host "=== WikiSuporte — 02_setup_environment.ps1 ===" -ForegroundColor White
Write-Host "Raiz do projeto: $root" -ForegroundColor Gray

# ---------------------------------------------------------------------------
# 1) Pastas críticas (criar se faltarem para bootstrap)
# ---------------------------------------------------------------------------
$requiredDirs = @(
    'assets',
    'database',
    'logs',
    'modules',
    'pages',
    'scripts',
    'services',
    'uploads_wiki',
    '.streamlit'
)

$missing = @()
foreach ($d in $requiredDirs) {
    $full = Join-Path $root $d
    if (-not (Test-Path -LiteralPath $full)) {
        $missing += $d
    }
}

if ($missing.Count -gt 0) {
    Write-Host "Pastas em falta (serão criadas): $($missing -join ', ')" -ForegroundColor Yellow
    foreach ($d in $missing) {
        New-Item -ItemType Directory -Path (Join-Path $root $d) -Force | Out-Null
    }
    Write-Host "Estrutura de pastas garantida." -ForegroundColor Green
} else {
    Write-Host "Estrutura de pastas OK (assets, database, logs, modules, pages, scripts, services, uploads_wiki, .streamlit)." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 1b) .env — criar só se não existir (ClickUp, GoTo, Gemini, DeepSeek, SMTP + DB)
# ---------------------------------------------------------------------------
$envPath = Join-Path $root '.env'
if (Test-Path -LiteralPath $envPath) {
    Write-Host "Ficheiro .env já existe — a saltar criação interativa." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "-------------------------------------------------------------------" -ForegroundColor Cyan
    Write-Host "  Criação do .env (valores em branco = linha vazia no ficheiro)" -ForegroundColor Cyan
    Write-Host "-------------------------------------------------------------------" -ForegroundColor Cyan
    Write-Host ""

    Write-Host "--- ClickUp ---" -ForegroundColor White
    $CLICKUP_API_TOKEN = Read-Host "ClickUp API token (Personal API Token)"
    $CLICKUP_TEAM_ID = Read-Host "ClickUp Team/Workspace ID (opcional)"

    Write-Host ""
    Write-Host "--- GoTo Connect ---" -ForegroundColor White
    $GOTO_CLIENT_ID = Read-Host "GOTO_CLIENT_ID"
    $GOTO_CLIENT_SECRET = Read-Host "GOTO_CLIENT_SECRET"
    $GOTO_REFRESH_TOKEN = Read-Host "GOTO_REFRESH_TOKEN (pode ficar vazio na primeira vez)"

    Write-Host ""
    Write-Host "--- APIs de IA ---" -ForegroundColor White
    $GEMINI_API_KEY = Read-Host "GEMINI_API_KEY"
    $GROQ_API_KEY = Read-Host "GROQ_API_KEY (fallback chat; pode ficar vazio)"

    Write-Host ""
    Write-Host "--- SMTP (e-mail suporte / monitor) ---" -ForegroundColor White
    $EMAIL_SUPORTE_HOST = Read-Host "Servidor SMTP (ex.: smtp.gmail.com)"
    $EMAIL_SUPORTE_USER = Read-Host "Utilizador SMTP"
    $EMAIL_SUPORTE_PASS = Read-Host "Password SMTP"
    $EMAIL_SUPORTE_FOLDER = Read-Host "Pasta IMAP (Enter = INBOX)"
    if ([string]::IsNullOrWhiteSpace($EMAIL_SUPORTE_FOLDER)) { $EMAIL_SUPORTE_FOLDER = "INBOX" }

    Write-Host ""
    Write-Host "--- Base de dados (wikisuporte) ---" -ForegroundColor White
    $DB_HOST = Read-Host "DB_HOST (Enter = localhost)"
    if ([string]::IsNullOrWhiteSpace($DB_HOST)) { $DB_HOST = "localhost" }
    $DB_PORT = Read-Host "DB_PORT (Enter = 5432)"
    if ([string]::IsNullOrWhiteSpace($DB_PORT)) { $DB_PORT = "5432" }
    $DB_NAME = Read-Host "DB_NAME (Enter = wikisuporte)"
    if ([string]::IsNullOrWhiteSpace($DB_NAME)) { $DB_NAME = "wikisuporte" }
    $DB_USER = Read-Host "DB_USER (Enter = postgres)"
    if ([string]::IsNullOrWhiteSpace($DB_USER)) { $DB_USER = "postgres" }
    $DB_PASS = Read-Host "DB_PASS (senha PostgreSQL)"

    Write-Host ""
    Write-Host "--- Tecnuv (Helpdesk) — opcional ---" -ForegroundColor White
    $TECNUV_USER = Read-Host "TECNUV_USER"
    $TECNUV_PASS = Read-Host "TECNUV_PASS"

    $LGPD = -join ((48..57) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
    $envBody = @"
# === Gerado por 02_setup_environment.ps1 ===
# === BANCO DE DADOS ===
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASS=$DB_PASS

MODO_HEADLESS=True
DEBUG=True

# --- TECNUV (Oráculo / raspagem) ---
TECNUV_USER=$TECNUV_USER
TECNUV_PASS=$TECNUV_PASS

LGPD_SECRET_KEY=$LGPD

# --- ClickUp ---
CLICKUP_API_TOKEN=$CLICKUP_API_TOKEN
CLICKUP_TEAM_ID=$CLICKUP_TEAM_ID

# --- GoTo ---
GOTO_CLIENT_ID=$GOTO_CLIENT_ID
GOTO_CLIENT_SECRET=$GOTO_CLIENT_SECRET
GOTO_REFRESH_TOKEN=$GOTO_REFRESH_TOKEN

# --- APIs ---
GEMINI_API_KEY=$GEMINI_API_KEY
GROQ_API_KEY=$GROQ_API_KEY

EMBEDDING_MODEL=gemini
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GROQ_MODEL=llama-3.3-70b-versatile

# --- SMTP / e-mail ---
EMAIL_SUPORTE_HOST=$EMAIL_SUPORTE_HOST
EMAIL_SUPORTE_USER=$EMAIL_SUPORTE_USER
EMAIL_SUPORTE_PASS=$EMAIL_SUPORTE_PASS
EMAIL_SUPORTE_FOLDER=$EMAIL_SUPORTE_FOLDER
"@
    try {
        Set-Content -LiteralPath $envPath -Value $envBody -Encoding UTF8
        Write-Host ""
        Write-Host ".env criado em: $envPath" -ForegroundColor Green
    } catch {
        Write-Fail "Não foi possível gravar .env: $($_.Exception.Message)"
    }
}

# ---------------------------------------------------------------------------
# 2) psql — localizar binário
# ---------------------------------------------------------------------------
$psql = $null
foreach ($c in @(
        "psql",
        "C:\Program Files\PostgreSQL\18\bin\psql.exe",
        "C:\Program Files\PostgreSQL\17\bin\psql.exe"
    )) {
    if ($c -eq "psql") {
        $cmd = Get-Command psql -ErrorAction SilentlyContinue
        if ($cmd) { $psql = $cmd.Source; break }
    } elseif (Test-Path -LiteralPath $c) {
        $psql = $c
        break
    }
}
if (-not $psql) {
    Write-Fail "psql não encontrado. Instale PostgreSQL 18 ou adicione bin ao PATH."
}

Write-Host ""
Write-Host "-------------------------------------------------------------------" -ForegroundColor DarkYellow
Write-Host "  ATENÇÃO: o PostgreSQL pode pedir a SENHA do utilizador ""postgres""." -ForegroundColor Yellow
Write-Host "  Quando aparecer Password for user postgres:, digite a senha e Enter." -ForegroundColor Yellow
Write-Host "-------------------------------------------------------------------" -ForegroundColor DarkYellow
Write-Host ""

# ---------------------------------------------------------------------------
# 3) Criar base wikisuporte se não existir (falha = script termina)
# ---------------------------------------------------------------------------
try {
    $check = & $psql -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='wikisuporte';" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Criação/verificação do banco: psql falhou (código $LASTEXITCODE). Saída: $check"
    }
    $exists = ($check | Out-String).Trim() -match '^1$'
    if (-not $exists) {
        Write-Host "A criar base de dados wikisuporte..." -ForegroundColor Cyan
        $createOut = & $psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE wikisuporte;" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Criação do banco: CREATE DATABASE falhou (código $LASTEXITCODE). $createOut"
        }
        Write-Host "  Base wikisuporte criada." -ForegroundColor Green
    } else {
        Write-Host "Base wikisuporte já existe." -ForegroundColor Green
    }
} catch {
    Write-Fail "Banco de dados: $($_.Exception.Message)"
}

# ---------------------------------------------------------------------------
# 4) CREATE EXTENSION vector (pgvector) — falha = script termina
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Novamente: se pedir, introduza a senha de postgres." -ForegroundColor DarkYellow
$vecOut = & $psql -U postgres -d wikisuporte -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Extensão pgvector: CREATE EXTENSION vector falhou (código $LASTEXITCODE). Instale pgvector no PostgreSQL 18. Detalhes: $vecOut"
}
Write-Host "Extensão vector ativa em wikisuporte." -ForegroundColor Green

# ---------------------------------------------------------------------------
# 5) Ambiente virtual .venv + Activate.ps1 + pip install -r ambientevirtual.txt
# ---------------------------------------------------------------------------
$venvRoot = Join-Path $root '.venv'
$venvPy = Join-Path $root '.venv\Scripts\python.exe'
$activatePs1 = Join-Path $root '.venv\Scripts\Activate.ps1'
$ambienteReq = Join-Path $root 'ambientevirtual.txt'

if (-not (Test-Path -LiteralPath $ambienteReq)) {
    Write-Fail "Ficheiro ambientevirtual.txt não encontrado na raiz do projeto. É obrigatório para pip install -r."
}

Write-Host ""
if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-Host "A criar ambiente virtual .venv (python -m venv .venv)..." -ForegroundColor Cyan
    & python -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Ambiente virtual: python -m venv .venv falhou (código $LASTEXITCODE). Verifique se Python está no PATH."
    }
    if (-not (Test-Path -LiteralPath $venvPy)) {
        Write-Fail "Ambiente virtual: após venv, não foi encontrado $venvPy"
    }
    Write-Host "  .venv criado na raiz do projeto." -ForegroundColor Green
} else {
    Write-Host "Ambiente virtual .venv já existe — a usar e a atualizar dependências." -ForegroundColor Green
}

Write-Host "A ativar ambiente virtual (PowerShell: Activate.ps1)..." -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $activatePs1)) {
    Write-Fail "Activate.ps1 não encontrado em .venv\Scripts\"
}
try {
    . $activatePs1
} catch {
    Write-Fail "Ativação do venv falhou: $($_.Exception.Message). Se for política de execução: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned"
}

Write-Host "A atualizar pip..." -ForegroundColor Cyan
& $venvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Dependências pip: pip install --upgrade pip falhou (código $LASTEXITCODE)."
}

Write-Host "A instalar dependências: pip install -r ambientevirtual.txt ..." -ForegroundColor Cyan
$pipOut = & $venvPy -m pip install -r $ambienteReq 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Dependências pip: pip install -r ambientevirtual.txt falhou (código $LASTEXITCODE). Saída: $pipOut"
}
Write-Host "  pip install -r ambientevirtual.txt concluído." -ForegroundColor Green

Write-Host ""
Write-Host "=== Fase 2 concluída ===" -ForegroundColor Green
Write-Host "  Base: wikisuporte | Extensão: vector | Venv: $root\.venv" -ForegroundColor Gray
Write-Host "  Ativar venv (nova sessão):  .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "  .env: já existente ou criado na Fase 1b; não commitar segredos." -ForegroundColor DarkGray
exit 0
