# Improvement Implementation Status

Dokumen ini merangkum hardening yang sudah diterapkan dari improvement plan. Batas evidence-grounded tetap berlaku: parsing, timestamp normalization, sorting, correlation, dan risk calculation adalah kode deterministik; LLM hanya merencanakan, memakai tool database read-only, dan menyusun interpretasi.

## Sudah diterapkan

- Timeline stabil lintas file dengan tie-breaker confidence, evidence file, nomor baris, dan event ID; provenance tahun/timezone dicatat.
- Session correlation diberi namespace host/source dan setiap correlation menyimpan alasan eksplisit.
- Risk score dinormalisasi 0–1, komponen dibatasi, diberi versi, breakdown, dan level kalibrasi.
- Authentication cookie HttpOnly, CSRF, global role, membership per-case, dan policy test cross-case.
- Claim contract multi-evidence: supporting/contradicting evidence, confidence, reasoning, limitations, dan kebutuhan bukti tambahan.
- Verification gate memeriksa kepemilikan evidence terhadap case, minimum bukti per status, entity/count/outcome dasar, serta membangun ulang jawaban hanya dari claim yang lolos.
- Raw log tidak dikirim ke provider eksternal secara default; tool output diberi delimiter dan secret redaction.
- Agent budget, timeout, repeated-tool/no-progress guard, serta state run persisten.
- Job parsing memiliki job ID, progress, heartbeat, retry, stuck-job detector, strict/quarantine mode, completeness, dan quarantine line.
- Integrity hash diverifikasi periodik dan sebelum export. Export parsing parsial membutuhkan acknowledgement eksplisit.
- Alembic baseline, Celery beat scheduler, security headers/CSP, upload validation, rate limiting, immutable raw fields, dan audit upload/chat/export.

## Validasi otomatis saat implementasi

- Backend: 44 test lulus, termasuk parser, timeline/correlation/risk, claim gate, prompt injection, insufficient evidence, auth, dan cross-case isolation.
- Frontend: production build dan TypeScript validation lulus.
- Docker Compose: PostgreSQL, Redis, backend, frontend, Celery worker, dan scheduler berhasil aktif; Alembic baseline berhasil dijalankan.
- Smoke API: login dan `/auth/me` berhasil, case dapat dibuat dengan CSRF, dan akses case tanpa autentikasi ditolak dengan HTTP 401.

## Belum dianggap production-ready

- Semantic entailment claim terhadap raw evidence masih validator deterministik terbatas, bukan pembuktian formal; investigator wajib membuka citation.
- Lifecycle user belum lengkap: belum ada UI password rotation/recovery, MFA/SSO, atau administrasi membership.
- Rate limit masih per-IP; belum per-user dan belum ada trusted-proxy production profile.
- Audit/database dan evidence filesystem belum WORM/cryptographically signed; administrator host/database tetap privileged.
- Belum ada TLS termination, external secret manager, antivirus scanning, object storage immutable, backup/restore drill, atau observability production.
- PDF masih memakai browser print dialog.

Item tersebut sengaja tidak disamarkan sebagai selesai dan harus menjadi gate sebelum deployment production.
