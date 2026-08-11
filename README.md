# TraceLens AI

Investigasi log keamanan siber berbasis bukti dengan bantuan AI untuk operasi defensif.

[![Security and Quality](https://github.com/davidlimss/TraceLens/actions/workflows/security-quality.yml/badge.svg)](https://github.com/davidlimss/TraceLens/actions/workflows/security-quality.yml)
[![Project Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#status-proyek)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](backend/pyproject.toml)
[![Node.js 22](https://img.shields.io/badge/node-22-339933.svg)](frontend/package.json)

TraceLens mengubah log mentah heterogen menjadi event ternormalisasi, timeline deterministik, korelasi entitas, finding, risk score, dan kesimpulan berbantuan AI yang tetap dapat dilacak ke evidence asli.

> TraceLens adalah alat bantu investigasi, bukan otoritas respons insiden otonom. Keputusan berdampak tinggi tetap wajib ditinjau manusia.

## Status proyek

TraceLens saat ini berada pada tahap **production-oriented beta foundation untuk riset, demo, dan validasi engineering**. Alur read-only sudah dapat dijalankan end-to-end, tetapi repository ini belum menjadi layanan enterprise, belum forensic-grade, dan belum boleh dipakai tanpa pengawasan investigator.

| Area | Kondisi saat ini |
|---|---|
| Scope produk | Investigasi log berbasis case, read-only |
| Quality | CI otomatis, test parser/engine/security/agent, evaluation offline |
| Production readiness | Bersyarat; deployment gate masih wajib dipenuhi |
| Release | Branch, pull request, migration, changelog, dan CI gate |

## Latar belakang dan tujuan

Log keamanan biasanya datang dari banyak format, memiliki timezone yang tidak
seragam, dan sulit dibaca sebagai satu kronologi. Investigator perlu menjaga
raw evidence, menggabungkan event dari beberapa sumber, memahami korelasi IP
atau user, lalu membedakan fakta dari dugaan. Kesalahan pada tahap tersebut
dapat menghasilkan false positive, false negative, atau kesimpulan AI yang
tidak dapat ditelusuri.

TraceLens dibangun untuk membantu investigator menjawab tiga pertanyaan inti:

1. Apa urutan kejadian yang dapat dibuktikan dari log?
2. Event, IP, user, atau session mana yang saling berkaitan?
3. Bukti apa yang masih kurang sebelum sebuah hipotesis dapat dipercaya?

Tujuan engineering-nya adalah memisahkan pekerjaan objektif dari pekerjaan
bahasa. Parsing, timestamp normalization, sorting, correlation, detection,
dan risk scoring dikerjakan secara deterministik. AI hanya merencanakan
pencarian, memilih tool read-only, membandingkan bukti, dan menyusun claim yang
kemudian diverifikasi backend.

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

### Di luar scope

TraceLens tidak melakukan active response, tidak mengeksekusi command pada
host, tidak memblokir IP, tidak menonaktifkan akun, dan tidak mengambil
keputusan containment otomatis. Konektor OpenSearch, Splunk, dan Wazuh bersifat
read-only. TraceLens juga bukan pengganti SIEM, SOC analyst, atau prosedur
forensik formal.

Format yang belum mempunyai parser deterministik tidak boleh dipresentasikan
sebagai format yang didukung hanya karena file tersebut ber-extension `.json`
atau `.txt`.

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
  +----> Hosted OpenAI-compatible LLM (Groq by default)
         pemilihan tool dan interpretasi evidence

  +----> External Evidence Plane (read-only)
         OpenSearch / Splunk / Wazuh Indexer
         -> MCP adapter -> immutable external_evidence snapshot
```

### Peta ownership kode

| Area perubahan | File utama | Bukti wajib sebelum PR |
|---|---|---|
| Parser | `backend/app/parsers/` | Test event valid, malformed, missing field, timestamp ambiguity |
| Analysis | `backend/app/engine.py` | Test timeline, correlation, detection, risk, golden case |
| API/security | `backend/app/main.py`, `auth.py`, `security.py` | Authorization, CSRF, upload, rate-limit regression |
| Agent | `backend/app/vigil.py`, `vigil_policy.py`, `llm_gateway.py` | Claim gate, prompt injection, budget, stop, replay |
| Database | `backend/alembic/`, `models.py` | Forward migration, downgrade, readiness, immutability |
| Frontend | `frontend/app/`, `frontend/lib/` | Typecheck, build, loading/error/empty state |
| Deployment | `docker-compose*.yml`, `.github/workflows/` | Compose config, image scan, secret scan, smoke |

File `.env` dan data evidence lokal tidak pernah menjadi bagian repository.
Sample di `samples/` hanya berisi log aman untuk demo dan test.

| Layer | Teknologi |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| API | FastAPI, Pydantic, SQLAlchemy |
| Database | PostgreSQL 16 |
| Queue | Redis 7, Celery |
| Scheduler | Celery Beat |
| LLM provider | OpenAI-compatible hosted provider; default development configuration is Groq |
| External telemetry | OpenSearch, Splunk, Wazuh Indexer melalui adapter MCP read-only |
| Deployment | Docker Compose |
| Monitoring | Prometheus metrics dan SLO rules |

Lihat [ARCHITECTURE.md](ARCHITECTURE.md) dan [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) untuk desain detail.

### Batas tanggung jawab komponen

| Komponen | Sumber kebenaran | Tidak boleh dilakukan |
|---|---|---|
| Next.js UI | State tampilan dan input investigator | Menghitung finding atau mengubah evidence |
| FastAPI case boundary | Auth, membership, API, audit, orchestration | Melewati authorization case |
| PostgreSQL | Case, event, finding, run, audit | Menyimpan raw event yang dapat ditimpa |
| Celery worker | Parsing dan analysis asynchronous | Memanggil LLM untuk parsing |
| VIGIL supervisor | Plan, state, budget, stop, repair | Menjalankan write action |
| Tool policy/MCP | Tool read-only yang allowlisted | Arbitrary SQL, DSL, credential, atau command |
| Claim verifier | Claim yang boleh ditampilkan | Menerima citation lintas case |

Alur agentiknya adalah `goal -> plan -> tool read-only -> observation tidak
tepercaya -> evidence ledger -> hypothesis/gap -> claim -> verification ->
answer atau abstention`. Karena itu TraceLens adalah bounded single-agent,
bukan multi-agent kosmetik dan bukan autonomous-response platform.

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
- API key provider LLM yang dikonfigurasi (default development: Groq).
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
APP_ENV=development
REQUIRE_MIGRATIONS=true
SCHEMA_REVISION=0007_vigil_replay_snapshots
POSTGRES_PASSWORD=ganti-dengan-password-random-panjang
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=ganti-dengan-password-random-panjang
# Hosted LLM provider (Groq free tier untuk development)
LLM_PROVIDER=groq
LLM_API_KEY=token-groq-kamu
LLM_ENDPOINT=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-120b
LLM_MAX_TOOL_CALLS=20
LOGIN_RATE_LIMIT=10
```

API sekarang menolak melayani deployment production bila schema belum berada
di revision Alembic yang diwajibkan. Endpoint `/ready` juga memeriksa
PostgreSQL, Redis, dan evidence storage; status `ready` bukan sekadar proses
HTTP hidup.

Untuk memakai konektor SIEM eksternal, isi konfigurasi `EXTERNAL_*`, `OPENSEARCH_*`, `SPLUNK_*`, atau `WAZUH_*` di `.env`. Biarkan `EXTERNAL_SOURCES_ENABLED=false` jika belum ada source yang sudah memiliki field `tracelens.case_id`/scope case.

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

Port frontend `3002` juga diizinkan untuk development. Ini berguna jika
`3001` dipakai service lain:

```powershell
$env:FRONTEND_PORT="3002"
docker compose up -d --build
Start-Process http://localhost:3002
```

`CORS_ORIGINS` pada `.env.example` telah memuat `3001` dan `3002`. Pada
deployment selain localhost, ganti dengan origin frontend yang sebenarnya dan
jangan menggunakan wildcard.

Ikuti log:

```bash
docker compose logs -f backend worker frontend
```

Stop tanpa menghapus data:

```bash
docker compose down
```

Jangan gunakan `docker compose down -v` kecuali database dan evidence volume lokal memang ingin dihapus permanen.

Untuk baseline hardening production, gunakan overlay berikut setelah secret,
TLS/WAF, storage, dan backup sudah disiapkan:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Gate deployment dan checklist operasional dirangkum di
[`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md) dan
[`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md).

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
- `search_external_events` — query terbatas ke OpenSearch, Splunk, atau Wazuh; hasil di-snapshot dulu sebagai evidence lokal.

Integrasi external telemetry dijelaskan di [docs/EXTERNAL_MCP_INTEGRATION_ID.md](docs/EXTERNAL_MCP_INTEGRATION_ID.md). Jika diaktifkan, external telemetry menjadi source utama agent; upload lokal menjadi fallback/konteks tambahan. Aktifkan hanya jika setiap source memiliki field scope case. TraceLens tidak menerima arbitrary OpenSearch DSL atau SPL dari model dan tidak menyediakan active response.

### Agent run dan external event plane

External snapshot yang lolos scope `case_id` diproyeksikan menjadi canonical `Event` dengan `event_origin=external`. Projection ini dibaca timeline, correlation, detection, dan risk engine; raw payload tetap immutable di `external_evidence` dan tidak ditimpa oleh projection.

Setiap sesi AI memiliki durable run dan checkpoint. Trace model/tool yang sudah direduksi tersimpan di `agent_steps`, sementara evidence yang benar-benar diamati tercatat di `evidence_ledgers`. Run yang gagal karena timeout/provider outage dapat dilanjutkan dari checkpoint:

```text
GET  /cases/{case_id}/agent-runs
GET  /cases/{case_id}/agent-runs/{run_id}
POST /cases/{case_id}/agent-runs/{run_id}/pause
POST /cases/{case_id}/agent-runs/{run_id}/resume
POST /cases/{case_id}/agent-runs/{run_id}/cancel
```

Run tidak menyimpan chain-of-thought tersembunyi. Investigator hanya melihat status, nama tool, jumlah step, evidence ID, dan hasil yang sudah direduksi. Celery Beat menandai run yang kehilangan heartbeat sebagai `failed`, sehingga dapat di-resume tanpa menganggap jawaban parsial sebagai jawaban final.

Backend memverifikasi status claim, keberadaan evidence, kepemilikan case, dukungan minimum inference/hypothesis, entity consistency, count consistency, limitation, dan overclaim.

Jawaban AI dibangun ulang hanya dari claim yang lolos verification gate.

### TraceLens VIGIL

Agent investigator saat ini menggunakan bounded single-agent VIGIL (*Verified
Investigation Graph & Evidence Loop*). Setiap run menyimpan plan eksplisit,
hypothesis registry, epistemic state, evidence gap, case-bounded memory,
provenance, next action, repair attempt, dan structured stop reason di
`AgentRun.state`. Setelah draft claim ditolak, gateway dapat mencari evidence
tambahan atau menurunkan claim secara maksimal dua kali; jika tetap gagal,
respons ditutup dengan insufficient evidence. UI menampilkan trace operasional
tersebut tanpa chain-of-thought.

VIGIL tetap read-only dan case-scoped. LLM tidak mem-parsing, mengurutkan,
mengorelasikan, mendeteksi, atau menghitung risk. Investigator manusia tetap
menjadi pengambil keputusan akhir.

### Mengapa TraceLens benar-benar agentic

TraceLens bukan chatbot yang menerima satu prompt lalu merangkum context
statis. Agent memiliki tujuan, rencana, aksi yang dipilih berdasarkan keadaan,
observasi dari environment, memori kasus, revisi hipotesis, dan kondisi berhenti
yang tersimpan. Model boleh mengusulkan langkah, tetapi executor deterministik
dan policy backend yang memutuskan apakah langkah tersebut valid.

```text
Pertanyaan investigator
        |
        v
Goal + case boundary
        |
        v
VIGIL membuat plan eksplisit dan stop condition
        |
        v
Policy memeriksa lifecycle, tool allowlist, case ID, dan budget
        |
        v
LLM memilih tool read-only
        |
        v
ToolRegistry menjalankan query deterministik
        |
        v
Observation dibungkus sebagai UNTRUSTED_DATABASE_DATA
        |
        v
State memperbarui evidence ledger, gap, hypothesis, dan next action
        |
        +---- evidence kurang/kontradiktif --> replan atau disconfirming search
        |
        v
LLM menyusun JSON claims
        |
        v
Claim Verification Gate memeriksa evidence dan semantik
        |
        +---- gagal, masih repairable --> repair maksimal 2 kali
        |
        +---- tetap gagal -----------> abstention / insufficient evidence
        |
        v
Jawaban terverifikasi + audit trail + stop reason
```

#### Siklus agent secara rinci

| Tahap | Yang dilakukan agent | Pengaman yang tetap deterministik |
|---|---|---|
| 1. Goal | Memahami pertanyaan investigator dalam case aktif | `case_id` berasal dari endpoint backend, bukan dari model |
| 2. Plan | Menentukan urutan pencarian dan evidence yang diharapkan | `create_investigation_plan()` membuat plan terversi; update plan harus allowlisted |
| 3. Select action | Memilih tool yang membantu step atau evidence gap | `InvestigationPolicy` menolak tool ilegal, state ilegal, pengulangan, dan budget habis |
| 4. Act | Memanggil search, timeline, correlation, raw evidence, atau MCP read-only | `ToolRegistry` memakai query terstruktur; tidak ada SQL/DSL/command arbitrary |
| 5. Observe | Membaca hasil tool dan mengumpulkan evidence ID | Hasil dianggap data tak tepercaya, di-redact, dibatasi ukuran, dan dicatat di ledger |
| 6. Update state | Memperbarui hypothesis, contradiction matrix, gap, provenance, dan next action | State divalidasi oleh kode; evidence dari case lain ditolak |
| 7. Replan | Mencari konteks benign atau bukti yang melemahkan hypothesis | Revisi plan dibatasi maksimal 3 dan `search_disconfirming_evidence` read-only |
| 8. Claim | Menyusun fact, inference, atau hypothesis dalam JSON | Claim wajib membawa evidence ID dan limitation yang sesuai status |
| 9. Verify | Menunggu keputusan Claim Verification Gate | UUID, ownership, entity, count, semantic support, dan overclaim diperiksa backend |
| 10. Stop | Menyelesaikan, abstain, pause, cancel, atau gagal secara terstruktur | Lifecycle state machine dan stop reason mencegah run menggantung atau mengarang hasil |

#### State durable dan checkpoint

State operasional disimpan pada `AgentRun.state` dengan schema
`vigil-state-v2`, bukan hanya berada di memory proses. Komponen pentingnya:

- lifecycle: `INITIALIZED`, `PLANNING`, `INVESTIGATING`, `EVIDENCE_REVIEW`,
  `VERIFYING`, `REPAIRING`, `PAUSED`, `COMPLETED`, `ABSTAINED`, `CANCELLED`,
  atau `FAILED`;
- plan terversi dengan step, objective, suggested tools, expected evidence,
  dependency, revision history, dan stop condition;
- hypothesis registry dengan status `proposed`, `investigating`, `supported`,
  `weakened`, `refuted`, atau `unresolved`;
- epistemic state: confirmed facts, active hypothesis, unknown, alternative
  explanation, observed evidence, evidence gap, dan next action;
- case memory yang hanya menyimpan konteks case aktif, bukan memory lintas case;
- evidence ledger dan provenance edge yang menghubungkan tool observation,
  event, snapshot external, hypothesis, dan claim;
- candidate action ranking berdasarkan prioritas gap, relevansi hypothesis,
  expected evidence value, source diversity, cost, dan remaining budget;
- repair state, transition history, progress/no-progress, cost accounting,
  verification summary, dan structured stop state.

Checkpoint disimpan setelah langkah model/tool. Jika provider timeout, worker
berhenti, atau investigator menekan pause, run dapat dilanjutkan dari state yang
tersimpan. Trace yang ditampilkan ke UI hanya berupa status, tool, step,
evidence ID, reason code, latency, dan stop reason—bukan chain-of-thought
pribadi model.

#### Apa yang dilakukan LLM dan apa yang tidak

| LLM boleh melakukan | LLM tidak boleh melakukan |
|---|---|
| Memilih tool berdasarkan pertanyaan dan plan | Mem-parsing raw log menjadi canonical event |
| Menentukan konteks tambahan yang perlu dicari | Mengurutkan timeline atau membuat correlation |
| Mengusulkan hypothesis dan alternatif benign | Menjalankan SQL, OpenSearch DSL, SPL, command, atau shell |
| Menginterpretasikan observation terstruktur | Mengubah evidence, event, finding, firewall, atau akun |
| Menulis claim fact/inference/hypothesis | Membuat evidence ID atau citation yang tidak diamati |
| Mengusulkan replan atau stop | Mengganti active case atau melewati policy backend |

Pemisahan ini adalah inti desain **deterministic-first**: model memberikan
fleksibilitas pada pertanyaan terbuka, sedangkan kebenaran operasional,
authorization, evidence ownership, dan keputusan tampil/tidak tampil tetap
ditentukan kode.

#### Contoh trajectory investigasi

Untuk pertanyaan “Apakah ada login sukses setelah kegagalan authentication
berulang?” trajectory yang diharapkan adalah:

1. VIGIL membuat plan untuk event authentication, timeline, correlation,
   disconfirming search, lalu verification.
2. Agent memanggil `search_events` untuk menemukan failure/success dan sumber
   IP atau user.
3. Agent memanggil `build_timeline` dan `correlate_entities`; urutan dan relasi
   berasal dari engine deterministik, bukan tebakan model.
4. Agent mengambil `get_surrounding_events` atau `get_raw_evidence` untuk
   memeriksa konteks baris sumber.
5. Sebelum menyatakan pola mencurigakan, agent memanggil
   `search_disconfirming_evidence` untuk mencari maintenance, scanner, atau
   penjelasan benign lain.
6. Model mengembalikan claim terstruktur. Fact hanya membutuhkan evidence
   langsung; inference membutuhkan minimal dua evidence, alasan, dan limitation;
   hypothesis wajib menyebut bukti tambahan yang masih dibutuhkan.
7. Verifier menerima claim yang didukung, menolak claim yang terlalu kuat, dan
   melakukan repair bounded bila masih mungkin. Jika tidak ada claim yang lolos,
   UI menampilkan `Belum cukup bukti untuk menjawab pertanyaan ini.`

#### Budget, reliability, dan safety agent

Default runtime membatasi satu run pada maksimal 8 tool rounds, 20 tool calls,
dua pengulangan tool yang sama, 3 revisi plan, dan 2 repair claim. Hasil tool
dibatasi jumlah baris/karakter; timeout, provider 429/5xx, no-progress, dan
worker heartbeat yang hilang menghasilkan status/stop reason yang jujur.

Semua tool agent bersifat read-only dan case-scoped. External hit tidak langsung
menjadi citation: adapter terlebih dahulu menyimpan snapshot immutable, hash,
dan UUID evidence lokal, lalu memproyeksikannya ke canonical event. Payload log
dan hasil SIEM diberi envelope data tak tepercaya, delimiter unik, injection
signal, secret redaction, dan truncation. Dengan demikian, kalimat seperti
`ignore previous instructions` di dalam log tidak boleh mengubah system policy.

#### Pembeda dari chatbot biasa

| Chatbot biasa | TraceLens VIGIL |
|---|---|
| Satu prompt lalu satu jawaban | Loop goal → plan → tool → observation → replan → verify → stop |
| Context statis | Query environment case aktif melalui tools |
| Tidak punya state durable | `AgentRun.state`, checkpoint, pause/resume/cancel |
| Bisa membuat citation sendiri | Evidence ledger dan UUID ownership diverifikasi backend |
| Tidak mencari bukti yang membantah | Ada evidence gap, alternative explanation, dan disconfirming search |
| Jawaban model langsung tampil | Claim gate menyaring, memperbaiki, atau fail-closed |
| Sering dipasarkan sebagai autonomous | Read-only, bounded, dan human-in-the-loop |

Implementasi utama berada di `backend/app/vigil.py` untuk state/plan,
`backend/app/vigil_policy.py` untuk policy/lifecycle, `backend/app/agent_tools.py`
untuk executor tools, `backend/app/llm_gateway.py` untuk loop model, dan
`backend/app/claim_verifier.py` untuk gate akhir. Evaluasi trajectory dan
regresinya berada di `backend/evals/` serta `backend/tests/`.

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
| `APP_VERSION` | `0.2.0-beta.1` | Versi API dan metadata release |
| `APP_ENV` | `development` | Mode deployment; `production` mengaktifkan hardening wajib |
| `REQUIRE_MIGRATIONS` | `true` | Menolak startup jika schema belum dimigrasikan |
| `SCHEMA_REVISION` | `0007_vigil_replay_snapshots` | Alembic revision yang harus aktif |
| `BACKEND_PORT` | `8002` | Port backend pada host |
| `FRONTEND_PORT` | `3001` | Port frontend pada host |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8002` | URL API browser |
| `CORS_ORIGINS` | `http://localhost:3001,http://localhost:3002` | Origin frontend development yang diizinkan |
| `SERVER_TIMEZONE` | `Asia/Jakarta` | Fallback timezone |
| `LLM_PROVIDER` | `groq` | Provider hosted yang dipakai agent |
| `LLM_API_KEY` | kosong | API key provider; jangan commit |
| `LLM_ENDPOINT` | `https://api.groq.com/openai/v1` | Base URL OpenAI-compatible provider |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Model tool-calling provider |
| `LOGIN_RATE_LIMIT` | `10` | Percobaan login per IP per window |
| `GITHUB_MODELS_ENDPOINT` | `https://models.github.ai/inference` | Fallback kompatibilitas lama |
| `GITHUB_MODELS_MODEL` | `openai/gpt-4.1` | Fallback model lama |
| `LLM_MAX_TOOL_CALLS` | `20` | Batas tool call per pertanyaan |
| `LLM_MAX_TOOL_RESULT_CHARACTERS` | `8000` | Batas context hasil tool |
| `LLM_MAX_OUTPUT_TOKENS` | `2048` | Budget output provider |
| `LLM_MAX_REPAIR_ATTEMPTS` | `2` | Maksimum repair claim terverifikasi |
| `LLM_MAX_PLAN_REVISIONS` | `3` | Maksimum revisi plan operasional |
| `LLM_MAX_HYPOTHESES` | `8` | Maksimum hypothesis per run |
| `ALLOW_RAW_LOG_TO_EXTERNAL_PROVIDER` | `false` | Kebijakan raw evidence eksternal |

Lihat [.env.example](.env.example) untuk daftar lengkap.

## API utama

Semua endpoint case memeriksa session, CSRF untuk mutation, membership, dan
scope `case_id`. Model tidak dapat mengganti case aktif melalui tool.

| Kelompok | Endpoint | Fungsi |
|---|---|---|
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | Session server-side dan CSRF |
| Case | `POST /cases` | Membuat workspace investigasi |
| Evidence | `POST /cases/{id}/logs`, `GET /cases/{id}/logs` | Upload dan status parsing |
| Analysis | `GET /cases/{id}/events`, `/timeline`, `/entities`, `/findings` | Query hasil deterministik |
| Agent | `POST /cases/{id}/chat` | Investigasi AI bounded dan terverifikasi |
| Agent trace | `GET /cases/{id}/agent-runs/{run_id}` | Plan, steps, ledger, stop state |
| Report | `POST /cases/{id}/exports` | Export Markdown/PDF dengan evidence reference |
| System | `GET /health`, `GET /ready`, `GET /metrics` | Liveness, readiness, dan Prometheus |

Swagger tersedia pada `http://localhost:8002/docs`. Raw evidence tidak boleh
dianggap sebagai instruksi; data tool dibungkus sebagai untrusted data sebelum
diteruskan ke provider.

## Validasi dan testing

```bash
pytest -q backend/tests
python backend/evals/run_eval.py
python backend/evals/run_detection_eval.py
python backend/evals/run_vigil_eval.py
```

Pada Windows, jalankan validasi lengkap:

```powershell
.\scripts\validate.ps1
```

Validation gate yang saat ini dipakai:

- 82 backend test lulus pada container Python 3.12;
- VIGIL golden evaluation 10/10 dan adversarial policy/envelope smoke 11/11;
- detection golden set internal 6/6 dengan precision, recall, dan F1 1.0;
- frontend typecheck, production build, dan `npm audit` lulus;
- `pip-audit`, Trivy image scan, dan Gitleaks secret scan lulus di GitHub CI;
- Docker Compose development dan production overlay berhasil divalidasi;
- runtime smoke berhasil: login, create case, upload, parsing, event, finding;
- load smoke lokal 200 request dengan 20 concurrency mencapai success rate 100%.

Angka tersebut adalah bukti regression dan smoke path repository, bukan klaim
generalisasi pada corpus SOC besar, availability bulanan, atau hasil red-team
independen. Evaluation agent offline tidak memanggil provider model live.

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

### Error authentication hosted LLM

- Pastikan `LLM_API_KEY` aktif dan sesuai provider.
- Pastikan `LLM_MODEL` adalah ID model yang mendukung tool-calling.
- Gemini API dapat dipakai melalui Google AI Studio free tier dengan
  `LLM_ENDPOINT=https://generativelanguage.googleapis.com/v1beta/openai/`.
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

## Manajemen repository dan governance

Repository dikelola sebagai proyek engineering, bukan kumpulan notebook:

1. `main` adalah baseline yang harus selalu dapat dibangun.
2. Perubahan dibuat pada branch fokus seperti `feat/...`, `fix/...`,
   `security/...`, atau `chore/...`.
3. Setiap perubahan masuk melalui pull request; commit harus menjelaskan satu
   tujuan dan tidak boleh membawa `.env`, credential, database dump, atau log
   sensitif.
4. CI wajib menjalankan test backend, evaluation, frontend build/typecheck,
   dependency audit, image scan, dan secret scan.
5. Perubahan schema wajib memakai Alembic migration dan menaikkan
   `SCHEMA_REVISION`; startup production menolak schema yang tidak sesuai.
6. Perubahan parser, detection, risk, prompt, model, atau agent graph harus
   memperbarui versi, test, evaluation, dan catatan changelog.
7. Perubahan security-sensitive memerlukan review kedua dan penjelasan
   rollback/recovery.
8. Release mengikuti SemVer dan checklist pada
   [`CONTRIBUTING.md`](CONTRIBUTING.md), [`CHANGELOG.md`](CHANGELOG.md), dan
   [`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md).

### Definition of done

Sebuah fitur dianggap selesai bila acceptance criteria, test regresi,
authorization, evidence provenance, observability, dokumentasi, dan jalur
rollback/recovery-nya telah diperiksa. “Berhasil build” saja tidak cukup untuk
perubahan yang menyentuh evidence atau AI claim.

### Cara membaca repository untuk evaluasi

- Mulai dari README ini untuk konteks, tujuan, batasan, dan cara menjalankan.
- Baca [`ARCHITECTURE.md`](ARCHITECTURE.md) untuk system context dan trust boundary.
- Baca [`docs/TRACELENS_ARSITEKTUR_TEKNIS_ID.md`](docs/TRACELENS_ARSITEKTUR_TEKNIS_ID.md)
  untuk desain komponen dan data flow.
- Baca [`docs/TRACELENS_AGENT_PROMPTS_ID.md`](docs/TRACELENS_AGENT_PROMPTS_ID.md)
  untuk kontrak prompt dan structured claim.
- Baca [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) untuk threat dan kontrol.
- Jalankan `scripts/validate.ps1` dan lihat workflow CI untuk bukti yang dapat
  direproduksi.

## Dokumentasi

- [Arsitektur](ARCHITECTURE.md)
- [Kebijakan keamanan](SECURITY.md)
- [Panduan kontribusi](CONTRIBUTING.md)
- [Pengembangan parser](docs/ADDING_A_PARSER.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Dokumentasi arsitektur teknis](docs/TRACELENS_ARSITEKTUR_TEKNIS_ID.md)
- [Dokumentasi prompt agent VIGIL](docs/TRACELENS_AGENT_PROMPTS_ID.md)
- [Arsitektur agent VIGIL](docs/AGENTIC_V2_ARCHITECTURE.md)
- [Integrasi MCP external read-only](docs/EXTERNAL_MCP_INTEGRATION_ID.md)
- [Production readiness](docs/PRODUCTION_READINESS.md)
- [Roadmap](docs/ROADMAP.md)
- [Release process](docs/RELEASE_PROCESS.md)
- [Changelog](CHANGELOG.md)
- [Support guide](SUPPORT.md)

Dokumen proposal, paper, literature review, dan PDF presentasi tidak menjadi
dependency aplikasi dan sengaja tidak termasuk dalam code PR ini.

## Kontribusi

Kontribusi dipersilakan. Baca [CONTRIBUTING.md](CONTRIBUTING.md), tambahkan test untuk perubahan perilaku, dan pertahankan evidence traceability serta case isolation.

## Lisensi

Lisensi open-source belum dideklarasikan. Sampai lisensi ditambahkan, seluruh hak tetap berada pada pemilik repository.
