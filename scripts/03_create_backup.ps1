<#
.SYNOPSIS
    WikiSuporte — Backup portátil: pg_dump, ZIP seletivo, retenção 30 dias, Task Scheduler.
.DESCRIPTION
    Executar a partir da raiz OU de scripts\. Gera dump SQL na raiz (temporário), compacta em
    backups\WikiSuporte_Backup_YYYYMMDD_HHMM.zip (exclui .venv, __pycache__, backups\).
    Ficheiros bloqueados são ignorados (não aborta). Falhas pg_dump/ZIP → backups\backup_error.log
.PARAMETER RegisterSchedule
    Regista tarefa semanal (domingo 03:00) como NT AUTHORITY\SYSTEM, RunLevel Highest.
.EXAMPLE
    .\03_create_backup.ps1
.EXAMPLE
    .\03_create_backup.ps1 -RegisterSchedule
#>

[CmdletBinding()]
param(
    [switch]$RegisterSchedule
)

$ErrorActionPreference = 'Stop'

# --- Raiz do projeto ---
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
Set-Location -LiteralPath $root

$backupsDir = Join-Path $root 'backups'
$errorLog = Join-Path $backupsDir 'backup_error.log'
$stamp = Get-Date -Format 'yyyyMMdd_HHmm'
$dumpFileName = "wikisuporte_dump_$stamp.sql"
$dumpPath = Join-Path $root $dumpFileName
$zipName = "WikiSuporte_Backup_$stamp.zip"
$zipPath = Join-Path $backupsDir $zipName
$manifestPath = Join-Path $scriptDir 'recovery_portability_manifest.json'
$defaultRootPatterns = @('.py', '.bat', '.exe')

function Get-BackupManifest {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-BackupLog "Manifesto de portabilidade nao carregado: $($_.Exception.Message)" -ErrorOnly
        return $null
    }
}

$defaultDirs = @('assets', 'database', 'logs', 'modules', 'pages', 'scripts', 'services', 'uploads_wiki', '.streamlit')
$manifest = Get-BackupManifest -Path $manifestPath

if ($manifest -and $manifest.portability -and $manifest.portability.backup_scope -and $manifest.portability.backup_scope.folders) {
    $structuralDirs = @($manifest.portability.backup_scope.folders + $defaultDirs) | Select-Object -Unique
} else {
    $structuralDirs = $defaultDirs
}

if ($manifest -and $manifest.portability -and $manifest.portability.backup_scope -and $manifest.portability.backup_scope.root_file_extensions) {
    $rootFilePatterns = $manifest.portability.backup_scope.root_file_extensions | ForEach-Object { $_.ToLowerInvariant().Trim() } | Where-Object { $_ }
    if ($rootFilePatterns.Count -eq 0) {
        $rootFilePatterns = $defaultRootPatterns
    }
} else {
    $rootFilePatterns = $defaultRootPatterns
}

function Write-BackupLog {
    param([string]$Message, [switch]$ErrorOnly)
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    if (-not (Test-Path -LiteralPath $backupsDir)) {
        New-Item -ItemType Directory -Path $backupsDir -Force | Out-Null
    }
    Add-Content -LiteralPath $errorLog -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($ErrorOnly) { Write-Host $line -ForegroundColor Red }
    else { Write-Host $line -ForegroundColor Gray }
}

function Test-ExcludePath {
    param([string]$FullPath)
    $n = $FullPath.ToLowerInvariant()
    if ($n -match '[\\/]\.venv[\\/]' -or $n -match '[\\/]venv[\\/]') { return $true }
    if ($n -match '[\\/]__pycache__[\\/]') { return $true }
    if ($n -match '[\\/]backups[\\/]') { return $true }
    return $false
}

function Find-PgDump {
    foreach ($c in @(
            'pg_dump',
            'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe',
            'C:\Program Files\PostgreSQL\17\bin\pg_dump.exe'
        )) {
        if ($c -eq 'pg_dump') {
            $cmd = Get-Command pg_dump -ErrorAction SilentlyContinue
            if ($cmd) { return $cmd.Source }
        } elseif (Test-Path -LiteralPath $c) { return $c }
    }
    return $null
}

function Get-DbPasswordFromEnv {
    $envFile = Join-Path $root '.env'
    if (-not (Test-Path -LiteralPath $envFile)) { return $null }
    foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        if ($line -match '^\s*DB_PASS\s*=\s*(.*)$') {
            return $Matches[1].Trim().Trim('"')
        }
    }
    return $null
}

function Add-ZipEntrySafe {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$SourceFile,
        [string]$EntryName
    )
    try {
        if (-not (Test-Path -LiteralPath $SourceFile)) { return $false }
        $null = [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $Archive, $SourceFile, $EntryName.Replace('\', '/'),
            [System.IO.Compression.CompressionLevel]::Optimal
        )
        return $true
    } catch {
        Write-BackupLog "ZIP skip (bloqueado ou erro): $SourceFile — $($_.Exception.Message)"
        return $false
    }
}

function Invoke-RetentionCleanup {
    if (-not (Test-Path -LiteralPath $backupsDir)) { return }
    $cutoff = (Get-Date).AddDays(-30)
    Get-ChildItem -LiteralPath $backupsDir -Filter '*.zip' -File -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.CreationTime -lt $cutoff) {
            try {
                Remove-Item -LiteralPath $_.FullName -Force
                Write-BackupLog "Retenção: removido (>30d) $($_.Name)"
            } catch {
                Write-BackupLog "Retenção: falha ao remover $($_.Name): $($_.Exception.Message)"
            }
        }
    }
}

function Register-WikiSuporteBackupTask {
    $scriptFull = Join-Path $scriptDir '03_create_backup.ps1'
    if (-not (Test-Path -LiteralPath $scriptFull)) {
        Write-BackupLog "Agendador: script não encontrado: $scriptFull" -ErrorOnly
        return
    }
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptFull`""
    try {
        $action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument $arg -WorkingDirectory $root
        # Domingo 03:00 (hora local)
        $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At ([DateTime]::Today.AddHours(3))
        $principal = New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
        Register-ScheduledTask -TaskName 'WikiSuporte_Backup_Semanal' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
        Write-Host "Tarefa registada: WikiSuporte_Backup_Semanal (domingos 03:00, SYSTEM, Highest)." -ForegroundColor Green
        Write-BackupLog "Agendador: WikiSuporte_Backup_Semanal registada."
    } catch {
        Write-BackupLog "Agendador Register-ScheduledTask falhou: $($_.Exception.Message)" -ErrorOnly
        throw
    }
}

# ---------------------------------------------------------------------------
# Modo só registo no Agendador
# ---------------------------------------------------------------------------
if ($RegisterSchedule) {
    if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host "Execute -RegisterSchedule como Administrador." -ForegroundColor Yellow
        exit 1
    }
    Register-WikiSuporteBackupTask
    exit 0
}

# ---------------------------------------------------------------------------
# Garantir backups\
# ---------------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $backupsDir)) {
    New-Item -ItemType Directory -Path $backupsDir -Force | Out-Null
}

Write-Host "=== WikiSuporte — 03_create_backup.ps1 ===" -ForegroundColor White
Write-Host "Raiz: $root" -ForegroundColor Gray

$pgDump = Find-PgDump
if (-not $pgDump) {
    $msg = 'pg_dump não encontrado. Instale PostgreSQL ou adicione o bin ao PATH.'
    Write-BackupLog $msg -ErrorOnly
    exit 1
}

# ---------------------------------------------------------------------------
# pg_dump → raiz (temporário)
# ---------------------------------------------------------------------------
$dbPass = Get-DbPasswordFromEnv
$env:PGPASSWORD = $dbPass
try {
    Write-Host "A executar pg_dump (wikisuporte)..." -ForegroundColor Cyan
    & $pgDump -U postgres -d wikisuporte -F p -f $dumpPath -v 2>&1 | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) { throw "pg_dump exit $LASTEXITCODE" }
    if (-not (Test-Path -LiteralPath $dumpPath) -or ((Get-Item $dumpPath).Length -lt 1)) {
        throw 'Dump vazio ou não criado.'
    }
    Write-Host "Dump: $dumpPath" -ForegroundColor Green
} catch {
    $msg = "FALHA pg_dump: $($_.Exception.Message)"
    Write-BackupLog $msg -ErrorOnly
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    exit 1
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------------------
# ZIP (tolerância a locks)
# ---------------------------------------------------------------------------
try {
    Add-Type -AssemblyName System.IO.Compression -ErrorAction Stop
    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop
} catch {
    Write-BackupLog "ZIP: assemblies compressão: $($_.Exception.Message)" -ErrorOnly
    Remove-Item -LiteralPath $dumpPath -Force -ErrorAction SilentlyContinue
    exit 1
}

$zipFailed = $false
$zip = $null
try {
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    $zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)

    # Pastas estruturais
    foreach ($dir in $structuralDirs) {
        $fullDir = Join-Path $root $dir
        if (-not (Test-Path -LiteralPath $fullDir)) { continue }
        Get-ChildItem -LiteralPath $fullDir -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
            if (Test-ExcludePath $_.FullName) { return }
            $rel = $dir + '\' + $_.FullName.Substring($fullDir.Length).TrimStart('\')
            [void](Add-ZipEntrySafe -Archive $zip -SourceFile $_.FullName -EntryName $rel)
        }
    }

    # Raiz: arquivos explicitamente configurados + por extensao
    $manifestRootFiles = @('.env')
    if ($manifest -and $manifest.portability -and $manifest.portability.backup_scope -and $manifest.portability.backup_scope.files) {
        $manifestRootFiles += $manifest.portability.backup_scope.files
        $manifestRootFiles = $manifestRootFiles | Sort-Object -Unique
    } else {
        $manifestRootFiles = @('.env')
    }

    foreach ($pattern in $manifestRootFiles) {
        $p = Join-Path $root $pattern
        if (Test-Path -LiteralPath $p) { [void](Add-ZipEntrySafe -Archive $zip -SourceFile $p -EntryName (Split-Path $p -Leaf)) }
    }
    Get-ChildItem -LiteralPath $root -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $ext = $_.Extension.ToLowerInvariant()
        if ($ext -notin $rootFilePatterns) { return }
        if (Test-ExcludePath $_.FullName) { return }
        [void](Add-ZipEntrySafe -Archive $zip -SourceFile $_.FullName -EntryName $_.Name)
    }

    if (Test-Path -LiteralPath $manifestPath) {
        [void](Add-ZipEntrySafe -Archive $zip -SourceFile $manifestPath -EntryName (Split-Path $manifestPath -Leaf))
    }

    # Dump SQL
    [void](Add-ZipEntrySafe -Archive $zip -SourceFile $dumpPath -EntryName $dumpFileName)
} catch {
    $zipFailed = $true
    Write-BackupLog "FALHA geração ZIP: $($_.Exception.Message)" -ErrorOnly
} finally {
    if ($null -ne $zip) { $zip.Dispose() }
}

# Remover dump temporário na raiz
try {
    Remove-Item -LiteralPath $dumpPath -Force -ErrorAction SilentlyContinue
} catch { Write-BackupLog "Aviso: não foi possível apagar dump temporário: $dumpPath" }

if ($zipFailed -or -not (Test-Path -LiteralPath $zipPath) -or ((Get-Item $zipPath -ErrorAction SilentlyContinue).Length -lt 1)) {
    Write-BackupLog 'FALHA: ficheiro ZIP inválido ou não gerado.' -ErrorOnly
    exit 1
}

Write-Host "ZIP: $zipPath" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Retenção 30 dias
# ---------------------------------------------------------------------------
Invoke-RetentionCleanup

Write-Host "=== Backup concluído ===" -ForegroundColor Green
Write-Host "Para agendar (Admin):  .\03_create_backup.ps1 -RegisterSchedule" -ForegroundColor DarkGray
exit 0
