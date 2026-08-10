# Bedah Struktur Aplikasi TraceLens AI / VIGIL

Dokumen ini menjelaskan TraceLens AI dari sudut pandang sistem: tujuan,
komponen, struktur repository, aliran data, database, agentic loop, MCP,
keamanan, deployment, dan batas kemampuan.

Status sistem: **production-oriented beta foundation**. Sistem belum
forensic-grade, bukan pengganti SOC analyst, bukan SIEM penuh, dan tidak
menjalankan active response seperti memblokir IP atau menonaktifkan akun.

## 1. Inti aplikasi

TraceLens menerima log keamanan, menyimpannya sebagai evidence yang dapat
ditelusuri, memprosesnya secara deterministik menjadi event, timeline, dan
finding, lalu menyediakan investigator AI bounded yang boleh mencari evidence
melalui tools read-only dan hanya menampilkan claim yang lolos verifikasi.

Kalimat presentasi:

> TraceLens AI adalah workspace investigasi log berbasis case yang memisahkan
> pemrosesan deterministik dari reasoning LLM, menggunakan tools read-only yang
> case-scoped, dan memverifikasi setiap kesimpulan terhadap evidence aktif.

## 2. Cara berpikir tentang sistem

~~~text
┌─────────────────────────────────────────────────────────────┐
│ 1. Presentation: Next.js UI                                │
│    Investigator membuat case, upload log, melihat hasil    │
├─────────────────────────────────────────────────────────────┤
│ 2. Control/API: FastAPI                                    │
│    Auth, CSRF, case permission, endpoint, orchestration    │
├─────────────────────────────────────────────────────────────┤
│ 3. Deterministic analysis                                  │
│    Parser, canonical event, timeline, correlation, rules   │
├─────────────────────────────────────────────────────────────┤
│ 4. Agentic investigation                                   │
│    VIGIL plan, tool loop, state, hypothesis, verifier      │
├─────────────────────────────────────────────────────────────┤
│ 5. Data/infrastructure                                     │
│    PostgreSQL, Redis, Celery, evidence, MCP/SIEM           │
└─────────────────────────────────────────────────────────────┘
~~~

LLM tidak boleh menjadi parser, database, atau sumber kebenaran utama. LLM
hanya membantu memilih langkah investigasi dan menjelaskan hasil yang sudah
diambil melalui tool.

## 3. Masalah yang diselesaikan

Log keamanan memiliki masalah praktis:

1. format heterogen: syslog, access log, JSON, CSV, atau logfmt;
2. timestamp dapat tidak memiliki tahun atau timezone;
3. satu kejadian sering tersebar pada banyak baris atau file;
4. investigator perlu menghubungkan IP, username, host, dan session;
5. rule menghasilkan finding, tetapi investigator tetap perlu konteks;
6. jawaban AI tanpa citation sulit diaudit.

### Pekerjaan deterministik

Dikerjakan oleh Python, SQLAlchemy, PostgreSQL, regex, dan rule engine:

- validasi dan hashing file;
- deteksi format dari isi file;
- parsing baris;
- normalisasi field dan timestamp;
- sorting timeline;
- correlation entity;
- detection pattern;
- risk score dan confidence breakdown;
- pembentukan finding;
- pengecekan case ownership.

### Pekerjaan agentic

Dilakukan oleh LLM gateway dan dibatasi verifier:

- memahami pertanyaan investigator;
- mengikuti investigation plan;
- memilih tool yang relevan;
- membaca observation terstruktur;
- memilih langkah berikutnya ketika evidence kosong atau kontradiktif;
- mencari evidence yang dapat melemahkan hypothesis;
- menyusun fact, inference, dan hypothesis;
- berhenti atau abstain ketika bukti tidak cukup.

## 4. Context diagram

~~~mermaid
flowchart LR
    U[Investigator / SOC Analyst]
    FE[Next.js Frontend]
    API[FastAPI Backend]
    DB[(PostgreSQL)]
    REDIS[(Redis)]
    CEL[Celery Worker + Beat]
    VOL[(Evidence Volume)]
    AG[VIGIL LLM Gateway]
    LLM[Hosted LLM Provider]
    TOOLS[Case-scoped Tool Registry]
    MCP[Private MCP Adapter]
    SIEM[OpenSearch / Splunk / Wazuh]
    AUDIT[Audit Logs]

    U --> FE
    FE -->|REST JSON / multipart| API
    API --> DB
    API --> REDIS
    API --> VOL
    REDIS --> CEL
    CEL --> DB
    CEL --> VOL
    API --> AG
    AG --> LLM
    AG --> TOOLS
    TOOLS --> DB
    TOOLS --> MCP
    MCP --> SIEM
    MCP --> DB
    API --> AUDIT
~~~

| Hubungan | Sifat | Makna |
|---|---|---|
| Investigator → Frontend | Interaktif | User membuat case, upload, filter, bertanya, dan meninjau citation. |
| Frontend → FastAPI | Sinkron HTTP | Frontend tidak mengakses database langsung. |
| FastAPI → PostgreSQL | Sinkron SQL | Menyimpan system of record. |
| FastAPI → Redis | Queue/sinkron | Rate limit, broker Celery, dan lock analisis. |
| Redis → Celery | Asinkron | Job parsing dan scheduler dijalankan worker. |
| Gateway → LLM | HTTPS | Mengirim policy dan observation yang diperlakukan sebagai data tak tepercaya. |
| Tool Registry → DB | Sinkron | Tool mengambil data dengan filter allowlist dan active case. |
| MCP → SIEM | Read-only API | Mengambil telemetry eksternal dengan query terbatas. |

## 5. Struktur repository

~~~text
loginvestigator-x/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── auth.py
│   │   ├── security.py
│   │   ├── tasks.py
│   │   ├── worker.py
│   │   ├── engine.py
│   │   ├── agent_tools.py
│   │   ├── llm_gateway.py
│   │   ├── vigil.py
│   │   ├── claim_verifier.py
│   │   ├── external_sources.py
│   │   ├── mcp_server.py
│   │   └── parsers/
│   │       ├── base.py
│   │       ├── detector.py
│   │       ├── registry.py
│   │       ├── linux.py
│   │       ├── access.py
│   │       ├── json_app.py
│   │       ├── csv_app.py
│   │       ├── logfmt.py
│   │       └── text.py
│   ├── alembic/versions/
│   ├── tests/
│   ├── evals/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── page.tsx
│   │   ├── login/page.tsx
│   │   └── cases/[caseId]/
│   │       ├── dashboard/page.tsx
│   │       ├── upload/page.tsx
│   │       ├── timeline/page.tsx
│   │       ├── events/page.tsx
│   │       ├── findings/page.tsx
│   │       └── chat/page.tsx
│   ├── components/
│   └── lib/
├── samples/
├── monitoring/
├── scripts/
├── docs/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
└── README.md
~~~

## 6. Backend: pusat kendali

Backend menggunakan FastAPI dan menjadi satu-satunya boundary yang mengatur
akses ke database, evidence, agent, dan external source.

### 6.1 main.py — HTTP API dan orchestration

Tanggung jawab:

- membuat aplikasi dan middleware;
- request ID dan security headers;
- health, readiness, metrics;
- login, logout, session;
- membuat case;
- upload dan status parsing;
- event, timeline, entity, finding;
- chat dan agent run control;
- rebuild analysis;
- export Markdown/PDF.

Endpoint penting:

| Kelompok | Endpoint | Fungsi |
|---|---|---|
| System | GET /health | Liveness sederhana. |
| System | GET /ready | Database, Redis, storage, dan schema revision. |
| Auth | POST /auth/login | Session cookie dan CSRF cookie. |
| Case | POST /cases | Membuat case dan membership awal. |
| Evidence | POST /cases/{case_id}/logs | Upload, hash, simpan, enqueue. |
| Evidence | GET /cases/{case_id}/jobs/{job_id} | Status parsing. |
| Evidence | POST /cases/{case_id}/logs/{id}/verify | Verifikasi SHA-256. |
| Analysis | GET /cases/{case_id}/events | Event canonical. |
| Analysis | GET /cases/{case_id}/timeline | Timeline deterministic + correlation. |
| Analysis | GET /cases/{case_id}/findings | Finding, risk, confidence, workflow. |
| Agent | POST /cases/{case_id}/chat | Membuat atau melanjutkan agent run. |
| Agent | GET /cases/{case_id}/agent-runs/{run_id} | State, steps, ledger. |
| Agent | POST .../pause, cancel, resume | Kontrol durable agent run. |
| Report | POST /cases/{case_id}/exports | Export report. |

### 6.2 config.py — konfigurasi runtime

~~~text
App          APP_VERSION, APP_ENV, REQUIRE_MIGRATIONS, SCHEMA_REVISION
Database     DATABASE_URL, REDIS_URL, EVIDENCE_STORAGE_PATH
Analysis     timezone, correlation window, brute-force threshold
Agent        provider, endpoint, model, rounds, calls, timeout, repair
Security     cookie, session TTL, upload/chat/login rate limit
External     OpenSearch, Splunk, Wazuh, MCP, timeout, retries
~~~

Contoh konfigurasi agent:

~~~dotenv
LLM_PROVIDER=groq
LLM_API_KEY=<secret>
LLM_ENDPOINT=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-120b
LLM_MAX_TOOL_ROUNDS=8
LLM_MAX_TOOL_CALLS=20
LLM_MAX_REPAIR_ATTEMPTS=2
LLM_MAX_PLAN_REVISIONS=3
LLM_TIMEOUT_SECONDS=60
~~~

API key tidak boleh ditulis di source, commit, prompt, atau trace. Production
harus mengganti credential default, memakai TLS, secure cookies, CORS allowlist,
dan secret manager.

### 6.3 database.py — koneksi SQLAlchemy

File ini menyediakan engine SQLAlchemy, session database, dan dependency
FastAPI untuk memperoleh session per request. PostgreSQL adalah system of
record. Frontend tidak pernah membaca PostgreSQL langsung.

### 6.4 models.py — model persistence

| Model/tabel | Inti data |
|---|---|
| Case / cases | Identitas workspace investigasi. |
| User / users | User, role global, password hash, status aktif. |
| UserSession / user_sessions | Hash session token, CSRF hash, expiry. |
| CaseMembership / case_memberships | Hubungan user dengan case dan role. |
| EvidenceFile / evidence_files | File upload, SHA-256, status, progress, format, integrity. |
| QuarantinedLine / quarantined_lines | Baris malformed pada mode quarantine. |
| Event / events | Canonical event hasil parser atau external projection. |
| Correlation / correlations | Relasi antar-event, alasan, dan delta waktu. |
| Finding / findings | Temuan rule, evidence IDs, risk, confidence, MITRE, workflow. |
| AgentRun / agent_runs | Sesi investigasi AI, question, state, versi, status. |
| AgentStep / agent_steps | Trace setiap model/tool/repair step. |
| EvidenceLedger / evidence_ledgers | Evidence yang diamati agent. |
| ExternalEvidence / external_evidence | Snapshot hit OpenSearch/Splunk/Wazuh. |
| AuditLog / audit_logs | Operasi penting dan actor. |

### 6.5 schemas.py — kontrak API

Pydantic schemas mendefinisikan bentuk request dan response untuk login, case,
evidence, event, timeline, finding, chat, claim, agent run, dan report. Schema
membatasi field yang masuk/keluar API dan menjadi kontrak frontend-backend.

### 6.6 auth.py — identity dan permission

Kontrol:

- password di-hash PBKDF2-HMAC-SHA256;
- token session disimpan sebagai hash;
- session memiliki expiry;
- CSRF wajib untuk operasi mutatif;
- role case menentukan permission read/upload/chat/export;
- setiap route case memverifikasi membership terhadap case_id URL.

### 6.7 security.py — upload dan rate limit

Upload memeriksa filename, extension, MIME, ukuran, UTF-8, dan pola isi. File
disimpan dengan UUID, bukan nama user. Redis fixed-window rate limiter membatasi
login, upload, dan chat. Quota per user masih merupakan peningkatan production.

## 7. Pipeline evidence dan parsing

### 7.1 Upload sampai queue

~~~mermaid
sequenceDiagram
    actor I as Investigator
    participant FE as Frontend
    participant API as FastAPI
    participant FS as Evidence Volume
    participant DB as PostgreSQL
    participant R as Redis
    participant W as Celery Worker

    I->>FE: Pilih file dan mode strict/quarantine
    FE->>API: POST multipart /cases/{id}/logs
    API->>API: Validasi filename/MIME/size/UTF-8/isi
    API->>API: Hitung SHA-256 secara streaming
    API->>FS: Simpan sebagai UUID path
    API->>DB: Simpan EvidenceFile + audit
    API->>R: Enqueue evidence_file_id
    API-->>FE: 202 Accepted + job_id
    R->>W: Jalankan parse_evidence_file
~~~

Parsing berjalan asynchronous. Request upload selesai lebih cepat dan worker
menjalankan pekerjaan berat tanpa mengunci request HTTP.

### 7.2 tasks.py — asynchronous ingestion

Task utama:

- parse_evidence_file: deteksi format, parser, event, quarantine;
- mark_stuck_jobs: menandai job dengan heartbeat terlalu lama;
- mark_stuck_agent_runs: menandai agent run macet;
- verify_evidence_files: menghitung ulang hash secara periodik.

Setelah event dibuat, worker mengambil Redis lock berdasarkan case. Lock
mencegah dua ingestion bersamaan menulis correlation/finding yang tumpang tindih.

| Mode | Perilaku |
|---|---|
| strict | Baris malformed dapat membuat file gagal dan tidak menghasilkan analisis parsial. |
| quarantine | Baris valid diproses; baris bermasalah masuk quarantined_lines; status parsed_with_warnings. |

Setiap event mempertahankan raw line, nomor baris, parser, confidence, timestamp
original/normalized, timezone, dan asumsi normalisasi.

### 7.3 Detector dan parser

Detector memilih parser berdasarkan isi, bukan extension saja.

| Modul | Fokus |
|---|---|
| detector.py | Skoring sinyal format. |
| linux.py | Linux auth/syslog, SSH login, sudo, privilege event. |
| access.py | Nginx/Apache combined access log. |
| json_app.py | JSON/JSONL dengan alias field umum. |
| csv_app.py | CSV dengan header dan alias canonical. |
| logfmt.py | key=value. |
| text.py | Generic text fallback dengan confidence rendah. |
| registry.py | Registrasi dan dispatch parser. |
| base.py | Tipe hasil parser dan error parsing. |

Di luar target inti: EVTX native, PCAP, cloud audit provider khusus,
Kubernetes runtime khusus, threat intelligence live, dan real-time tailing.

### 7.4 Canonical Event

Canonical event adalah bahasa bersama parser, engine, tools, UI, dan verifier.

~~~text
Identity       event_id, case_id
Provenance     evidence_file_id, external_evidence_id, event_origin
Time           timestamp_original, timestamp_normalized, timezone
Time quality   timestamp_confidence, assumptions, year_source, timezone_source
Source         source_type, source_name, host
Semantics      event_category, event_action, event_outcome, severity
Entities       username, source_ip, destination_ip, session_id
Process/file   process_name, parent_process_name, file_name, command_line, file_hash
Network/web    ports, protocol, http_method, http_status, url_path, user_agent
Traceability   raw_log, raw_line_number, parser_name, parser_confidence, tags
~~~

Field yang tidak tersedia di sumber dibiarkan None; sistem tidak boleh mengarang
data.

## 8. Analysis engine deterministik

File utama: backend/app/engine.py.

### 8.1 Timeline

Urutan timeline menggunakan:

1. timestamp valid lebih dahulu;
2. timestamp normalized;
3. timestamp confidence lebih tinggi;
4. evidence/source identifier;
5. raw line number;
6. event ID sebagai tie-break.

LLM tidak menyusun urutan. Replay terhadap data sama diharapkan menghasilkan
urutan sama.

### 8.2 Correlation

Correlation default menggunakan source_ip, username, dan session_id dengan
namespace host/source type, dalam jendela waktu default 10 menit. Setiap relasi
memiliki predecessor, delta waktu, dan correlation reason.

Contoh reason:

~~~text
shared source_ip within 10 minutes (0.5 minutes apart)
~~~

Correlation bersifat indikatif, bukan bukti dua event pasti berasal dari aktor
yang sama.

### 8.3 Detection dan finding

Rule yang tersedia:

- brute force;
- successful login setelah failures;
- password spraying;
- distributed password guessing;
- suspicious PowerShell;
- potential web exploitation;
- persistence/service install;
- privilege escalation.

Finding menyimpan evidence IDs dan mapping MITRE ATT&CK sebagai konteks rule.
Mapping MITRE bukan bukti teknik tersebut pasti dilakukan.

### 8.4 Risk dan confidence

~~~text
risk = severity*0.30
     + frequency*0.20
     + privilege*0.25
     + correlation*0.15
     + novelty*0.10
~~~

Risk score heuristik dan belum dikalibrasi sebagai probabilitas insiden.
Confidence berbeda dari risk:

~~~text
confidence = parser_quality*0.40
           + timestamp_quality*0.20
           + evidence_support*0.25
           + source_diversity*0.15
~~~

Confidence menyatakan kualitas dukungan data, bukan kemungkinan attacker benar.

### 8.5 Rebuild analysis

~~~text
events dari case
  -> rebuild correlation
  -> build correlations
  -> detect auth findings
  -> detect extended findings
  -> hitung risk/confidence
  -> pertahankan workflow finding yang key-nya sama
  -> simpan audit
~~~

Idempotency dan equivalence full/incremental rebuild masih perlu diuji lebih
luas sebelum skala produksi tinggi.

## 9. Agentic layer: VIGIL

VIGIL adalah nama state dan workflow agentic, bukan model baru. Model aktif
ditentukan konfigurasi provider, sementara VIGIL mengatur bagaimana model boleh
melakukan investigasi.

### 9.1 Komponen state

| Komponen | Peran |
|---|---|
| Goal | Pertanyaan investigator dan case aktif. |
| Plan | Objective, suggested tools, expected evidence, dependency, stop condition. |
| Hypothesis registry | Status hypothesis, evidence support/contradiction, alternative explanation. |
| Evidence gaps | Evidence yang belum tersedia. |
| Case memory | Ringkasan state hanya untuk case/run tersebut. |
| Provenance edges | Relasi hypothesis/claim/observation dengan evidence/tool. |
| Repair state | Alasan claim ditolak dan jumlah repair. |
| Stop state | Kode berhenti dan alasan operasional. |

Schema utama state adalah vigil-state-v2 dan disimpan dalam AgentRun.state.

### 9.2 Loop agent

~~~mermaid
sequenceDiagram
    actor I as Investigator
    participant API as FastAPI
    participant G as LLMGateway
    participant M as Hosted LLM
    participant T as ToolRegistry
    participant DB as PostgreSQL
    participant V as ClaimVerifier

    I->>API: POST /cases/{case_id}/chat
    API->>G: question + active case
    G->>G: create/restore plan and state
    G->>M: policy + plan + allowed tool schemas
    M-->>G: tool call atau final JSON
    G->>T: validate tool, args, case, budget
    T->>DB: deterministic read-only query
    DB-->>T: observation + evidence IDs
    T-->>G: untrusted data envelope
    G->>G: update ledger, gaps, hypothesis, next action
    G->>M: next observation/state
    M-->>G: next tool, revised plan, atau claims
    G->>V: verify draft claims
    V-->>G: verified/rejected + reason codes
    G-->>API: answer, claims, run state, stop reason
    API-->>I: verified response + clickable citations
~~~

### 9.3 Budget dan stop

Agent dibatasi oleh maximum rounds/calls, repetition, no-progress, timeout,
context size, plan revisions, dan repair attempts. Jika provider gagal atau
budget habis, status run disimpan sebagai failed/paused dengan stop reason.

### 9.4 Tool yang tersedia

| Tool | Fungsi | Batasan |
|---|---|---|
| search_events | Filter canonical events | Allowlist, bounded, case-scoped. |
| get_surrounding_events | Konteks event | Window dan ownership dibatasi. |
| build_timeline | Timeline deterministic | Model tidak sorting sendiri. |
| correlate_entities | Relasi IP/user/session | Entity type allowlist. |
| get_raw_evidence | Raw line/citation | Case ownership dan raw-log policy. |
| generate_case_summary | Ringkasan finding/risk | Bersumber dari database. |
| search_disconfirming_evidence | Evidence yang melemahkan hypothesis | Read-only dan bounded. |
| get_external_source_status | Status provider external | Tidak mengembalikan secret. |
| search_external_events | Search telemetry external | Provider allowlist dan snapshot lokal. |

Tidak ada arbitrary SQL/DSL/SPL, shell command, firewall, EDR containment,
account disable, delete, atau action tool.

### 9.5 Claim Verification Gate

Model mengirim draft JSON. Backend memeriksa status, evidence UUID, case
ownership, direct support untuk fact, minimal dua evidence untuk inference,
limitation/additional evidence untuk hypothesis, semantic/entity consistency,
confidence, dan kalimat per claim.

Claim gagal diberi reason code dan dapat masuk repair loop terbatas. Jika semua
claim gagal:

~~~text
Belum cukup bukti untuk menjawab pertanyaan ini.
~~~

Gate mengurangi claim unsupported. Gate tidak menghapus hallucination secara
matematis dan tidak membuktikan keaslian sumber log.

## 10. MCP dan telemetry eksternal

MCP adalah private read-only adapter, bukan active response dan bukan pengganti
SIEM. Provider yang didukung: OpenSearch, Splunk, dan Wazuh Indexer. External
source disabled secara default.

### Alur external evidence

~~~text
Agent memilih provider
  -> cek status/configuration
  -> backend menambahkan case scope
  -> adapter membuat query terbatas
  -> provider mengembalikan hit
  -> hit diberi content/query metadata dan hash
  -> hit disimpan sebagai ExternalEvidence immutable
  -> hit diproyeksikan menjadi canonical Event
  -> timeline/correlation/detection dapat dibangun ulang
  -> citation memakai UUID lokal TraceLens
~~~

Case scope mencegah event dari case lain ikut masuk. Jika provider gagal,
sistem menyatakan external unavailable dan tidak mengarang hasil.

Snapshot lokal memberikan evidence UUID, content hash, query metadata, waktu
retrieval, hubungan case, dan replay. Ini tetap belum menjadi chain-of-custody
legal formal tanpa WORM, trusted timestamp, dan prosedur eksternal.

## 11. Frontend: workspace investigator

Frontend menggunakan Next.js App Router, React, TypeScript, dan API client
berbasis fetch/XMLHttpRequest untuk upload.

### 11.1 Halaman utama

| Route | Fungsi inti |
|---|---|
| / | Membuat case baru atau membuka case UUID. |
| /login | Login investigator. |
| /cases/{caseId}/dashboard | Ringkasan event, entity, risk, finding, dan status evidence. |
| /cases/{caseId}/upload | Drag-and-drop upload, progress, parsing mode, quarantine count. |
| /cases/{caseId}/timeline | Timeline event terurut dengan correlation. |
| /cases/{caseId}/events | Explorer/filter event dan raw evidence. |
| /cases/{caseId}/findings | Finding, risk breakdown, MITRE, disposition, notes, workflow. |
| /cases/{caseId}/chat | Chat investigator, claim badge, citation, limitation, agent trace. |

### 11.2 Komponen UI penting

- AppShell.tsx: shell navigasi dan layout aplikasi;
- UI.tsx: badge severity, loading/error/empty state, raw log, evidence modal;
- api.ts: session cookie, CSRF header, REST helper, upload progress;
- types.ts: TypeScript contract untuk event, finding, claim, agent run, ledger.

### 11.3 Alur user di UI

~~~text
Login
  -> create/open case
  -> upload evidence
  -> tunggu parsed/parsed_with_warnings
  -> dashboard
  -> timeline/events/findings
  -> chat AI Investigator
  -> buka citation raw evidence
  -> review limitation/finding
  -> export report
~~~

Frontend menampilkan narasi AI dan evidence sebagai blok berbeda. Tujuannya
agar investigator tidak menganggap teks AI sebagai raw source.

## 12. Database dan hubungan data

~~~mermaid
erDiagram
    CASES ||--o{ CASE_MEMBERSHIPS : has
    USERS ||--o{ CASE_MEMBERSHIPS : joins
    CASES ||--o{ EVIDENCE_FILES : contains
    EVIDENCE_FILES ||--o{ EVENTS : produces
    CASES ||--o{ EXTERNAL_EVIDENCE : snapshots
    EXTERNAL_EVIDENCE ||--o{ EVENTS : projects
    CASES ||--o{ EVENTS : scopes
    CASES ||--o{ CORRELATIONS : scopes
    EVENTS ||--o{ CORRELATIONS : relates
    CASES ||--o{ FINDINGS : produces
    CASES ||--o{ AGENT_RUNS : owns
    AGENT_RUNS ||--o{ AGENT_STEPS : contains
    AGENT_RUNS ||--o{ EVIDENCE_LEDGERS : observes
    CASES ||--o{ AUDIT_LOGS : records
~~~

Semua objek investigasi penting memiliki case_id. Sebuah UUID tanpa case_id
tidak boleh dianggap citation yang sah.

### Status evidence file

~~~text
queued -> parsing -> parsed
                  -> parsed_with_warnings
                  -> failed
                  -> stuck
                  -> cancelled
~~~

parsed_with_warnings berarti event valid tersedia, tetapi ada baris yang
dikarantina. Dashboard memberi peringatan sebelum laporan dibuat.

### Status agent run

~~~text
running -> complete
        -> paused -> resume -> running
        -> failed
        -> cancelled
        -> stuck
~~~

stop_reason menjelaskan mengapa run berhenti. State dan steps tetap disimpan
untuk audit dan resume.

## 13. Migration dan deployment

### 13.1 Alembic

Migration saat ini:

~~~text
0001_baseline
0002_security_enrichment
0003_soc_workflow
0004_external_evidence
0005_agent_runs_and_canonical_external_events
0006_production_hardening
~~~

Container backend menjalankan alembic upgrade head sebelum Uvicorn. API
memeriksa schema revision pada readiness dan tidak boleh melakukan runtime DDL
sebagai pengganti migration.

### 13.2 Docker Compose services

| Service | Fungsi |
|---|---|
| postgres | PostgreSQL 16. |
| redis | Broker Celery, rate limit, lock. |
| evidence-init | Menyiapkan ownership evidence volume. |
| backend | FastAPI/Uvicorn. |
| worker | Celery parser dan analysis task. |
| scheduler | Celery Beat untuk watchdog dan integrity check. |
| frontend | Next.js web app. |
| prometheus | Metrics pada production overlay. |

### 13.3 Volume

- postgres_data: data database;
- evidence_data: file evidence level aplikasi;
- prometheus_data: metrics production overlay.

Jangan menjalankan docker compose down -v jika ingin mempertahankan database
dan evidence.

### 13.4 Default port

| Service | Default host URL |
|---|---|
| Frontend | http://localhost:3001 |
| Backend | http://localhost:8002 |
| Swagger | http://localhost:8002/docs |
| Health | http://localhost:8002/health |
| Ready | http://localhost:8002/ready |

Port host dapat berbeda jika sudah dipakai container lain. Pada environment
yang sedang direview, frontend pernah dipetakan ke 3002 karena 3001 terpakai.

### 13.5 Perintah menjalankan

~~~powershell
cd D:\SEM-6\AI\loginvestigator-x
Copy-Item .env.example .env
# Edit .env: database password, bootstrap password, dan LLM_API_KEY
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8002/health
Invoke-RestMethod http://localhost:8002/ready
~~~

Melihat log:

~~~powershell
docker compose logs -f backend worker frontend
~~~

## 14. Apa yang terjadi ketika LLM tidak tersedia?

LLM bukan bagian dari parsing dasar. Maka:

- upload dan parsing tetap dapat berjalan;
- timeline, event explorer, correlation, detection, dan finding tetap dapat
  digunakan;
- chat agent gagal atau paused dengan status provider yang jujur;
- sistem tidak mengarang jawaban dari cache yang tidak terverifikasi;
- investigator tetap dapat membuka raw evidence dan report deterministik.

Ini adalah graceful degradation: fitur agent berhenti, tetapi system of record
dan analisis deterministic tetap hidup.

## 15. Apa yang terjadi ketika dependency gagal?

Health dan readiness berbeda. health hanya menjawab proses hidup, sedangkan
ready memeriksa dependency utama.

| Gangguan | Perilaku yang diharapkan |
|---|---|
| PostgreSQL gagal | Readiness gagal; endpoint data tidak dianggap siap. |
| Redis gagal | Queue, rate limit, atau lock terganggu; readiness gagal. |
| Evidence volume gagal | Readiness gagal; upload/export dihentikan. |
| Worker macet | Scheduler menandai job/run stuck; operator dapat retry. |
| Integrity mismatch | Evidence/report diblokir atau diberi status mismatch. |
| Provider LLM 429/5xx | Retry terbatas, pause/fail, tanpa fabricated answer. |
| MCP unavailable | Fallback local evidence jika ada; external result tidak dikarang. |

## 16. Keamanan per boundary

### Browser dan API

- session cookie HttpOnly;
- CSRF token untuk operasi mutatif;
- membership permission per case;
- rate limit login/upload/chat;
- request ID dan security headers;
- CORS harus allowlist pada production.

### Upload dan parser

- nama file tidak dipercaya;
- file disimpan dengan UUID;
- ukuran dan MIME dibatasi;
- isi dideteksi dari konten;
- parser tidak memanggil LLM;
- raw line dipertahankan untuk provenance;
- parser sandbox dan malware scanner masih peningkatan production.

### Agent dan provider

- tool allowlist;
- active case tidak boleh diganti model;
- tidak ada arbitrary SQL/DSL/SPL;
- tool result dibungkus sebagai untrusted data;
- secret dan raw log dapat di-redact/withhold;
- claim diverifikasi sebelum response;
- tidak ada write/action tool.

### Data dan audit

- SHA-256 evidence file;
- immutable guard pada raw evidence;
- external snapshot content hash;
- audit log operasi penting;
- external WORM/tamper-evident audit masih gate production.

## 17. Di mana agentic-nya dan di mana bukan?

### Bagian yang agentic

~~~text
Pertanyaan terbuka
  -> goal/plan
  -> pemilihan tool
  -> observation
  -> update gap/hypothesis
  -> pencarian disconfirming
  -> replan atau repair
  -> stop/abstain
~~~

### Bagian yang bukan agentic

- parser format;
- regex;
- timestamp normalization;
- sorting timeline;
- correlation rule;
- detection rule;
- risk formula;
- query authorization;
- evidence ownership;
- claim verification.

Pembagian ini adalah desain keselamatan. Jika LLM mengambil alih semua bagian,
aplikasi lebih sulit direplay, diuji, dan diaudit.

## 18. Contoh investigasi end-to-end

Misalkan investigator upload auth log dengan lima login gagal lalu satu login
sukses dari IP yang sama.

~~~text
1. Upload API menghitung SHA-256 dan menyimpan file UUID.
2. Celery mendeteksi Linux auth/syslog.
3. Parser membuat event login failed/success.
4. Engine mengurutkan timestamp dan menghubungkan source_ip.
5. Rule membuat finding brute_force.
6. Rule membuat finding successful_login_after_failures.
7. Risk breakdown dan evidence_ids disimpan.
8. Investigator bertanya kepada AI.
9. VIGIL membuat plan: timeline -> correlation -> context
   -> disconfirming search -> answer.
10. Model memilih tool; backend memeriksa active case dan budget.
11. Tool mengembalikan event IDs dan observation.
12. VIGIL mencatat ledger, hypothesis, gap, dan next action.
13. Model membuat claim fact/inference/hypothesis.
14. Verifier memeriksa evidence UUID dan semantic support.
15. Claim valid ditampilkan dengan citation; claim lemah ditolak atau repair.
16. Investigator membuka raw line dan memutuskan tindak lanjut manual.
~~~

Sistem tidak boleh langsung menyatakan akun telah dikompromikan hanya dari
urutan ini. Pernyataan tersebut biasanya masih hypothesis dan memerlukan
evidence tambahan seperti endpoint telemetry, session context, atau activity
pasca-login.

## 19. Pengujian dan evaluasi

### Test code

~~~text
backend/tests/test_parsers.py
backend/tests/test_engine.py
backend/tests/test_agent.py
backend/tests/test_security.py
backend/tests/test_external_sources.py
backend/tests/test_vigil.py
~~~

Area test:

- parser valid/malformed dan format detection;
- timeline tie-break dan correlation;
- finding/risk/extended detection;
- authorization/cross-case/upload/rate limit;
- claim verifier dan prompt injection;
- MCP scope dan external snapshot;
- VIGIL plan, state, hypothesis, gap, stop, repair.

### Evaluation offline

~~~powershell
docker compose exec backend pytest -q
docker compose exec backend python evals/run_vigil_eval.py
docker compose exec backend python evals/run_detection_eval.py
~~~

Golden set internal adalah regression evidence, bukan bukti generalisasi ke
semua SOC. Evaluasi lanjutan perlu membandingkan human analyst, rule/SOAR,
single-shot LLM, VIGIL gate off, dan VIGIL gate on. Gate off dan gate on harus
memakai data, model, prompt, tool, dan budget yang sama; hanya verification gate
yang berbeda.

## 20. Batas kemampuan saat ini

### Sudah tersedia

- case workspace dan membership;
- upload asynchronous;
- SHA-256 dan evidence UUID;
- parser Linux/access/JSON/CSV/logfmt/text;
- canonical event dan timestamp provenance;
- deterministic timeline/correlation/detection/risk;
- finding workflow dan report;
- VIGIL plan/state/tool loop/checkpoint/resume;
- claim verification dan abstention;
- private MCP read-only OpenSearch/Splunk/Wazuh;
- Prometheus/health/readiness/watchdog;
- Docker production overlay dan Alembic migration gate.

### Belum boleh dianggap tersedia

- Windows EVTX native;
- PCAP/network reassembly;
- malware sandbox atau active response;
- threat intelligence live yang sudah tervalidasi;
- real-time tailing/streaming;
- multi-agent supervisor;
- forensic-grade legal chain-of-custody;
- calibrated probability risk score;
- multi-tenant enterprise isolation yang sudah diuji;
- load/soak production evidence;
- independent red-team sign-off.

## 21. Urutan membaca source

1. README.md untuk cara menjalankan;
2. docs/TRACELES_AI_PENJELASAN_LENGKAP_ID.md untuk gambaran sistem;
3. docker-compose.yml untuk container dan dependency;
4. backend/app/main.py untuk route/API;
5. backend/app/models.py dan migration untuk data model;
6. backend/app/tasks.py untuk upload-to-event;
7. backend/app/parsers/ untuk format log;
8. backend/app/engine.py untuk timeline/finding/risk;
9. backend/app/agent_tools.py untuk tool boundary;
10. backend/app/vigil.py untuk state/plan/hypothesis;
11. backend/app/llm_gateway.py untuk model-tool loop;
12. backend/app/claim_verifier.py untuk evidence gate;
13. backend/app/external_sources.py dan mcp_server.py untuk MCP;
14. frontend/app/cases/[caseId]/ untuk UI investigator;
15. backend/tests/ dan backend/evals/ untuk kontrak yang harus lulus.

## 22. Inti final

TraceLens bukan satu program monolitik yang diberi chatbot. Ia terdiri dari:

~~~text
Frontend investigator
  + API/auth/case boundary
  + PostgreSQL system of record
  + Redis/Celery asynchronous pipeline
  + immutable evidence storage
  + deterministic parser/analysis engine
  + VIGIL bounded single-agent
  + case-scoped tool registry
  + private MCP external telemetry
  + claim verification gate
  + audit/metrics/reporting
~~~

Inti keselamatannya adalah pembatasan kewenangan: LLM boleh memilih langkah dan
menjelaskan evidence, tetapi tidak boleh mengakses database langsung, mengubah
raw evidence, menjalankan command, melakukan active response, atau menampilkan
claim tanpa citation valid.

Inti agentic-nya adalah loop **plan → tool → observation → gap/hypothesis →
replan/verify → stop**, bukan sekadar **prompt → paragraph**.

Inti produk yang harus dibuktikan berikutnya bukan menambah fitur sebanyak
mungkin, melainkan mengukur apakah loop tersebut membuat investigasi lebih
cepat, lebih dapat ditelusuri, dan lebih aman dibanding baseline human, rule,
dan LLM biasa.

Dokumen terkait:

- [Technical review](AGENTIC_AI_TECHNICAL_REVIEW_ID.md)
- [Penjelasan lengkap](TRACELES_AI_PENJELASAN_LENGKAP_ID.md)
- [Arsitektur VIGIL](AGENTIC_V2_ARCHITECTURE.md)
- [External MCP integration](EXTERNAL_MCP_INTEGRATION_ID.md)
- [Production readiness](PRODUCTION_READINESS.md)
- [Product acceptance checklist](PRODUCT_ACCEPTANCE_CHECKLIST_ID.md)
- [Threat model](THREAT_MODEL.md)
