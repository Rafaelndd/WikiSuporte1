#Requires -RunAsAdministrator
<#
.SYNOPSIS
    WikiSuporte — dependências base no Windows (PostgreSQL 18, Python 3.14, VS Code, pgvector).
.DESCRIPTION
    Exige execução como Administrador. Instala via winget e implanta pgvector no PostgreSQL 18.
    Qualquer falha crítica aborta com exit 1.
#>

$ErrorActionPreference = 'Stop'

function Write-Fail {
    param([string]$Message)
    Write-Host ""
    Write-Host "[ERRO] $Message" -ForegroundColor Red
    Write-Host ""
    exit 1
}

function Invoke-WingetInstall {
    param(
        [Parameter(Mandatory = $true)][string]$PackageId,
        [string]$Label
    )
    try {
        Write-Host "winget: instalando $Label ($PackageId)..." -ForegroundColor Cyan
        & winget install --id $PackageId --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            throw "winget terminou com código $LASTEXITCODE"
        }
        Write-Host "  OK: $Label" -ForegroundColor Green
    } catch {
        Write-Fail "Falha no winget ao instalar $Label ($PackageId). Detalhe: $($_.Exception.Message)"
    }
}

# ---------------------------------------------------------------------------
# 1) Administrador ( #Requires já bloqueia sem elevação )
# ---------------------------------------------------------------------------
Write-Host "=== WikiSuporte — 01_install_os_deps.ps1 (elevado) ===" -ForegroundColor White

# ---------------------------------------------------------------------------
# 2) PostgreSQL 18 — obrigatório; falha = aborta
# ---------------------------------------------------------------------------
try {
    Invoke-WingetInstall -PackageId "PostgreSQL.PostgreSQL.18" -Label "PostgreSQL 18"
} catch {
    Write-Fail "Instalação do PostgreSQL 18 falhou. Não é seguro continuar sem o banco. $($_.Exception.Message)"
}

$pgRoot = "C:\Program Files\PostgreSQL\18"
if (-not (Test-Path -LiteralPath $pgRoot)) {
    Write-Fail "Pasta esperada do PostgreSQL não encontrada: $pgRoot. Ajuste o caminho ou reinstale o PostgreSQL 18."
}

# ---------------------------------------------------------------------------
# 3) Python 3.14 e VS Code
# ---------------------------------------------------------------------------
Invoke-WingetInstall -PackageId "Python.Python.3.14" -Label "Python 3.14"
Invoke-WingetInstall -PackageId "Microsoft.VisualStudioCode" -Label "Visual Studio Code"

# ---------------------------------------------------------------------------
# 4) pgvector — download, extração, cópia para Postgres 18
# ---------------------------------------------------------------------------
$zipUrl = "https://raw.githubusercontent.com/Rafaelndd/Wk_Satelite/f72cf7fb4eb35837e723b115a4754121953405d5/pgvector_pgsql_windows-0.8.2_18.0.2.zip"
$zipPath = Join-Path $env:TEMP "pgvector.zip"
$extractDir = Join-Path $env:TEMP "pgvector_extract_$(Get-Random)"

try {
    Write-Host "pgvector: baixando..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    if (-not (Test-Path -LiteralPath $zipPath) -or ((Get-Item $zipPath).Length -lt 1024)) {
        throw "Arquivo baixado inválido ou vazio: $zipPath"
    }
} catch {
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue }
    Write-Fail "Falha no download do pgvector. URL: $zipUrl. $($_.Exception.Message)"
}

try {
    New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
    Write-Host "pgvector: extraindo..." -ForegroundColor Cyan
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
} catch {
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Fail "Falha ao extrair pgvector.zip. $($_.Exception.Message)"
}

try {
    Write-Host "pgvector: copiando para $pgRoot ..." -ForegroundColor Cyan
    # O .zip pode ter raiz única (ex.: pasta interna) ou lib/share na raiz — copiar recursivamente tudo para PG18
    $children = Get-ChildItem -LiteralPath $extractDir -Force
    if ($children.Count -eq 1 -and $children[0].PSIsContainer) {
        $sourceRoot = $children[0].FullName
    } else {
        $sourceRoot = $extractDir
    }
    Copy-Item -Path (Join-Path $sourceRoot '*') -Destination $pgRoot -Recurse -Force
    Write-Host "  OK: pgvector implantado em PostgreSQL 18" -ForegroundColor Green
} catch {
    Write-Fail "Falha ao copiar binários pgvector para '$pgRoot'. Verifique permissões e estrutura do ZIP. $($_.Exception.Message)"
} finally {
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $extractDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "=== Concluído: PostgreSQL 18, Python 3.14, VS Code e pgvector. ===" -ForegroundColor Green
Write-Host "Reinicie o terminal (ou o serviço PostgreSQL) se necessário. Crie a extensão no banco: CREATE EXTENSION vector;" -ForegroundColor DarkGray
exit 0
