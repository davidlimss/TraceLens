$ErrorActionPreference = "Stop"
Push-Location backend
try {
  pytest -q
  python evals/run_detection_eval.py
} finally { Pop-Location }
Push-Location frontend
try {
  npm run typecheck
  npm run build
} finally { Pop-Location }
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
Write-Output "TraceLens validation passed"
