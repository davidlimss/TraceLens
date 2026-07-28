# TraceLens AI

Investigasi log keamanan siber berbasis bukti dengan bantuan AI untuk operasi defensif.

[![Security and Quality](https://github.com/davidlimss/TraceLens/actions/workflows/security-quality.yml/badge.svg)](https://github.com/davidlimss/TraceLens/actions/workflows/security-quality.yml)
[![Project Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#status-proyek)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](backend/pyproject.toml)
[![Node.js 22](https://img.shields.io/badge/node-22-339933.svg)](frontend/package.json)

TraceLens mengubah log mentah heterogen menjadi event ternormalisasi, timeline deterministik, korelasi entitas, finding, risk score, dan kesimpulan berbantuan AI yang tetap dapat dilacak ke evidence asli.

> TraceLens adalah alat bantu investigasi, bukan otoritas respons insiden otonom. Keputusan berdampak tinggi tetap wajib ditinjau manusia.

## Status proyek

TraceLens saat ini berada pada tahap **alpha untuk riset dan engineering**. Repository ini memiliki baseline berorientasi production, tetapi belum tersertifikasi untuk penggunaan production tanpa pengawasan.

| Area | Kondisi saat ini |
|---|---|
| Scope produk | Masih dalam pengembangan |
| Quality | CI otomatis dan validasi lokal |
| Production readiness | Bersyarat; masih ada gap |
| Release | Proses terdokumentasi berorientasi SemVer |

## Prinsip utama

- Parsing, normalisasi timestamp, ordering, correlation, detection, dan risk scoring bersifat deterministik.
- LLM hanya memilih tool investigasi read-only dan menginterpretasikan evidence terstruktur.
- Setiap claim AI yang diterima wajib memiliki evidence valid dari case aktif.
- Claim diklasifikasikan sebagai `fact`, `inference`, atau `hypothesis`.
- Claim tanpa dukungan evidence dihapus oleh backend sebelum ditampilkan.
- Raw evidence menyimpan nomor baris sumber dan dilindungi dari perubahan.
- Jika bukti tidak cukup, sistem menghasilkan respons insufficient-evidence.

## Kemampuan

- Workspace investigasi berbasis case dan membership.
- Upload evidence dengan hash SHA-256.
- Parsing asynchronous menggunakan Redis dan Celery.
- Timeline deterministik lintas file.
- Event explorer dengan konteks sebelum dan sesudah.
- Korelasi IP, user, session, host, dan process.
- Finding detection dengan pemetaan MITRE ATT&CK.
- Risk scoring explainable dengan breakdown komponen.
- AI investigator dengan citation yang dapat diklik.
- Report formal Markdown dan PDF.
- Audit record untuk operasi sensitif.

## Format log

| Format | Input umum |
|---|---|
| Linux authentication | `auth.log`, `secure` |
| Web access | Apache/Nginx combined log |
| Generic application CSV | Header dan satu record per baris |
| Generic JSON/JSONL | Satu object per baris |
| Cowrie JSON | `cowrie.json` |
| Windows/Sysmon JSON | JSON hasil export |
| AWS CloudTrail JSONL | Satu event per baris |
| Suricata EVE JSON | `eve.json` |
| Logfmt | Log gaya Go dan Ollama |
| Plain text | Log UTF-8 |

Deteksi format berbasis isi file. Extension hanya menjadi salah satu sinyal validasi dan tidak memilih parser sendirian.

EVTX binary, PCAP, archive terkompresi, live SIEM streaming, dan tailing real-time belum didukung secara native. Export sumber tersebut terlebih dahulu ke JSON, JSONL, CSV, atau text.

## Arsitektur

```text
Browser
  |
  v
Next.js frontend :3001
  |
  v
FastAPI backend :8002 ----> PostgreSQL
  |                         cases, events, findings,
  |                         users, sessions, dan audit
  |
  +----> Redis ----> Celery worker / Celery Beat
  |                  parsing dan analysis
  |
  +----> Evidence volume
  |      file sumber dan hash immutable
  |
  +----> GitHub Models
         pemilihan tool dan interpretasi evidence
```

| Layer | Teknologi |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| API | FastAPI, Pydantic, SQLAlchemy |
| Database | PostgreSQL 16 |
| Queue | Redis 7, Celery |
| Scheduler | Celery Beat |
| LLM provider | GitHub Models |
| Deployment | Docker Compose |
| Monitoring | Prometheus metrics dan SLO rules |

Lihat [ARCHITECTURE.md](ARCHITECTURE.md) dan [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) untuk desain detail.

## Struktur repository

```text
TraceLens/
├── backend/                 FastAPI API, parser, engine, dan test
│   ├── app/parsers/         Deteksi isi dan parser canonical
│   ├── app/agent_tools.py   Tool investigasi read-only
│   ├── app/llm_gateway.py   Kontrol provider dan context compaction
│   ├── app/claim_verifier.py
│   ├── app/engine.py        Korelasi, detection, dan risk scoring
│   ├── alembic/             Database migration
│   ├── evals/               Harness evaluasi
│   └── tests/
├── frontend/                Console investigasi Next.js
├── monitoring/              Prometheus dan SLO
├── scripts/                 Validasi, backup, restore, dan smoke test
├── samples/                 Log aman untuk demonstrasi
├── docs/                    Desain, readiness, threat model, dan runbook
├── docker-compose.yml       Stack development
└── docker-compose.prod.yml  Baseline production yang di-hardening
```

## Menjalankan secara lokal

### Prasyarat

- Docker Desktop dengan Docker Compose.
- Git.
- Token GitHub Models dengan izin memakai model yang dikonfigurasi.
- Minimal 4 GB memory yang tersedia direkomendasikan.

### 1. Clone dan konfigurasi

```bash
git clone https://github.com/davidlimss/TraceLens.git
cd TraceLens
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Isi `.env` dengan nilai aman:

```dotenv
POSTGRES_PASSWORD=ganti-dengan-password-random-panjang
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=ganti-dengan-password-random-panjang
GITHUB_MODELS_TOKEN=token-github-models-kamu
GITHUB_MODELS_MODEL=openai/gpt-4.1
LLM_MAX_TOOL_CALLS=20
```

Jangan commit `.env`.

### 2. Jalankan stack

```bash
docker compose up -d --build
docker compose ps
```

Buka:

- Frontend: http://localhost:3001
- Backend API: http://localhost:8002
- Dokumentasi API: http://localhost:8002/docs
- Health: http://localhost:8002/health
- Readiness: http://localhost:8002/ready

Ikuti log:

```bash
docker compose logs -f backend worker frontend
```

Stop tanpa menghapus data:

```bash
docker compose down
```

Jangan gunakan `docker compose down -v` kecuali database dan evidence volume lokal memang ingin dihapus permanen.

## Alur investigasi

1. Login menggunakan akun bootstrap dari `.env`.
2. Buat case dari halaman utama.
3. Upload file log yang didukung.
4. Pilih mode `strict` atau `quarantine`.
5. Pantau status parsing dan analysis.
6. Tinjau dashboard, finding, timeline, dan detail event.
7. Ajukan pertanyaan terarah kepada AI investigator.
8. Verifikasi setiap claim melalui citation evidence.
9. Tinjau limitation dan evidence tambahan.
10. Export report formal.

Contoh pertanyaan:

```text
Apa yang terjadi pada case ini?
IP mana yang menghasilkan kegagalan authentication berulang?
Buat timeline insiden singkat dan sertakan evidence pendukung.
Finding mana yang harus segera ditinjau investigator?
Telemetry tambahan apa yang diperlukan untuk mengonfirmasi hypothesis utama?
```

## Pipeline analysis deterministik

```text
Upload
  -> validasi isi
  -> hash SHA-256
  -> deteksi format
  -> pilih parser
  -> normalisasi canonical event
  -> provenance timestamp
  -> stable ordering
  -> entity correlation
  -> detection rules
  -> risk scoring
  -> data finding dan report
```

Canonical event mempertahankan timestamp asli, timestamp normalisasi, asumsi timezone, identitas sumber, entity, nomor baris raw, parser version, confidence, dan tags.

## AI investigator dan claim verification

LLM tidak mengakses database secara langsung. LLM hanya dapat memanggil tool read-only yang dibatasi ke case aktif.

Tool utama:

- `search_events`
- `get_surrounding_events`
- `build_timeline`
- `correlate_entities`
- `get_raw_evidence`
- `generate_case_summary`

Backend memverifikasi status claim, keberadaan evidence, kepemilikan case, dukungan minimum inference/hypothesis, entity consistency, count consistency, limitation, dan overclaim.

Jawaban AI dibangun ulang hanya dari claim yang lolos verification gate.

## Kontrol keamanan

- Hash password PBKDF2-SHA256 dengan salt.
- Random session token disimpan sebagai hash.
- HttpOnly session cookie dan CSRF protection.
- Authorization berbasis role dan membership case.
- Child resource dibatasi oleh `case_id`.
- Validasi ukuran, filename, extension, MIME, UTF-8, dan isi upload.
- Penolakan path traversal dan absolute path.
- Nama file evidence internal berbasis UUID.
- ORM guard dan PostgreSQL trigger untuk raw event immutable.
- Redaction secret untuk PAT, bearer token, JWT, private key, password, dan cookie.
- Pengiriman raw log ke provider eksternal dimatikan secara default.
- Timeout agent, tool-call budget, repetition guard, dan no-progress guard.
- Audit event untuk authentication, upload, agent, integrity check, dan export.

Baca [SECURITY.md](SECURITY.md) dan [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) sebelum membuka service di luar environment development tepercaya.

## Konfigurasi utama

| Variable | Default | Kegunaan |
|---|---|---|
| `BACKEND_PORT` | `8002` | Port backend pada host |
| `FRONTEND_PORT` | `3001` | Port frontend pada host |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8002` | URL API browser |
| `CORS_ORIGINS` | `http://localhost:3001` | Origin frontend yang diizinkan |
| `SERVER_TIMEZONE` | `Asia/Jakarta` | Fallback timezone |
| `GITHUB_MODELS_ENDPOINT` | `https://models.github.ai/inference` | Endpoint provider |
| `GITHUB_MODELS_MODEL` | `openai/gpt-4.1` | Model tool-calling |
| `LLM_MAX_TOOL_CALLS` | `20` | Batas tool call per pertanyaan |
| `LLM_MAX_TOOL_RESULT_CHARACTERS` | `8000` | Batas context hasil tool |
| `LLM_MAX_OUTPUT_TOKENS` | `2048` | Budget output provider |
| `ALLOW_RAW_LOG_TO_EXTERNAL_PROVIDER` | `false` | Kebijakan raw evidence eksternal |

Lihat [.env.example](.env.example) untuk daftar lengkap.

## Validasi dan testing

```bash
pytest -q backend/tests
python backend/evals/run_eval.py
python backend/evals/run_detection_eval.py
```

Pada Windows, jalankan validasi lengkap:

```powershell
.\scripts\validate.ps1
```

## Baseline production

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Sebelum production, siapkan TLS/WAF, managed secret store, credential rotation, private network, immutable backup, evidence retention, monitoring, SLO alerting, dan security assessment independen.

## Troubleshooting

### `Failed to fetch`

```powershell
Invoke-RestMethod http://localhost:8002/ready
docker compose ps
docker compose logs --tail 100 backend frontend
```

Jika baru mengubah `.env`, recreate service:

```powershell
docker compose up -d --force-recreate backend worker frontend
```

Refresh browser dengan `Ctrl+F5`.

### Error authentication GitHub Models

- Pastikan token aktif dan memiliki izin GitHub Models.
- Pastikan `GITHUB_MODELS_MODEL` adalah ID model yang mendukung tool-calling.
- Jangan pernah mencetak atau commit token.

### Parsing job tetap queued

```bash
docker compose ps redis worker
docker compose logs --tail 200 worker redis
```

## Keterbatasan yang diketahui

- TraceLens bukan SIEM dan tidak menyediakan ingestion real-time native.
- EVTX, PCAP, archive terkompresi, dan threat intelligence eksternal belum termasuk.
- MFA, SSO, password recovery, dan lifecycle identity lengkap belum diimplementasikan.
- Evidence storage dan audit database belum WORM atau cryptographically signed.
- TLS, malware scanning, immutable object storage, dan external secret management membutuhkan integrasi deployment.
- Risk score bersifat heuristik dan belum dikalibrasi untuk setiap environment production.
- Evidence citation membuktikan traceability, bukan kebenaran absolut interpretasi.

Jangan gunakan TraceLens sebagai satu-satunya dasar kesimpulan hukum, attribution penyerang, atau respons insiden berdampak tinggi tanpa validasi manusia yang kompeten.

## Dokumentasi

- [Arsitektur](ARCHITECTURE.md)
- [Kebijakan keamanan](SECURITY.md)
- [Panduan kontribusi](CONTRIBUTING.md)
- [Pengembangan parser](docs/ADDING_A_PARSER.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Production readiness](docs/PRODUCTION_READINESS.md)
- [Build validation report](docs/BUILD_VALIDATION_REPORT.md)
- [Implementation report](docs/IMPLEMENTATION_REPORT.md)
- [Project charter](docs/PROJECT_CHARTER.md)
- [Roadmap](docs/ROADMAP.md)
- [RAID register](docs/RAID.md)
- [Decision log](docs/DECISIONS.md)
- [Release process](docs/RELEASE_PROCESS.md)
- [Changelog](CHANGELOG.md)
- [Support guide](SUPPORT.md)

## Kontribusi

Kontribusi dipersilakan. Baca [CONTRIBUTING.md](CONTRIBUTING.md), tambahkan test untuk perubahan perilaku, dan pertahankan evidence traceability serta case isolation.

## Lisensi

Lisensi open-source belum dideklarasikan. Sampai lisensi ditambahkan, seluruh hak tetap berada pada pemilik repository.
