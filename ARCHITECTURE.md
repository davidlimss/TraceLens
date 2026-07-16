# TraceLens AI Architecture

## System context

```text
SOC Analyst
    │ HTTPS + session/CSRF
    ▼
Next.js UI ───────► FastAPI API ───────► PostgreSQL
                         │                    │
                         ├──── Redis ◄──── Celery worker/beat
                         │
                         ├──── evidence volume / production object storage
                         ├──── GitHub Models (optional, redacted tool context)
                         └──── Prometheus metrics
```

## Investigation flow

```text
Create case → upload evidence → validate type/size/UTF-8 → hash + immutable storage
→ asynchronous deterministic parsing → normalized events → correlations/detections
→ analyst triage/disposition → evidence-grounded AI assistance → formal report
```

Deterministic parsing, correlations, findings, risk, and confidence remain the system of record. The LLM is an investigation assistant and must cite stored evidence; it does not silently create canonical events or findings.

## Trust boundaries

- Browser/API: authenticated session, strict SameSite cookie, CSRF on mutations, CORS allowlist.
- Upload/API: filename, MIME, size, UTF-8, path and parsing-mode validation.
- API/worker: database-backed job state and Redis queue; evidence referenced by generated ID.
- External LLM: raw log forwarding disabled by default; tool rounds, repetitions, timeout and result size are bounded.
- Report consumer: output identifies automation, confidence, limitations, evidence IDs and required analyst verification.

## Data ownership

PostgreSQL owns cases, membership, normalized events, findings, workflow and audit records. Evidence bytes live in immutable storage and are linked by SHA-256. Redis is disposable coordination state and is not authoritative.

## Failure behavior

- Invalid evidence is rejected or quarantined without becoming a trusted event.
- Worker failures retain job status and can be retried.
- LLM unavailability does not block deterministic investigation and reporting.
- Readiness fails when PostgreSQL is unavailable; SLO metrics expose request failures and latency.
