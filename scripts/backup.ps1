param([string]$OutputDirectory = ".\backups")
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$database = Join-Path $OutputDirectory "tracelens-$stamp.sql"
docker compose exec -T postgres pg_dump -U loginvestigator -d loginvestigator | Set-Content -Encoding utf8 $database
Get-FileHash -Algorithm SHA256 $database | Format-List | Set-Content "$database.sha256.txt"
Write-Output $database
