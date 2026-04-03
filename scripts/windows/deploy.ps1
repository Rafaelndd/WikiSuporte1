#Requires -Version 5.1
<#
.SYNOPSIS
  Atualiza producao a partir do Git (servicos NSSM parados durante a janela de manutencao).

.PARAMETER GitRef
  Opcional. Ex.: main | v1.0.1

.PARAMETER SkipPip
  Omite pip install -r requirements.txt.

.EXAMPLE
  .\deploy.ps1
  .\deploy.ps1 -GitRef v1.0.1
  .\deploy.ps1 -GitRef main -SkipPip
#>
param(
    [string]$GitRef = "",
    [switch]$SkipPip
)

$ErrorActionPreference = "Stop"

$Services = @("WikiSuporteStreamlit", "WikiSuporteMotor")
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot "venv\Scripts\python.exe"

function Stop-WikiServices {
    foreach ($name in $Services) {
        $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
        if ($null -ne $svc -and $svc.Status -ne "Stopped") {
            Write-Host "Parando servico: $name"
            Stop-Service -Name $name -Force
        }
    }
}

function Start-WikiServices {
    foreach ($name in $Services) {
        $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
        if ($null -ne $svc) {
            Write-Host "Iniciando servico: $name"
            Start-Service -Name $name
        }
        else {
            Write-Warning "Servico nao instalado: $name - ver scripts\windows\README.md (NSSM)"
        }
    }
}

if (-not (Test-Path $Python)) {
    throw "Python do venv nao encontrado: $Python"
}

Stop-WikiServices
Set-Location $RepoRoot
Write-Host "Repositorio: $RepoRoot"

git fetch origin --tags

if ($GitRef) {
    Write-Host "Checkout: $GitRef"
    git checkout $GitRef
    if ($GitRef -match '^v?\d+\.\d+\.\d+$') {
        Write-Host "Ref parece tag de versao; sem pull."
    }
    else {
        git pull origin $GitRef
    }
}
else {
    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    Write-Host "Pull branch atual: $branch"
    git pull origin $branch
}

if (-not $SkipPip) {
    Write-Host "pip install -r requirements.txt"
    & $Python -m pip install -r (Join-Path $RepoRoot "requirements.txt")
}

Write-Host "Se usa Alembic: ative o venv e rode alembic upgrade head (comando da equipe)."
Start-WikiServices
Write-Host "Concluido. Teste http://localhost:8502 e a pasta logs\"
