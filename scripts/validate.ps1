$ErrorActionPreference = "Stop"
Push-Location backend
try {
  pytest -q
  python evals/run_eval.py
  python evals/run_vigil_eval.py
  python evals/run_phase2_eval.py
  python evals/run_adversarial_eval.py
  python evals/run_detection_eval.py
} finally { Pop-Location }
Push-Location frontend
try {
  npm run typecheck
  npm run build
} finally { Pop-Location }
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
Write-Output "TraceLens validation passed"
