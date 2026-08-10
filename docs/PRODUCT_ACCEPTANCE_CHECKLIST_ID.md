# Product Acceptance Checklist — TraceLens AI

Checklist ini dipakai sebelum demo resmi, beta internal, dan production
release. Setiap item harus memiliki bukti berupa log CI, test report, screenshot,
atau sign-off operator.

## Functional acceptance

- [ ] Investigator dapat membuat case dan membership dibuat otomatis.
- [ ] Upload valid menghasilkan SHA-256, evidence UUID, dan job Celery.
- [ ] File malformed dapat diproses dengan mode strict atau quarantine.
- [ ] Event, timeline, correlation, finding, dan risk dapat direplay.
- [ ] Chat membuat agent run dengan plan, tool trace, ledger, dan stop state.
- [ ] Claim fact/inference/hypothesis menampilkan citation dan limitation.
- [ ] Export Markdown/PDF memuat manifest evidence dan versi analisis.

## Failure-path acceptance

- [ ] Provider LLM 429/5xx menghasilkan status jujur dan tidak mengarang hasil.
- [ ] Tool timeout atau budget habis membuat run berhenti fail-closed.
- [ ] Evidence integrity mismatch memblokir export.
- [ ] Cross-case evidence ID selalu ditolak.
- [ ] Prompt injection di raw log tidak mengubah tool policy.
- [ ] Worker macet ditandai dan dapat di-retry.
- [ ] Database/Redis/storage gagal membuat readiness 503.

## Production configuration acceptance

- [ ] `APP_ENV=production` digunakan pada deployment target.
- [ ] `REQUIRE_MIGRATIONS=true` dan `SCHEMA_REVISION` sesuai Alembic head.
- [ ] Credential default diganti melalui secret manager.
- [ ] `SECURE_COOKIES=true` dan CORS berisi allowlist eksplisit.
- [ ] TLS/WAF, backup terenkripsi, retention, dan alert routing aktif.
- [ ] Evidence volume/database tidak diekspos ke internet publik.

## Evidence to attach

1. `pytest -q` report.
2. VIGIL and detection evaluation report.
3. Frontend typecheck/build report.
4. `alembic upgrade head` from empty and legacy database.
5. DAST, dependency, secret, and image scan report.
6. Backup/restore drill with measured RPO/RTO.
7. Staging E2E and load/soak result.
8. Named approver and expiry for every open risk.
