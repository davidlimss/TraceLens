# TraceLens AI

TraceLens AI adalah aplikasi investigasi log keamanan siber berbasis agentic AI yang mengubah log mentah heterogen menjadi event terstruktur, timeline insiden, korelasi entity, finding, risk score, dan jawaban AI yang dapat ditelusuri kembali ke baris log asli.

Prinsip utama aplikasi adalah **evidence-grounded investigation**:

- parsing, deteksi format, normalisasi timestamp, sorting, correlation, dan risk scoring dilakukan secara deterministik oleh Python;
- LLM hanya digunakan untuk memilih tool investigasi, melakukan interpretasi, menyusun hipotesis, chat, dan laporan;
- setiap claim AI harus memiliki status `fact`, `inference`, atau `hypothesis`;
- setiap claim harus merujuk `evidence_id` yang valid pada case aktif;
- backend memverifikasi claim sebelum respons ditampilkan;
- apabila bukti tidak mencukupi, sistem menjawab bahwa bukti belum cukup;
- raw log disimpan bersama nomor baris dan tidak boleh ditimpa setelah menjadi event.

## Daftar isi

- [Fitur MVP](#fitur-mvp)
- [Format log](#format-log-yang-didukung)
- [Arsitektur](#arsitektur-sistem)
- [Struktur proyek](#struktur-proyek)
- [Persyaratan](#persyaratan)
- [Menjalankan aplikasi](#menjalankan-aplikasi)
- [Credential login](#credential-login)
- [Cara menggunakan](#cara-menggunakan-aplikasi)
- [Konfigurasi AI](#konfigurasi-github-models)
- [Pipeline deterministik](#pipeline-ingestion-dan-analisis)
- [AI dan claim verification](#ai-investigator-dan-claim-verification)
- [Keamanan](#kontrol-keamanan)
- [API](#ringkasan-api)
- [Testing](#menjalankan-test)
- [Troubleshooting](#troubleshooting)
- [Batasan](#batasan-mvp)
- [Dokumentasi lanjutan](#dokumentasi-lanjutan)

## Fitur MVP

### Case management

- membuat case investigasi;
- membership dan permission per case;
- halaman dashboard untuk melihat ringkasan evidence, event, entity, rentang waktu, dan risiko;
- audit aktivitas penting pada case.

### Evidence ingestion

- drag-and-drop upload;
- validasi ukuran, extension, MIME type, UTF-8, nama file, dan format berdasarkan isi;
- perhitungan SHA-256 saat upload;
- file disimpan menggunakan nama UUID, bukan nama file dari pengguna;
- parsing asynchronous melalui Redis dan Celery;
- progress, heartbeat, retry, serta deteksi job macet;
- mode `strict` dan `quarantine`;
- verifikasi ulang hash secara manual, periodik, dan sebelum export.

### Analisis deterministik

- schema event kanonik;
- timestamp normalization dengan provenance dan confidence;
- timeline lintas file dengan urutan stabil;
- correlation berdasarkan IP, username, dan session;
- alasan correlation yang dapat dibaca manusia;
- deteksi brute force, password spraying, distributed guessing, suspicious PowerShell, web exploitation, persistence, dan privilege escalation;
- pemetaan MITRE ATT&CK, confidence evidence terpisah dari risk, pertimbangan false positive, dan query investigasi lanjutan;
- risk score 0–1 dengan breakdown komponen dan versi formula.

### AI Investigator

- single agent dengan beberapa database tools read-only;
- GitHub Models API, default `openai/gpt-4.1-mini`;
- supporting dan contradicting evidence;
- badge `fact`, `inference`, dan `hypothesis`;
- confidence, reasoning summary, limitations, dan kebutuhan evidence tambahan;
- citation yang dapat diklik untuk membuka raw log;
- claim verification gate di backend;
- jawaban insufficient-evidence bila tidak ada claim yang lolos.

### Reporting

- daftar finding dan risk breakdown;
- export Markdown;
- export PDF investigasi langsung dari backend;
- evidence hash, integrity status, completeness, dan versi transformasi pada laporan;
- acknowledgement wajib apabila evidence diproses dengan warning.

## Format log yang didukung

| Format | Contoh | Fokus parser |
|---|---|---|
| Linux auth/syslog | `auth.log`, `syslog` | SSH login gagal/berhasil, sudo, privilege event |
| Nginx/Apache | combined access log | IP, method, path, status, user-agent, timestamp |
| JSON/JSONL generik | satu object JSON per baris | timestamp, level, message, user, IP, session |
| CSV aplikasi generik | header dan satu record per baris | alias kolom umum untuk timestamp, level, message, user, IP |
| Cowrie JSON | `cowrie.json` | login, command, session, IP, dan username honeypot |
| Windows/Sysmon JSON | JSON export | 4624/4625, process creation, file creation, dan service install |
| AWS CloudTrail JSONL | satu event per baris | event name, identity, source IP, dan error outcome |
| Suricata EVE JSON | `eve.json` | network alert, source/destination, protocol, dan severity |
| Logfmt | Ollama dan aplikasi Go | timestamp, level, message, service, session, dan endpoint |
| Plain text fallback | UTF-8 line-oriented log | ingestion low-confidence tanpa klaim semantik berlebihan |

Deteksi format dilakukan dari pola baris awal file. Extension hanya menjadi salah satu lapisan validasi dan tidak menentukan parser sendirian.

Belum didukung secara native: binary Windows EVTX, PCAP, archive terkompresi, SIEM streaming, dan real-time tail. Format tersebut perlu diekspor lebih dahulu ke JSON/JSONL/CSV/text.

## Arsitektur sistem

```mermaid
flowchart LR
    U[Investigator] --> F[Next.js Frontend]
    F -->|Cookie session + CSRF| B[FastAPI Backend]
    B --> P[(PostgreSQL)]
    B --> R[(Redis)]
    B --> V[(Evidence Volume)]
    B -->|Enqueue job| W[Celery Worker]
    W --> R
    W --> V
    W --> P
    S[Celery Beat] --> R
    B -->|Tool calling| G[GitHub Models]
    G -->|Draft claims| B
    B --> C[Claim Verification Gate]
    C --> F
```

| Komponen | Teknologi | Tanggung jawab |
|---|---|---|
| Frontend | Next.js 15, React, CSS | Login, dashboard, upload, timeline, explorer, chat, finding, export |
| Backend | FastAPI, SQLAlchemy | Authentication, authorization, API, audit, query, orchestration agent |
| Database | PostgreSQL 16 | Case, user, membership, evidence, event, correlation, finding, agent run, audit |
| Queue | Redis 7 | Broker Celery, shared rate-limit counter, dan analysis lock |
| Worker | Celery | Parsing deterministik, progress job, correlation, finding, integrity job |
| Scheduler | Celery Beat | Deteksi stuck job dan verifikasi integrity berkala |
| LLM provider | GitHub Models | Tool selection dan interpretasi evidence |
| Evidence storage | Docker volume | File evidence asli dengan nama penyimpanan UUID |

## Struktur proyek

```text
loginvestigator-x/
├── backend/
│   ├── alembic/              # Database migration
│   ├── app/
│   │   ├── agent_tools.py    # Tool database read-only untuk agent
│   │   ├── auth.py           # Session, password hashing, CSRF, permission
│   │   ├── claim_verifier.py # Verification gate claim AI
│   │   ├── engine.py         # Timeline, correlation, finding, risk
│   │   ├── llm_gateway.py    # GitHub Models tool-calling gateway
│   │   ├── main.py           # FastAPI endpoints
│   │   ├── models.py         # SQLAlchemy models
│   │   ├── parsers.py        # Parser deterministik
│   │   ├── security.py       # Upload validation dan rate limiting
│   │   ├── tasks.py          # Celery parsing/integrity tasks
│   │   └── worker.py         # Celery configuration
│   ├── tests/                # Test backend
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── app/                  # Next.js App Router pages
│   ├── components/           # UI reusable
│   ├── lib/                  # API client dan TypeScript types
│   ├── Dockerfile
│   └── next.config.ts
├── docs/                     # Arsitektur, threat model, parser guide
├── samples/                  # Contoh log
├── docker-compose.yml
├── .env.example
└── README.md
```

## Persyaratan

Cara yang direkomendasikan menggunakan Docker Compose:

- Windows 10/11, Linux, atau macOS;
- Docker Desktop/Docker Engine;
- Docker Compose v2;
- koneksi internet saat build pertama dan ketika menggunakan GitHub Models;
- GitHub Models token dengan permission yang sesuai untuk memakai model.

Untuk development tanpa Docker dibutuhkan Python 3.12, Node.js 22, PostgreSQL, dan Redis.

## Menjalankan aplikasi

### 1. Siapkan environment

PowerShell:

```powershell
Copy-Item .env.example .env
```

Bash:

```bash
cp .env.example .env
```

Edit `.env`, kemudian minimal ganti nilai berikut:

```env
POSTGRES_PASSWORD=ganti-password-database
DATABASE_URL=postgresql+psycopg://loginvestigator:ganti-password-database@postgres:5432/loginvestigator
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=ganti-password-admin
GITHUB_MODELS_TOKEN=isi-token-baru-di-sini
```

Jangan commit `.env`. File tersebut sudah tercantum di `.gitignore`. Jangan menaruh token asli di `.env.example`.

### 2. Build dan jalankan service

```powershell
docker compose up -d --build
```

Baseline hardening produksi (jalankan di belakang HTTPS dengan secret non-default):

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Observability tersedia melalui `/metrics`; SLO, launch gate, dan runbook terdapat di `docs/SLO.md`, `docs/PRODUCTION_READINESS.md`, dan `docs/runbooks/`.

Periksa status:

```powershell
docker compose ps
```

Service utama:

- Frontend: http://localhost:3001
- Login: http://localhost:3001/login
- Backend API: http://localhost:8002
- Swagger UI: http://localhost:8002/docs
- Health check: http://localhost:8002/health

### 3. Melihat log service

```powershell
docker compose logs -f backend frontend worker scheduler
```

Tekan `Ctrl+C` untuk keluar dari tampilan log tanpa menghentikan container.

### 4. Menghentikan aplikasi

```powershell
docker compose down
```

Perintah tersebut tidak menghapus volume PostgreSQL atau evidence. Untuk keamanan, jangan memakai `docker compose down -v` kecuali benar-benar ingin menghapus seluruh database dan evidence lokal.

## Credential login

Credential dibaca dari `.env`:

```env
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=change-me-local
```

Nilai di atas hanya default development. Ganti password sebelum aplikasi dapat diakses perangkat lain.

Bootstrap admin dibuat saat startup pertama jika username tersebut belum ada. Mengubah password di `.env` setelah user sudah tersimpan tidak otomatis mengganti password record lama di PostgreSQL.

## Cara menggunakan aplikasi

### 1. Login

1. Buka http://localhost:3001/login.
2. Masukkan credential bootstrap dari `.env`.
3. Setelah berhasil, browser menyimpan session HttpOnly dan CSRF cookie.

### 2. Membuat case

1. Pada halaman awal, masukkan nama case.
2. Tekan **Buat investigasi**.
3. Aplikasi membuka dashboard case dan menghasilkan UUID case.

Simpan UUID tersebut jika perlu membuka kembali case dari halaman awal.

### 3. Mengunggah log

1. Pilih menu **Unggah**.
2. Pilih mode parsing:
   - `strict`: satu baris malformed menggagalkan parsing file;
   - `quarantine`: baris malformed dicatat terpisah dan event valid tetap diproses.
3. Drag-and-drop file atau pilih melalui file picker.
4. Tunggu upload selesai dan monitor progress parsing.

Status umum:

| Status | Arti |
|---|---|
| `queued` | Job menunggu worker |
| `parsing` | Worker sedang membaca dan memproses file |
| `parsed` | Seluruh file berhasil diproses |
| `parsed_with_warnings` | Selesai dengan baris quarantine |
| `failed` | Parsing gagal secara eksplisit |
| `stuck` | Heartbeat job melewati batas waktu |

### 4. Menelaah timeline dan event

- **Timeline** menampilkan event lintas file dengan urutan deterministik.
- Filter dapat membatasi severity dan source.
- Klik event untuk melihat raw log asli dan metadata timestamp.
- **Penjelajah** menyediakan tabel, search/filter, serta context sebelum dan sesudah event.

### 5. Memakai AI Investigator

1. Buka menu **Penyidik AI**.
2. Ajukan pertanyaan, misalnya `Apa yang terjadi pada case ini?`.
3. Periksa badge claim dan confidence.
4. Klik setiap evidence citation untuk membuka raw log.
5. Baca limitations dan evidence tambahan yang disarankan untuk inference/hypothesis.

AI bukan pengganti verifikasi investigator. Citation valid membuktikan bahwa evidence ada pada case, sedangkan kebenaran interpretasi tetap harus ditinjau manusia.

### 6. Mengekspor laporan

1. Buka **Temuan & Laporan**.
2. Tinjau risk breakdown dan evidence IDs.
3. Jika terdapat `parsed_with_warnings`, centang acknowledgement.
4. Pilih export Markdown atau **Unduh PDF Investigasi**.

Backend memverifikasi ulang hash evidence sebelum export. Export diblokir apabila integrity mismatch ditemukan.

PDF memuat ringkasan case, rundown maksimal 100 event, temuan rule-based, risk heuristik, evidence ID,
manifest SHA-256, status integritas, serta versi parser, prompt, tool, dan model.

### Menjalankan evaluation harness

Harness offline tidak membutuhkan token atau koneksi provider:

```powershell
cd backend
python evals\run_eval.py --output eval-results.json
```

Perintah keluar dengan kode `1` apabila pass rate berada di bawah quality gate. Untuk mengubah gate:

```powershell
python evals\run_eval.py --min-pass-rate 0.90
```

Evaluasi live terhadap agent dan case nyata membutuhkan `GITHUB_MODELS_TOKEN` serta database aplikasi aktif:

```powershell
python evals\run_eval.py --live-case UUID-CASE --output live-eval-results.json
```

Mode live mengukur evidence grounding, pemeriksaan overclaim dasar, jumlah claim, latency, putaran agent,
dan tool calls. Golden cases dapat ditambah di `backend/evals/golden_cases.json`.

## Konfigurasi GitHub Models

Aplikasi memakai GitHub Models API, bukan endpoint internal GitHub Copilot.

```env
GITHUB_MODELS_TOKEN=replace-with-a-github-models-token
GITHUB_MODELS_ENDPOINT=https://models.github.ai/inference
GITHUB_MODELS_MODEL=openai/gpt-4.1-mini
```

Model harus mendukung tool/function calling dan structured JSON response yang dipakai agent. Mengganti model tanpa regression test dapat mengubah kualitas pemilihan tool dan format claim.

Setelah mengubah konfigurasi:

```powershell
docker compose up -d --force-recreate backend worker scheduler
```

Periksa bahwa token masuk tanpa menampilkan nilainya:

```powershell
docker compose exec backend python -c "from app.config import Settings; print('Token aktif:', bool(Settings().github_models_token))"
```

Konfigurasi proteksi provider:

```env
ALLOW_RAW_LOG_TO_EXTERNAL_PROVIDER=false
LLM_MAX_TOOL_ROUNDS=8
LLM_MAX_TOOL_CALLS=20
LLM_MAX_SAME_TOOL_REPETITION=2
LLM_NO_PROGRESS_LIMIT=2
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOOL_RESULT_CHARACTERS=20000
```

Secara default, raw log tidak dikirim ke provider eksternal. Structured event yang dibutuhkan agent tetap diperlakukan sebagai untrusted data dan mengalami secret redaction.

## Pipeline ingestion dan analisis

```text
Upload
  -> filename/size/MIME/content validation
  -> SHA-256 streaming
  -> evidence UUID storage
  -> Celery job
  -> content-based format detection
  -> deterministic parsing
  -> canonical event mapping
  -> timestamp normalization + provenance
  -> stable timeline ordering
  -> rule-based correlation
  -> rule-based findings
  -> explainable risk score
  -> audit record
```

Setiap event menyimpan minimal:

- `event_id` sebagai evidence citation ID;
- `case_id` dan `evidence_file_id`;
- timestamp original dan normalized;
- timezone, confidence, assumptions, year source, dan timezone source;
- source type/name dan host;
- category, action, outcome, severity;
- username, IP, session, process, dan filename bila tersedia;
- `raw_log` dan `raw_line_number`;
- parser name, parser confidence, dan tags.

### Stable timeline ordering

Timeline diurutkan menggunakan:

```text
timestamp_normalized ASC
timestamp_confidence DESC
evidence_file_id ASC
raw_line_number ASC
event_id ASC
```

Dengan demikian, timestamp identik tetap menghasilkan urutan yang reproducible.

### Correlation

Correlation memakai shared entity dalam window waktu konfigurabel:

```env
CORRELATION_WINDOW_MINUTES=10
```

Contoh alasan yang disimpan:

```text
shared source_ip within 10 minutes
```

Session diberi namespace berdasarkan host dan source type agar identifier generik dari sistem berbeda tidak langsung digabungkan.

### Risk scoring

Formula deterministik:

```text
risk_score =
  severity_weight * 0.30
  + frequency_score * 0.20
  + privilege_weight * 0.25
  + correlation_count * 0.15
  + novelty_score * 0.10
```

Hasil dinormalisasi 0–1. Breakdown menyimpan value, weight, contribution, cap, risk version, threshold version, dan risk level.

## AI Investigator dan claim verification

Agent hanya dapat memakai tool berikut:

1. `search_events(case_id, filters)`
2. `get_surrounding_events(event_id, window)`
3. `build_timeline(case_id)`
4. `correlate_entities(case_id, entity)`
5. `get_raw_evidence(event_id)`
6. `generate_case_summary(case_id)`

Tool registry mengunci akses ke case dari URL aktif. Tool call yang mencoba mengambil case lain ditolak.

Respons agent berbentuk:

```json
{
  "answer": "Narasi yang dibangun ulang dari claim valid.",
  "claims": [
    {
      "claim_id": "claim-1",
      "text": "Terjadi beberapa kegagalan autentikasi dari IP yang sama.",
      "status": "inference",
      "evidence_id": "EVENT_UUID",
      "supporting_evidence_ids": ["EVENT_UUID_1", "EVENT_UUID_2"],
      "contradicting_evidence_ids": [],
      "entities": {"source_ip": "192.0.2.10"},
      "confidence": 0.78,
      "reasoning_summary": "Event gagal terjadi berulang dalam window waktu yang berdekatan.",
      "limitations": ["Tidak tersedia telemetry endpoint tujuan lainnya."],
      "required_additional_evidence": []
    }
  ]
}
```

Verification gate memeriksa:

- status claim termasuk enum yang diizinkan;
- evidence UUID benar-benar ada pada case aktif;
- minimum supporting evidence berdasarkan jenis claim;
- inference memiliki reasoning dan limitations;
- hypothesis menyebut limitations dan kebutuhan evidence tambahan;
- entity, outcome, serta count sederhana konsisten dengan event;
- claim interpretif berlebihan tidak disamarkan sebagai `fact`.

Jika tidak ada claim yang lolos:

```text
Belum cukup bukti untuk menjawab pertanyaan ini.
```

## Kontrol keamanan

### Authentication dan authorization

- password disimpan menggunakan PBKDF2-SHA256 dengan salt;
- session token acak disimpan sebagai hash di database;
- session browser menggunakan cookie HttpOnly;
- request mutating dilindungi CSRF double-submit;
- role: viewer, investigator, reviewer, dan admin;
- membership dan permission diperiksa per case;
- query child-resource selalu di-scope dengan `case_id`.

### Upload

- ukuran maksimum default 50 MiB;
- allowlist extension dan MIME;
- validasi isi UTF-8 dan supported format;
- path traversal dan absolute path ditolak;
- evidence disimpan menggunakan UUID;
- SHA-256 dihitung saat streaming;
- raw event memiliki ORM guard dan PostgreSQL immutability trigger.

### AI boundary

- tools database read-only;
- active-case binding;
- raw/tool content dianggap untrusted data;
- secret redaction untuk PAT, bearer token, JWT, private key, password, token, dan cookie;
- raw log tidak dikirim ke provider secara default;
- timeout, tool-call budget, repetition guard, dan no-progress guard;
- jawaban model tidak ditampilkan sebelum claim verification.

### Audit dan integrity

Audit mencatat antara lain:

- login/logout;
- pembuatan case;
- upload diterima atau ditolak;
- parser/model/prompt/tool schema version;
- jawaban agent dan evidence IDs;
- export laporan;
- integrity verification.

Audit aplikasi belum cryptographically signed atau WORM. Administrator database/host tetap merupakan privileged trust boundary.

## Ringkasan API

Semua endpoint case memerlukan session dan permission yang sesuai. Endpoint `POST` juga memerlukan CSRF token.

| Method | Endpoint | Fungsi |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/auth/login` | Membuat session login |
| POST | `/auth/logout` | Menghapus session |
| GET | `/auth/me` | Identitas user aktif |
| POST | `/cases` | Membuat case |
| POST | `/cases/{case_id}/logs` | Upload evidence dan enqueue parsing |
| GET | `/cases/{case_id}/logs` | Daftar evidence |
| GET | `/cases/{case_id}/logs/{file_id}` | Detail evidence |
| GET | `/cases/{case_id}/jobs/{job_id}` | Progress parsing job |
| POST | `/cases/{case_id}/jobs/{job_id}/retry` | Retry failed/stuck job |
| POST | `/cases/{case_id}/logs/{file_id}/verify` | Verifikasi ulang SHA-256 |
| GET | `/cases/{case_id}/events` | Event pagination dan filter |
| GET | `/cases/{case_id}/events/{event_id}` | Event, raw log, before/after context |
| GET | `/cases/{case_id}/timeline` | Timeline dan correlation |
| GET | `/cases/{case_id}/entities` | Ringkasan IP/user/session |
| GET | `/cases/{case_id}/findings` | Finding dan risk breakdown |
| POST | `/cases/{case_id}/chat` | AI Investigator |
| POST | `/cases/{case_id}/exports` | Export Markdown/PDF request |

Dokumentasi request/response interaktif tersedia di http://localhost:8002/docs.

## Konfigurasi environment

| Variable | Default development | Kegunaan |
|---|---:|---|
| `BACKEND_PORT` | `8002` | Port API pada host |
| `FRONTEND_PORT` | `3001` | Port frontend pada host |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8002` | URL API dari browser |
| `CORS_ORIGINS` | `http://localhost:3001` | Origin frontend yang diizinkan |
| `SERVER_TIMEZONE` | `Asia/Jakarta` | Asumsi timezone bila log tidak memilikinya |
| `MAX_UPLOAD_BYTES` | `52428800` | Batas upload dalam byte |
| `UPLOAD_RATE_LIMIT` | `10` | Upload per window per IP |
| `CHAT_RATE_LIMIT` | `20` | Chat per window per IP |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Window rate limit |
| `CORRELATION_WINDOW_MINUTES` | `10` | Window correlation entity |
| `BRUTE_FORCE_WINDOW_MINUTES` | `10` | Window brute-force rule |
| `BRUTE_FORCE_THRESHOLD` | `5` | Minimum kegagalan untuk finding |
| `SESSION_TTL_HOURS` | `12` | Masa berlaku session |
| `SECURE_COOKIES` | `false` | Harus `true` ketika memakai HTTPS production |
| `STUCK_JOB_MINUTES` | `10` | Batas heartbeat parsing job |
| `INTEGRITY_CHECK_INTERVAL_SECONDS` | `86400` | Interval integrity scheduler |

Lihat [.env.example](.env.example) untuk daftar lengkap.

## Menjalankan test

### Dari container

```powershell
docker compose exec backend pytest -q
```

Expected result saat dokumentasi ini diperbarui:

```text
52 passed
```

### Secara lokal

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
```

### Build frontend

```powershell
cd frontend
npm ci
npm run build
```

Test mencakup parser valid/malformed/missing fields, Windows/CloudTrail/Cowrie/logfmt, timeline, correlation, risk dan confidence, detection MITRE, claim verification, insufficient evidence, prompt injection, auth, upload security, path traversal, dan cross-case isolation.

### Benchmark detection

```powershell
cd backend
python evals\run_detection_eval.py --output detection-eval-results.json
```

Benchmark melaporkan true positive, false positive, false negative, precision, recall, dan F1. Dataset bawaan adalah golden set internal terkontrol dan tidak boleh diperlakukan sebagai bukti performa pada seluruh lingkungan produksi.

## Operasional Docker

Restart satu service:

```powershell
docker compose restart backend
docker compose restart frontend
```

Rebuild setelah perubahan kode:

```powershell
docker compose up -d --build
```

Melihat penggunaan resource:

```powershell
docker stats
```

Masuk ke shell backend:

```powershell
docker compose exec backend sh
```

Melihat revision database:

```powershell
docker compose exec backend alembic current
```

## Troubleshooting

### Halaman hanya berwarna gelap atau kosong

1. Pastikan frontend aktif: `docker compose ps`.
2. Lakukan hard refresh `Ctrl+Shift+R`.
3. Periksa `docker compose logs --tail 100 frontend`.
4. Pastikan membuka `http://localhost:3001`, bukan port backend.

### Halaman login reload terus

Versi terbaru sudah mencegah redirect loop `/auth/me` 401 pada halaman login. Rebuild frontend dan bersihkan cache:

```powershell
docker compose up -d --build frontend
```

Kemudian tekan `Ctrl+Shift+R`.

### Login gagal

- cek `BOOTSTRAP_ADMIN_USERNAME` dan `BOOTSTRAP_ADMIN_PASSWORD` di `.env`;
- ingat bahwa mengganti `.env` tidak mengubah password user yang sudah tersimpan;
- lihat log: `docker compose logs --tail 100 backend`.

### `GitHub Models API request failed`

- pastikan `GITHUB_MODELS_TOKEN` aktif dan belum expired/revoked;
- pastikan model ID benar;
- pastikan akun/token mempunyai akses GitHub Models;
- cek koneksi internet container;
- lihat error backend tanpa membagikan token.

```powershell
docker compose logs --tail 100 backend
```

### Upload berhenti di queued

```powershell
docker compose ps worker redis
docker compose logs --tail 100 worker redis
```

Pastikan worker dan Redis aktif. Job failed/stuck dapat di-retry melalui endpoint/UI yang tersedia.

### Port sudah digunakan

Ubah `.env`:

```env
BACKEND_PORT=8012
FRONTEND_PORT=3011
NEXT_PUBLIC_API_URL=http://localhost:8012
CORS_ORIGINS=http://localhost:3011
```

Kemudian rebuild frontend dan backend.

### Reset total development

Peringatan: perintah berikut menghapus database dan evidence volume lokal secara permanen.

```powershell
docker compose down -v
docker compose up -d --build
```

Gunakan hanya jika seluruh data development boleh dibuang.

## Menambah parser baru

Menambah format parser adalah perubahan eksplisit terhadap scope dan harus disetujui terlebih dahulu.

Secara umum:

1. tambah deteksi format berbasis konten;
2. implementasikan parser deterministik tanpa LLM;
3. map ke `ParsedEvent` dan schema kanonik;
4. simpan raw line tanpa modifikasi;
5. tetapkan parser name/version dan confidence;
6. tambahkan test valid, missing field, malformed, dan detection ambiguity;
7. dokumentasikan timestamp serta timezone assumptions.

Panduan lengkap: [docs/ADDING_A_PARSER.md](docs/ADDING_A_PARSER.md).

## Batasan MVP

- bukan SIEM dan belum menerima real-time ingestion;
- belum mendukung Windows EVTX, PCAP, cloud audit, container log, atau threat intelligence eksternal;
- rate limit masih per-IP, bukan per-user;
- lifecycle user belum lengkap: belum ada UI password rotation/recovery, MFA, atau SSO;
- claim verifier melakukan pemeriksaan semantik deterministik terbatas, bukan formal proof;
- investigator tetap wajib memeriksa raw evidence;
- filesystem evidence dan audit database belum WORM atau cryptographically signed;
- belum ada TLS termination, external secret manager, antivirus scanning, dan object storage immutable;
- PDF dibatasi pada 100 event timeline per laporan agar ukuran dan waktu generasi tetap terkendali;
- risk formula bersifat heuristic dan belum dikalibrasi menggunakan corpus insiden berlabel;
- CSV multiline quoted record belum didukung.

Jangan gunakan MVP ini sebagai satu-satunya dasar keputusan hukum, atribusi attacker, atau respons insiden berisiko tinggi tanpa validasi investigator manusia.

## Dokumentasi lanjutan

- [Arsitektur dan gap analysis](docs/ARCHITECTURE.md)
- [Threat model MVP](docs/THREAT_MODEL.md)
- [Status improvement implementation](docs/IMPROVEMENT_IMPLEMENTATION_STATUS.md)
- [Panduan menambah parser](docs/ADDING_A_PARSER.md)
- [Cakupan ide produk dan roadmap](docs/PRODUCT_SCOPE_IDEAS.md)

## Status verifikasi

Pada validasi terakhir:

- Docker Compose menjalankan PostgreSQL, Redis, FastAPI, Next.js, Celery worker, dan Celery Beat;
- Alembic migration berhasil dijalankan saat backend startup;
- backend test suite: **44 passed**;
- Next.js production build berhasil;
- endpoint API dan halaman login merespons HTTP 200;
- akses case tanpa session ditolak dengan HTTP 401.

---

TraceLens AI adalah alat bantu investigasi. Nilai utamanya bukan sekadar menghasilkan narasi AI, melainkan menjaga agar setiap narasi dapat diperiksa kembali terhadap evidence asli.
