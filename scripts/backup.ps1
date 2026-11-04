param(
    [string]$OutputRoot = "backups"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path (Join-Path $projectRoot $OutputRoot) $stamp
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

Push-Location $projectRoot
try {
    docker compose exec -T db pg_dump -U couple_app -d couple_app --no-owner --no-privileges |
        Set-Content -LiteralPath (Join-Path $backupDir "database.sql") -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL backup failed" }
    docker compose cp backend:/app/data/uploads (Join-Path $backupDir "uploads")
    if ($LASTEXITCODE -ne 0) { throw "Upload backup failed" }
    @{
        created_at = (Get-Date).ToString("o")
        database = "database.sql"
        uploads = "uploads"
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backupDir "manifest.json") -Encoding utf8
    Write-Output "Backup created: $backupDir"
}
finally {
    Pop-Location
}
