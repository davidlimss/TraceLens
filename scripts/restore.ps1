param([Parameter(Mandatory=$true)][string]$DatabaseDump)
$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $DatabaseDump)) { throw "Dump not found: $DatabaseDump" }
Get-Content -Raw -LiteralPath $DatabaseDump | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U loginvestigator -d loginvestigator
docker compose exec -T backend alembic upgrade head
