# TraceLens AI — Jalur Produk 10/10

Dokumen ini menetapkan arti “10/10” secara engineering. Angka tersebut bukan
janji bahwa sistem bebas bug atau sudah bersertifikasi. Nilai 10/10 hanya boleh
diberikan jika seluruh gate teknis, keamanan, operasional, dan lingkungan telah
lulus serta dibuktikan pada deployment target.

## Posisi saat ini

TraceLens sudah melewati fase demonstrator sederhana. Fondasinya adalah
production-oriented investigation platform dengan:

- parser, timeline, correlation, detection, dan risk yang deterministik;
- evidence hash dan immutable provenance;
- case-scoped read-only tools dan MCP;
- single-agent VIGIL dengan plan, hypothesis, checkpoint, repair terbatas, dan
  stop state;
- claim verification gate serta human-in-the-loop;
- PostgreSQL, Redis, Celery, Prometheus, Docker Compose, test, dan evaluasi
  golden set.

Perubahan pada fase productization ini menutup gap penting berikut:

1. schema database tidak lagi diubah oleh proses API saat startup;
2. versi schema wajib cocok dengan Alembic head sebelum aplikasi melayani;
3. `/ready` memeriksa database, Redis, dan evidence storage;
4. login memiliki rate limit per IP dan per username;
5. API menambahkan request ID dan security response headers;
6. konfigurasi production menolak credential default, cookie tidak aman, dan
   CORS wildcard.

## Definisi produk yang dapat dipertanggungjawabkan

### Reliability

- API liveness dan readiness terpisah.
- Worker dan scheduler memiliki watchdog untuk job/run yang macet.
- Parsing memiliki retry terkontrol dan per-case lock.
- Database migration berjalan sebelum API; runtime tidak melakukan DDL.
- Backup dan restore diuji pada lingkungan terisolasi.

### Security

- Case authorization dan CSRF wajib untuk operasi mutatif.
- Login, upload, dan chat dibatasi rate limit.
- Evidence disimpan dengan UUID, hash SHA-256, dan guard immutable.
- Raw log diperlakukan sebagai untrusted data.
- Tool agent read-only, allowlisted, bounded, dan case-scoped.
- Production memerlukan TLS/secure cookie, secret manager, dan CORS allowlist.

### Agentic quality

- Agent mengikuti loop plan → tool → observation → verify → stop.
- State durable menyimpan plan, hypothesis, gap, provenance, dan next action.
- Investigator dapat pause, cancel, dan resume.
- Claim yang ditampilkan harus lolos evidence gate.
- Repair maksimal terbatas dan fail-closed.
- Tidak ada active response otomatis.

### Operability

- Request ID menghubungkan request dengan audit/log trace.
- Prometheus memantau latency, error, finding queue, dan provider failure.
- SLO, runbook, release checklist, dan security scan menjadi artefak wajib.
- Model, prompt, graph, parser, tool, dan risk version tercatat.

## Release gates menuju 10/10

### Gate A — engineering

- [ ] Semua unit/integration test lulus.
- [ ] Frontend typecheck dan production build lulus.
- [ ] Alembic upgrade dari database kosong lulus.
- [ ] Alembic upgrade dari database legacy lulus.
- [ ] Migration downgrade hanya diperbolehkan untuk schema non-evidence;
      migration evidence tetap fail-closed.
- [ ] Concurrency ingestion dan incremental/full rebuild equivalence diuji.

### Gate B — AI dan evidence

- [ ] VIGIL golden state evaluation lulus.
- [ ] Claim evidence validity, semantic support, cross-case isolation, dan
      insufficient-evidence honesty lulus.
- [ ] Prompt-injection corpus lulus tanpa tool policy bypass.
- [ ] Provider failure, timeout, 429, malformed JSON, dan resume diuji.
- [ ] Citation correctness dinilai oleh reviewer, bukan hanya UUID valid.

### Gate C — security

- [ ] Dependency audit, secret scan, image scan, dan DAST lulus.
- [ ] TLS/WAF, secure headers, secret rotation, dan least privilege diterapkan.
- [ ] Audit sink immutable/tamper-evident ditetapkan.
- [ ] Retention, privacy classification, legal hold, dan export authorization
      ditetapkan.

### Gate D — operasi

- [ ] Backup evidence-inclusive dipulihkan dan RPO/RTO tercatat.
- [ ] Soak/load test memakai ukuran evidence yang representatif.
- [ ] Alert routing, on-call owner, dan runbook diuji.
- [ ] Capacity limit PostgreSQL, Redis, evidence storage, dan queue ditentukan.
- [ ] Staging E2E browser test untuk upload → parse → timeline → chat → export
      lulus.

## Skala penilaian

| Skor | Makna |
|---:|---|
| 6–7 | MVP berjalan, tetapi hardening dan bukti operasi masih minim |
| 8 | Strong MVP/research prototype dengan agentic loop nyata |
| 9 | Beta operasional untuk tim terbatas, gate engineering dan security dasar lulus |
| 10 | Release produk pada deployment target setelah seluruh Gate A–D ditandatangani |

Saat ini label yang jujur adalah **production-oriented beta foundation** setelah
perubahan hardening kode ini; belum boleh disebut 10/10 sebelum gate lingkungan
ditutup.

## Hal yang sengaja tidak dijadikan syarat 10/10

- bukan forensic-grade formal evidence;
- bukan pengganti SOC analyst;
- bukan zero-hallucination system;
- bukan SIEM penuh;
- bukan active-response platform;
- bukan multi-agent kosmetik.

Nilai produk berasal dari keterlacakan, batas kewenangan, reproducibility, dan
kejujuran saat bukti tidak cukup.
