<#
#.SYNOPSIS
#    WikiSuporte — Provisionamento seguro do schema de banco de dados (produção).
#.DESCRIPTION
#    Cria/verifica banco, valida pré-requisitos, executa o script SQL consolidado,
#    grava log persistente e faz rollback (drop do banco recém-criado) em falhas.
#.PARAMETER DbHost
#    Host do PostgreSQL (padrão: localhost).
#.PARAMETER DbPort
#    Porta do PostgreSQL (padrão: 5432).
#.PARAMETER DbName
#    Nome do banco de destino (padrão: wikisuporte).
#.PARAMETER DbAdminUser
#    Usuário administrador do PostgreSQL usado para criação/execução (padrão: postgres).
#.PARAMETER AdminDatabase
#    Banco de administração para operações de controle (padrão: postgres).
#.PARAMETER SchemaFile
#    Caminho do script SQL consolidado.
#.PARAMETER RecreateIfExists
#    Apaga e recria o banco antes da execução se ele já existir.
#.PARAMETER AllowNonEmpty
#    Permite executar em banco existente com objetos já criados.
#.PARAMETER PromptForPassword
#    Solicita a senha interativamente quando DB_PASS não for localizado.
#.PARAMETER LogDirectory
#    Pasta de logs (padrão: logs).
#.EXAMPLE
#    .\04_apply_schema_prod.ps1
#.EXAMPLE
#    .\04_apply_schema_prod.ps1 -DbHost 127.0.0.1 -DbName wikisuporte -RecreateIfExists
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)][string]$DbHost = 'localhost',
    [Parameter(Mandatory = $false)][int]$DbPort = 5432,
    [Parameter(Mandatory = $false)][string]$DbName = 'wikisuporte',
    [Parameter(Mandatory = $false)][string]$DbAdminUser = 'postgres',
    [Parameter(Mandatory = $false)][string]$AdminDatabase = 'postgres',
    [Parameter(Mandatory = $false)][string]$SchemaFile = 'database/wikisuporte_schema_full_ddl.sql',
    [Parameter(Mandatory = $false)][string]$LogDirectory = 'logs',
    [Parameter(Mandatory = $false)][string]$EnvironmentRoot,
    [switch]$RecreateIfExists,
    [switch]$AllowNonEmpty,
    [switch]$PromptForPassword,
    [switch]$SkipRollback
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = if ($EnvironmentRoot) { $EnvironmentRoot } else { Split-Path -Parent $scriptDir }
$null = Set-Location -LiteralPath $root

$isBoundDbHost = $PSBoundParameters.ContainsKey('DbHost')
$isBoundDbPort = $PSBoundParameters.ContainsKey('DbPort')
$isBoundDbName = $PSBoundParameters.ContainsKey('DbName')
$isBoundDbAdminUser = $PSBoundParameters.ContainsKey('DbAdminUser')

$psqlPath = $null
$dbPassword = $null
$logFile = $null
$createdByScript = $false

function Write-Log {
    param([string]$Message, [string]$Color = 'Gray')
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line -ForegroundColor $Color
    if ($logFile) {
        Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
    }
}

function Resolve-PsqlPath {
    $candidates = @(
        'psql',
        'C:\Program Files\PostgreSQL\18\bin\psql.exe',
        'C:\Program Files\PostgreSQL\17\bin\psql.exe'
    )
    foreach ($candidate in $candidates) {
        if ($candidate -eq 'psql') {
            $cmd = Get-Command psql -ErrorAction SilentlyContinue
            if ($cmd) { return $cmd.Source }
        } elseif (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    return $null
}

function Get-EnvValue {
    param(
        [string]$FilePath,
        [string]$Key
    )
    if (-not (Test-Path -LiteralPath $FilePath)) { return $null }
    $escaped = [regex]::Escape($Key)
    $line = Get-Content -LiteralPath $FilePath -Encoding UTF8 | Where-Object {
        $_ -match "^\s*$escaped\s*="
    } | Select-Object -First 1
    if (-not $line) { return $null }
    $parts = $line -split '=\s*', 2
    if ($parts.Count -lt 2) { return $null }
    $value = $parts[1].Trim()
    if ($value -match '^"(.*)"$') { return $Matches[1] }
    if ($value -match "^'(.*)'$") { return $Matches[1] }
    return $value
}

function Escape-SqlLiteral {
    param([string]$Value)
    return ($Value -replace "'", "''")
}

function Invoke-Psql {
    param(
        [string]$Database,
        [string]$Query = $null,
        [string]$SqlFile = $null,
        [string]$Stage
    )

    if (-not $dbPassword) {
        throw "Senha do PostgreSQL não definida para a função Invoke-Psql."
    }

    $args = @(
        '-X',
        '-q',
        '-A',
        '-t',
        '-v', 'ON_ERROR_STOP=1',
        '-h', $DbHost,
        '-p', $DbPort.ToString(),
        '-U', $DbAdminUser,
        '-d', $Database
    )

    if ($Query) {
        $args += @('-c', $Query)
    } elseif ($SqlFile) {
        $args += @('-f', $SqlFile)
    } else {
        throw 'Invoke-Psql requires Query ou SqlFile.'
    }

    Write-Log "[$Stage] Executando psql: $psqlPath $($args -join ' ')" 'Gray'
    $env:PGPASSWORD = $dbPassword
    try {
        $output = & $psqlPath @args 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }

    if ($logFile) {
        $output | Out-String | Add-Content -LiteralPath $logFile -Encoding UTF8
    }

    if ($exitCode -ne 0) {
        Write-Log "Falha em [$Stage]. Codigo: $exitCode." 'Red'
        throw "Falha no psql para [$Stage] (exit=$exitCode)."
    }
    return $output
}

function Get-PsqlScalar {
    param([string]$Database, [string]$Query)
    $out = Invoke-Psql -Database $Database -Query $Query -Stage 'scalar'
    $value = ($out | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    return $value
}

function Test-DatabaseExists {
    param([string]$Database)
    $name = Escape-SqlLiteral $Database
    $query = "SELECT 1 FROM pg_database WHERE datname = '$name';"
    $value = Get-PsqlScalar -Database $AdminDatabase -Query $query
    return ($value -eq '1')
}

function Invoke-RollbackIfNeeded {
    if ($SkipRollback -or -not $createdByScript) { return }
    if (-not (Test-DatabaseExists -Database $DbName)) { return }
    Write-Log "Rollback ativo: removendo banco recém-provisionado '$DbName'." 'Yellow'
    $safeDb = Escape-SqlLiteral $DbName
    $disconnect = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$safeDb' AND pid <> pg_backend_pid();"
    try {
        Invoke-Psql -Database $AdminDatabase -Query $disconnect -Stage 'rollback'
        $drop = "DROP DATABASE IF EXISTS `"$safeDb`";"
        Invoke-Psql -Database $AdminDatabase -Query $drop -Stage 'rollback'
        Write-Log "Rollback concluído: banco '$DbName' removido." 'Green'
    } catch {
        Write-Log "Não foi possível remover automaticamente '$DbName' no rollback: $($_.Exception.Message)" 'Red'
    }
}

function Write-Header {
    Write-Host ''
    Write-Host '=== WikiSuporte — provisionamento assistido de banco (produção) ===' -ForegroundColor White
    Write-Host "Projeto: $root" -ForegroundColor Gray
    Write-Host "Banco: $DbName@$DbHost:$DbPort (admin: $DbAdminUser, controle: $AdminDatabase)" -ForegroundColor Gray
}

try {
    Write-Header

    $psqlPath = Resolve-PsqlPath
    if (-not $psqlPath) {
        throw 'psql não encontrado. Instale PostgreSQL 18+ ou adicione bin ao PATH.'
    }

    if (-not (Test-Path -LiteralPath $root)) {
        throw "Raiz do projeto não encontrada: $root"
    }

    $schemaPath = if ([System.IO.Path]::IsPathRooted($SchemaFile)) {
        $SchemaFile
    } else {
        Join-Path $root $SchemaFile
    }
    if (-not (Test-Path -LiteralPath $schemaPath)) {
        throw "Script DDL não encontrado: $schemaPath"
    }

    $envFile = Join-Path $root '.env'
    if (Test-Path -LiteralPath $envFile) {
        $fileHost = Get-EnvValue -FilePath $envFile -Key 'DB_HOST'
        $filePort = Get-EnvValue -FilePath $envFile -Key 'DB_PORT'
        $fileName = Get-EnvValue -FilePath $envFile -Key 'DB_NAME'
        $fileUser = Get-EnvValue -FilePath $envFile -Key 'DB_USER'
        if (-not $isBoundDbHost -and $fileHost) { $DbHost = $fileHost }
        if (-not $isBoundDbPort -and $filePort -and $filePort -match '^\d+$') { $DbPort = [int]$filePort }
        if (-not $isBoundDbName -and $fileName) { $DbName = $fileName }
        if (-not $isBoundDbAdminUser -and $fileUser) { $DbAdminUser = $fileUser }
        if (-not $dbPassword) { $dbPassword = Get-EnvValue -FilePath $envFile -Key 'DB_PASS' }
    }

    if (-not $dbPassword -and $PromptForPassword) {
        $secure = Read-Host "Senha PostgreSQL para $DbAdminUser" -AsSecureString
        $dbPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        )
    }

    if (-not $dbPassword) {
        throw 'Senha de banco não definida. Defina DB_PASS no .env ou use -PromptForPassword.'
    }

    $logsDir = Join-Path $root $LogDirectory
    if (-not (Test-Path -LiteralPath $logsDir)) { New-Item -ItemType Directory -Path $logsDir -Force | Out-Null }
    $logFile = Join-Path $logsDir ("schema_provision_{0}_{1}.log" -f $DbName, (Get-Date -Format 'yyyyMMdd_HHmmss'))
    Add-Content -LiteralPath $logFile -Value "Início do log - $(Get-Date -Format 's')" -Encoding UTF8

    Write-Log "Pré-checks e preparação iniciados." 'Cyan'

    # 1) Validação de permissão de criação de banco
    $roleInfo = Get-PsqlScalar -Database $AdminDatabase -Query "SELECT rolsuper::text || ':' || rolcreatedb::text FROM pg_roles WHERE rolname = current_user;"
    if ([string]::IsNullOrWhiteSpace($roleInfo)) {
        throw "Usuário atual não encontrado em pg_roles: $DbAdminUser"
    }
    $parts = $roleInfo.Split(':')
    $isSuper = ($parts[0] -eq 't')
    $canCreateDb = ($parts[1] -eq 't')
    if (-not ($isSuper -or $canCreateDb)) {
        throw "Usuário $DbAdminUser não tem permissão para criar banco (nem rolcreatedb nem superuser)."
    }

    # 2) Verifica se extensão vector está disponível no cluster
    $vectorAvailable = Get-PsqlScalar -Database $AdminDatabase -Query "SELECT 1 FROM pg_available_extensions WHERE name='vector';"
    if ($vectorAvailable -ne '1') {
        throw "Extensão pgvector não está disponível no servidor. Instale o pacote/extension do PostgreSQL 18."
    }
    Write-Log "Pré-check pgvector: disponível." 'Green'

    # 3) Checagem de banco de destino
    $exists = Test-DatabaseExists -Database $DbName
    if ($exists -and -not $RecreateIfExists -and -not $AllowNonEmpty) {
        $safe = Escape-SqlLiteral $DbName
        $tableCount = Get-PsqlScalar -Database $DbName -Query @"
SELECT COUNT(*)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema');
"@
        if ([int]$tableCount -gt 0) {
            throw "Banco '$DbName' já existe e não está vazio. Use -AllowNonEmpty para manter objetos existentes ou -RecreateIfExists para recriar."
        }
        Write-Log "Banco '$DbName' existe, mas está vazio e pode ser reutilizado." 'Green'
    }

    if (-not $exists) {
        Write-Log "Criando banco '$DbName' no servidor." 'Cyan'
        $safe = Escape-SqlLiteral $DbName
        $create = "CREATE DATABASE `"$safe`";"
        Invoke-Psql -Database $AdminDatabase -Query $create -Stage 'create-database'
        $createdByScript = $true
        Write-Log "Banco '$DbName' criado." 'Green'
    } elseif ($RecreateIfExists) {
        Write-Log "Recriando banco '$DbName' conforme parâmetro -RecreateIfExists." 'Yellow'
        $safe = Escape-SqlLiteral $DbName
        $disconnect = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$safe' AND pid <> pg_backend_pid();"
        Invoke-Psql -Database $AdminDatabase -Query $disconnect -Stage 'disconnect-existing'
        $drop = "DROP DATABASE `"$safe`";"
        Invoke-Psql -Database $AdminDatabase -Query $drop -Stage 'drop-existing'
        $create = "CREATE DATABASE `"$safe`";"
        Invoke-Psql -Database $AdminDatabase -Query $create -Stage 'create-database'
        $createdByScript = $true
        Write-Log "Banco '$DbName' recriado com sucesso." 'Green'
    }

    # 4) Executa DDL consolidado com log e fail-fast
    Write-Log "Iniciando execução do schema: $schemaPath" 'Cyan'
    Invoke-Psql -Database $DbName -SqlFile $schemaPath -Stage 'apply-schema'
    Write-Log "Schema aplicado com sucesso em '$DbName'." 'Green'

    # 5) Validações rápidas pós-deploy
    $vectorAfter = Get-PsqlScalar -Database $DbName -Query "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector');"
    if ($vectorAfter -ne 't') {
        throw "Pós-deploy: extensão vector não foi instalada no banco '$DbName'."
    }
    $usuariosExists = Get-PsqlScalar -Database $DbName -Query "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='usuarios');"
    if ($usuariosExists -ne 't') {
        throw "Pós-deploy: tabela 'usuarios' não foi criada."
    }
    Write-Log "Validações pós-deploy concluídas: extensão vector e tabela usuarios presentes." 'Green'

    Write-Log 'Provisionamento finalizado com sucesso.' 'Green'
} catch {
    Write-Log "ERRO: $($_.Exception.Message)" 'Red'
    if ($createdByScript -or $RecreateIfExists) {
        Invoke-RollbackIfNeeded
    }
    Write-Log "Detalhes completos no log: $logFile" 'DarkGray'
    throw
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    if ($logFile) {
        Write-Log "Fim do processo em $(Get-Date -Format 's')." 'Gray'
        Write-Log "Arquivo de log: $logFile" 'Gray'
    }
}
