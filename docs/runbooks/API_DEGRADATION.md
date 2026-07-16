# Runbook: API Degradation

1. Confirm `/ready`, database health, Redis health, queue depth, and recent deployment changes.
2. If impact follows a release, roll back to the last verified image; otherwise reduce ingestion concurrency and preserve interactive traffic.
3. Check 5xx route breakdown and latency histogram, then capture correlation IDs and container logs for the incident record.

Escalate when availability burn persists for 15 minutes, evidence ingestion stops, authentication is unavailable, or integrity verification fails. Do not delete evidence or bypass integrity controls as mitigation.
