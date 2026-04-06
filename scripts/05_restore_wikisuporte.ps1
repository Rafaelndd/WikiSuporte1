<#
.SYNOPSIS
    WikiSuporte — Restore portátil com restauracao de arquivos e banco.
.DESCRIPTION
    Descompacta backup gerado por 03_create_backup.ps1, restaura os artefatos da aplicacao
    e reaplica o dump SQL no PostgreSQL com validacoes de seguranca e log persistente.
.PARAMETER BackupPath
    Caminho do arquivo .zip gerado pelo backup (obrigatorio).
.PARAMETER TargetRoot
    Raiz do projeto para restauracao dos arquivos (padrao: raiz do repositorio local do script).
.PARAMETER DbHost
    Host do PostgreSQL (padrao: localhost).
.PARAMETER DbPort
    Porta do PostgreSQL (padrao: 5432).
.PARAMETER DbName
    Nome do banco de destino (padrao: wikisuporte).
.PARAMETER DbAdminUser
    Usuario administrativo do PostgreSQL para comandos de banco (padrao: postgres).
.PARAMETER AdminDatabase
    Banco de administracao para operacoes de controle (padrao: postgres).
.PARAMETER DropExistingDatabase
    Dropa e recria o banco antes de restaurar o dump.
.PARAMETER AllowExistingDatabase
    Permite restaurar em banco existente (recomendado apenas para migracoes manuais com DROP manual).
.PARAMETER SkipDatabaseRestore
    Pula restauracao do banco e executa apenas restauracao de arquivos.
.PARAMETER SkipFileRestore
    Pula restauracao de arquivos e executa apenas banco.
.PARAMETER ForceFileOverwrite
    Sobrescreve arquivos existentes durante a restauração de arquivos.
.PARAMETER PromptForPassword
    Solicita senha do PostgreSQL interativamente.
.PARAMETER KeepTemporaryFiles
    Mantem pasta temporaria de extracao (debug).

.EXAMPLE
    .\scripts\05_restore_wikisuporte.ps1 -BackupPath .\backups\WikiSuporte_Backup_20260406_0300.zip
.EXAMPLE
    .\scripts\05_restore_wikisuporte.ps1 -BackupPath .\backups\...zip -DropExistingDatabase -ForceFileOverwrite -PromptForPassword
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$BackupPath,
    [string]$TargetRoot,
    [string]$DbHost = 'localhost',
    [int]$DbPort = 5432,
    [string]$DbName = 'wikisuporte',
    [string]$DbAdminUser = 'postgres',
    [string]$AdminDatabase = 'postgres',
    [string]$ManifestPath = 'scripts/recovery_portability_manifest.json',
    [string]$SchemaFilePattern = 'wikisuporte_dump_*.sql',
    [string]$TempWorkspace = 'restore_tmp',
    [string]$LogDirectory = 'logs',
    [switch]$DropExistingDatabase,
    [switch]$AllowExistingDatabase,
    [switch]$SkipDatabaseRestore,
    [switch]$SkipFileRestore,
    [switch]$ForceFileOverwrite,
    [switch]$PromptForPassword,
    [switch]$KeepTemporaryFiles
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$defaultRoot = Split-Path -Parent $scriptDir
if (-not $TargetRoot) { $TargetRoot = $defaultRoot }

if (-not (Test-Path -LiteralPath $TargetRoot)) {
    throw "TargetRoot invalido: $TargetRoot"
}

if (-not (Test-Path -LiteralPath $TargetRoot)) {
    throw "TargetRoot nao encontrado: $TargetRoot"
}

if (-not [System.IO.Path]::IsPathRooted($TargetRoot)) {
    $TargetRoot = Join-Path $defaultRoot $TargetRoot
}

$backupCandidate = $BackupPath
if (-not [System.IO.Path]::IsPathRooted($backupCandidate)) {
    $backupCandidate = Join-Path (Get-Location) $BackupPath
}
$backupFull = Resolve-Path -LiteralPath $backupCandidate -ErrorAction SilentlyContinue
if (-not $backupFull) {
    throw "Backup nao encontrado: $BackupPath"
}

Set-Location -LiteralPath $TargetRoot

$backupName = Split-Path -Leaf $backupFull.Path
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$logDir = Join-Path $TargetRoot $LogDirectory
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logFile = Join-Path $logDir ("restore_wikisuporte_{0}_{1}.log" -f $DbName, $stamp)
Add-Content -LiteralPath $logFile -Value "Inicio do restore: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Encoding UTF8

$boundDbHost = $PSBoundParameters.ContainsKey('DbHost')
$boundDbPort = $PSBoundParameters.ContainsKey('DbPort')
$boundDbName = $PSBoundParameters.ContainsKey('DbName')
$boundDbAdminUser = $PSBoundParameters.ContainsKey('DbAdminUser')
$boundAdminDatabase = $PSBoundParameters.ContainsKey('AdminDatabase')

$tempRoot = Join-Path $TargetRoot $TempWorkspace
$extractDir = Join-Path $tempRoot ("restore_" + $stamp)
$schemaFile = $null
$psqlPath = $null
$dbPassword = $null

function Write-Log {
    param([string]$Message, [string]$Color = 'Gray')
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line -ForegroundColor $Color
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
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
    $regex = "^\s*{0}\s*=\s*(.*)$" -f [regex]::Escape($Key)
    foreach ($line in Get-Content -LiteralPath $FilePath -Encoding UTF8) {
        if ($line -match $regex) {
            $value = $Matches[1].Trim()
            if ($value -match '^"(.*)"$') { return $Matches[1] }
            if ($value -match "^'(.*)'$") { return $Matches[1] }
            return $value
        }
    }
    return $null
}

function Read-Manifest {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Log "Manifesto invalido ou ilegivel: $Path" 'Yellow'
        return $null
    }
}

function Invoke-Psql {
    param(
        [string]$Database,
        [string]$SqlFile = $null,
        [string]$Query = $null,
        [string]$Context
    )

    if (-not $dbPassword) {
        throw "Senha do PostgreSQL ausente em Invoke-Psql para $Context."
    }

    $args = @(
        '-X',
        '-v', 'ON_ERROR_STOP=1',
        '-h', $DbHost,
        '-p', $DbPort.ToString(),
        '-U', $DbAdminUser,
        '-d', $Database
    )

    if ($SqlFile) {
        $args += @('-f', $SqlFile)
    } elseif ($Query) {
        $args += @('-c', $Query)
    } else {
        throw "Invoke-Psql precisa de SqlFile ou Query."
    }

    Write-Log "[$Context] $psqlPath " + ($args -join ' ')
    $env:PGPASSWORD = $dbPassword
    try {
        $output = & $psqlPath @args 2>&1
        $code = $LASTEXITCODE
    } finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }

    if ($logFile) {
        $output | Out-String | Add-Content -LiteralPath $logFile -Encoding UTF8
    }

    if ($code -ne 0) {
        throw "Falha no psql [$Context], codigo $code."
    }
    return $output
}

function Get-PsqlScalar {
    param([string]$Database, [string]$Query)
    $out = Invoke-Psql -Database $Database -Query $Query -Context 'scalar'
    $value = ($out | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    return $value
}

function Test-DatabaseExists {
    param([string]$Database)
    $safe = ($Database -replace "'", "''")
    $query = "SELECT 1 FROM pg_database WHERE datname = '$safe';"
    $value = Get-PsqlScalar -Database $AdminDatabase -Query $query
    return $value -eq '1'
}

function Get-UserTableCount {
    param([string]$Database)
    $query = @"
SELECT COUNT(*)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema');
"@
    $count = Get-PsqlScalar -Database $Database -Query $query
    if ([string]::IsNullOrWhiteSpace($count)) { return 0 }
    return [int]$count
}

function Extract-Backup {
    param([string]$ZipPath, [string]$Destination)
    Write-Log "Iniciando extracao do backup: $ZipPath" 'Cyan'
    Add-Type -AssemblyName System.IO.Compression -ErrorAction Stop
    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop

    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($entry in $zip.Entries) {
            if (-not $entry.FullName) { continue }
            $safeEntry = $entry.FullName.Replace('/', '\')
            $dest = Join-Path $Destination $safeEntry
            if ($entry.FullName.EndsWith('/')) {
                New-Item -ItemType Directory -Path $dest -Force | Out-Null
                continue
            }
            $parent = Split-Path -Parent $dest
            if (-not (Test-Path -LiteralPath $parent)) {
                New-Item -ItemType Directory -Path $parent -Force | Out-Null
            }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $dest, $true)
        }
    } finally {
        $zip.Dispose()
    }
}

function Restore-Files {
    param([string]$SourceRoot, [string]$TargetRoot, [string]$SqlDumpPath)
    if ($SkipFileRestore) {
        Write-Log "Arquivo SkipFileRestore ativo: pulando restauracao de arquivos." 'Yellow'
        return
    }

    Write-Log "Iniciando restauracao de arquivos para: $TargetRoot" 'Cyan'
    $srcFiles = Get-ChildItem -LiteralPath $SourceRoot -Recurse -File -Force
    foreach ($file in $srcFiles) {
        if ($SqlDumpPath -and ($file.FullName -eq $SqlDumpPath)) { continue }

        $relative = $file.FullName.Substring($SourceRoot.Length).TrimStart('\', '/')
        if ([string]::IsNullOrWhiteSpace($relative)) { continue }
        if ($relative -like '.git\*' -or $relative -like '.github\*') { continue }

        $dest = Join-Path $TargetRoot $relative
        $parent = Split-Path -Parent $dest
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }

        if ((Test-Path -LiteralPath $dest) -and -not $ForceFileOverwrite) {
            Write-Log "Arquivo existente pulado (use -ForceFileOverwrite): $relative" 'Yellow'
            continue
        }

        if ($PSCmdlet.ShouldProcess($dest, "Restaurar arquivo $relative")) {
            Copy-Item -LiteralPath $file.FullName -Destination $dest -Force
            Write-Log "Arquivo restaurado: $relative" 'Gray'
        }
    }
}

try {
    Write-Log "=== WikiSuporte - restore assistido ===" 'White'
    Write-Log "Backup: $backupFull"
    Write-Log "Destino: $TargetRoot"

    $psqlPath = Resolve-PsqlPath
    if (-not $psqlPath) {
        throw 'psql nao encontrado no PATH ou em Program Files\\PostgreSQL\\18/17.'
    }

    if ([string]::IsNullOrWhiteSpace($BackupPath) -or -not (Test-Path -LiteralPath $backupFull.Path)) {
        throw "Arquivo backup invalido: $BackupPath"
    }

    $extractedFromBackup = $true
    $manifestFromRepo = Join-Path $TargetRoot $ManifestPath
    $manifestFromBackup = Join-Path $extractDir 'recovery_portability_manifest.json'
    if (Test-Path -LiteralPath (Join-Path $TargetRoot 'scripts\recovery_portability_manifest.json')) {
        $manifestFromRepo = Join-Path $TargetRoot 'scripts\recovery_portability_manifest.json'
    }
    $backupManifest = Read-Manifest -Path $manifestFromBackup
    if (-not $backupManifest -and (Test-Path -LiteralPath $manifestFromRepo)) {
        $backupManifest = Read-Manifest -Path $manifestFromRepo
    }

    Extract-Backup -ZipPath $backupFull.Path -Destination $extractDir

    $dumpCandidates = Get-ChildItem -LiteralPath $extractDir -Recurse -File -Filter $SchemaFilePattern | Sort-Object LastWriteTime -Descending
    if ($dumpCandidates.Count -eq 0) {
        throw "Nenhum arquivo de dump encontrado no backup (padrao: $SchemaFilePattern)."
    }
    $schemaFile = $dumpCandidates[0].FullName
    Write-Log "Arquivo dump selecionado: $schemaFile"

    # 1) Restauracao de arquivos
    Restore-Files -SourceRoot $extractDir -TargetRoot $TargetRoot -SqlDumpPath $schemaFile

    if ($SkipDatabaseRestore) {
        Write-Log "SkipDatabaseRestore ativo. Encerrando apenas com restauração de arquivos."
        return
    }

    # 2) Regras de configuração de banco por parametro / .env extraido / .env local
    $candidateEnvFiles = @()
    if (Test-Path -LiteralPath (Join-Path $extractDir '.env')) {
        $candidateEnvFiles += (Join-Path $extractDir '.env')
    }
    if (Test-Path -LiteralPath (Join-Path $TargetRoot '.env')) {
        $candidateEnvFiles += (Join-Path $TargetRoot '.env')
    }

    foreach ($envFile in $candidateEnvFiles) {
        $fileHost = Get-EnvValue -FilePath $envFile -Key 'DB_HOST'
        $filePort = Get-EnvValue -FilePath $envFile -Key 'DB_PORT'
        $fileDb = Get-EnvValue -FilePath $envFile -Key 'DB_NAME'
        $fileUser = Get-EnvValue -FilePath $envFile -Key 'DB_USER'
        $filePass = Get-EnvValue -FilePath $envFile -Key 'DB_PASS'

        if (-not $boundDbHost -and $fileHost) { $DbHost = $fileHost }
        if (-not $boundDbPort -and $filePort -and $filePort -match '^\d+$') { $DbPort = [int]$filePort }
        if (-not $boundDbName -and $fileDb) { $DbName = $fileDb }
        if (-not $boundDbAdminUser -and $fileUser) { $DbAdminUser = $fileUser }
        if (-not $boundAdminDatabase -and (Get-EnvValue -FilePath $envFile -Key 'DB_ADMIN')) {
            $AdminDatabase = Get-EnvValue -FilePath $envFile -Key 'DB_ADMIN'
        }
        if (-not $dbPassword -and $filePass) { $dbPassword = $filePass }
    }

    if (-not $dbPassword -and $env:PGPASSWORD) {
        $dbPassword = $env:PGPASSWORD
    }

    if (-not $dbPassword -and $PromptForPassword) {
        $secure = Read-Host "Senha PostgreSQL para $DbAdminUser" -AsSecureString
        $dbPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        )
    }

    if (-not $dbPassword) {
        throw "Senha de banco ausente. Use -PromptForPassword ou defina DB_PASS em .env."
    }

    Write-Log "Configuracao final de banco: host=$DbHost:$DbPort db=$DbName admin=$DbAdminUser"

    # 3) Validacao administrativa e restauracao do banco
    $isRole = Get-PsqlScalar -Database $AdminDatabase -Query "SELECT rolcreaterole, rolcreatedb, rolsuper FROM pg_roles WHERE rolname = current_user;"
    if ([string]::IsNullOrWhiteSpace($isRole)) {
        throw "Usuario administrativo $DbAdminUser nao autenticou no PostgreSQL."
    }

    $exists = Test-DatabaseExists -Database $DbName
    if (-not $exists) {
        Write-Log "Banco $DbName nao existe. Criando..." 'Cyan'
        $safeDb = $DbName -replace "'", "''"
        Invoke-Psql -Database $AdminDatabase -Query "CREATE DATABASE `"$safeDb`";" -Context 'create-db'
    } else {
        if ($DropExistingDatabase) {
            Write-Log "DropExisting ativo: removendo banco $DbName" 'Yellow'
            $safeDb = $DbName -replace "'", "''"
            Invoke-Psql -Database $AdminDatabase -Query "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$safeDb' AND pid <> pg_backend_pid();" -Context 'disconnect-db'
            Invoke-Psql -Database $AdminDatabase -Query "DROP DATABASE `"$safeDb`";" -Context 'drop-db'
            Invoke-Psql -Database $AdminDatabase -Query "CREATE DATABASE `"$safeDb`";" -Context 'create-db'
        } elseif (-not $AllowExistingDatabase) {
            $count = Get-UserTableCount -Database $DbName
            if ($count -gt 0) {
                throw "Banco $DbName existe com $count tabelas. Use -DropExistingDatabase ou -AllowExistingDatabase."
            }
            Write-Log "Banco existe, sem objetos publicos. Prosseguindo restore no banco atual."
        } else {
            Write-Log "AllowExistingDatabase ativo. Restaura para banco existente." 'Yellow'
        }
    }

    if ($PSCmdlet.ShouldProcess($DbName, "Restaurar dump $schemaFile")) {
        Invoke-Psql -Database $DbName -SqlFile $schemaFile -Context 'restore-schema'
    }

    # 4) Validacao minima
    $vecExists = Get-PsqlScalar -Database $DbName -Query "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector');"
    if ($vecExists -ne 't') {
        throw "Pos-restore: extensao vector nao encontrada no banco $DbName."
    }
    $usuariosExists = Get-PsqlScalar -Database $DbName -Query "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='usuarios');"
    if ($usuariosExists -ne 't') {
        throw "Pos-restore: tabela usuarios nao encontrada no banco $DbName."
    }

    $rowCount = Get-PsqlScalar -Database $DbName -Query "SELECT COUNT(*) FROM base_conhecimento;"
    Write-Log "Pos-restore: base_conhecimento=$rowCount"

    Write-Log "Restore concluido com sucesso." 'Green'
} catch {
    Write-Log "ERRO no restore: $($_.Exception.Message)" 'Red'
    throw
} finally {
    if ($extractDir -and (Test-Path -LiteralPath $extractDir)) {
        if ($KeepTemporaryFiles) {
            Write-Log "Arquivos temporarios mantidos em: $extractDir"
        } else {
            Remove-Item -LiteralPath $extractDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    if ($tempRoot -and (Test-Path -LiteralPath $tempRoot) -and -not (Get-ChildItem -LiteralPath $tempRoot -Force -ErrorAction SilentlyContinue)) {
        Remove-Item -LiteralPath $tempRoot -Force -ErrorAction SilentlyContinue
    }
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Write-Log "Arquivo de log final: $logFile" 'Gray'
}
