# TraceLens AI
## Arsitektur Teknis untuk Audiensi AI Engineering

### Tujuan sistem

TraceLens AI adalah platform investigasi log keamanan yang mengubah file log heterogen menjadi event kanonik, timeline, correlation, finding, risk score, dan jawaban AI yang dapat ditelusuri ke raw evidence.

Prinsip terpentingnya adalah **deterministic-first**:

- parser, normalisasi timestamp, sorting, correlation, detection, dan risk scoring dilakukan oleh kode Python;
- LLM hanya memilih tool, membantu interpretasi, menyusun hipotesis, chat, dan report;
- setiap claim AI diverifikasi di backend sebelum dikirim ke investigator.

### 1. Technology stack

#### Application layer

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS.
- **Backend API:** FastAPI, Python, Pydantic, SQLAlchemy.
- **Database migration:** Alembic.
- **Database:** PostgreSQL 16.
- **Queue dan cache:** Redis 7.
- **Async processing:** Celery Worker dan Celery Beat.
- **Container runtime:** Docker Compose.
- **LLM provider:** LLM gateway OpenAI-compatible; konfigurasi aktif menggunakan Groq dan dapat diganti tanpa mengubah agent executor.
- **Model aktif:** `openai/gpt-oss-120b` melalui endpoint provider yang dikonfigurasi di `.env`.
- **Testing:** pytest, parser/detection evaluation, frontend typecheck, production build.

#### Storage dan observability

- Docker volume untuk evidence file dalam development.
- SHA-256 untuk identitas dan integrity evidence.
- PostgreSQL untuk metadata, event, finding, audit, dan agent run.
- Prometheus metrics dan SLO rules tersedia untuk baseline observability.

### 2. Context diagram

```text
┌─────────────────┐       HTTPS/session/CSRF       ┌─────────────────┐
│ SOC Investigator│ ─────────────────────────────▶ │ Next.js Frontend│
└─────────────────┘                                └────────┬────────┘
                                                           │ REST/JSON
                                                           ▼
                                                  ┌─────────────────┐
                                                  │ FastAPI Backend  │
                                                  └──┬─────┬──────┬──┘
                                                     │     │      │
                                             SQL/ORM  │     │      │ HTTPS
                                                     ▼     ▼      ▼
                                             ┌───────┐ ┌─────┐ ┌─────────────┐
                                             │Postgres│ │Redis│ │LLM Gateway │
                                             └───────┘ └──┬──┘ └─────────────┘
                                                         │ broker/backend
                                                         ▼
                                                  ┌──────────────┐
                                                  │Celery worker  │
                                                  │+ scheduler    │
                                                  └──────┬───────┘
                                                         │
                                                         ▼
                                                  ┌──────────────┐
                                                  │Evidence volume│
                                                  └──────────────┘
```

### 3. Tanggung jawab service

#### Frontend

Next.js menyediakan halaman login, dashboard case, upload, timeline, event explorer, chat AI, findings, dan report. Frontend tidak melakukan analisis keamanan sendiri; frontend memanggil API dan menampilkan hasil yang sudah diverifikasi backend.

#### FastAPI backend

Backend mengelola authentication, authorization, case membership, upload validation, endpoint query, audit log, deterministic analysis trigger, agent orchestration, claim verification, dan export report.

#### PostgreSQL

PostgreSQL adalah system of record. Query child resource selalu dibatasi oleh `case_id` dan membership user.

#### Redis dan Celery

Upload file besar tidak diproses di request HTTP. Backend menyimpan evidence dan membuat job, Redis menjadi broker, lalu Celery worker melakukan detection, parsing, normalization, correlation, detection, dan rebuild finding.

#### LLM Gateway

Gateway hanya meneruskan system policy, state terpilih, dan observation yang sudah dibatasi. Provider aktif saat ini adalah Groq melalui API OpenAI-compatible. LLM tidak diberi akses database langsung dan tidak membuat canonical event. Penggantian provider dilakukan melalui konfigurasi, bukan dengan memindahkan parsing atau policy ke provider.

### 4. Data flow end-to-end

```text
POST /cases/{id}/logs
        │
        ├─ validasi ukuran, extension, MIME, UTF-8, isi, dan path
        ├─ streaming SHA-256
        ├─ simpan UUID filename pada evidence storage
        ├─ tulis evidence_files dan audit_logs
        └─ enqueue Celery job
                  │
                  ▼
        format detection berdasarkan pola isi file
                  │
                  ▼
        deterministic parser → ParsedEvent
                  │
                  ▼
        canonical events + raw_log + raw_line_number
                  │
                  ▼
        stable timeline → correlation → detection → risk → findings
                  │
                  ▼
        UI query atau AI read-only tools
```

### 5. Deterministic analysis boundary

Parser yang tersedia meliputi Linux auth/syslog, Nginx/Apache access log, JSON application, CSV application, dan parser text/logfmt yang dikontrol konfigurasi. Format unsupported seharusnya ditolak atau diberi status experimental, bukan dianggap sebagai fakta keamanan.

Setiap event kanonik menyimpan:

- `event_id` dan `case_id`;
- `timestamp_original` dan `timestamp_normalized`;
- timezone serta provenance asumsi tahun/timezone;
- source type, host, category, action, outcome, severity;
- username, source IP, destination IP, process, file;
- `raw_log` dan `raw_line_number`;
- `evidence_file_id`, parser name, parser version, confidence, dan tags.

Timeline diurutkan berdasarkan timestamp normalized. Tie-breaker menggunakan line/provenance sehingga urutan dapat direproduksi.

Correlation rule-based menggunakan shared source IP, username, atau session dalam window konfigurasi. Setiap correlation memiliki `correlation_reason`, misalnya `shared source_ip within 10 minutes`.

Risk score explainable menggunakan komponen severity, frequency, privilege, correlation, dan novelty. Investigator dapat melihat breakdown, bukan hanya nilai akhir.

### 6. Database model

Tabel utama:

- `users`, `user_sessions`: identity dan session server-side;
- `cases`, `case_memberships`: isolation dan role;
- `evidence_files`: filename asli, internal path, hash, size, status, parser job;
- `events`: canonical security events dan provenance raw log;
- `quarantined_lines`: baris malformed pada mode quarantine;
- `correlations`: hubungan event dan correlation reason;
- `findings`: pola, risk score, breakdown, MITRE context, workflow status;
- `agent_runs`: pertanyaan, trajectory, tool budget, status, dan state;
- `audit_logs`: upload, login, chat, citation, integrity verification, export, dan perubahan workflow.

Raw event fields dijaga immutable setelah ingestion. Evidence bytes dan metadata hash menjadi dasar chain-of-custody development baseline.

### 7. AI agent architecture

TraceLens menggunakan **single agent dengan banyak read-only tools**, bukan multi-agent.

Tools utama:

- `search_events(case_id, filters)`;
- `get_surrounding_events(event_id, window)`;
- `build_timeline(case_id)`;
- `correlate_entities(case_id, entity)`;
- `get_raw_evidence(event_id)`;
- `generate_case_summary(case_id)`.

Alur chat:

```text
Investigator question
        ▼
LLM gateway + system policy
        ▼
tool call dengan case_id aktif
        ▼
ToolRegistry query scoped ke case
        ▼
hasil dibungkus sebagai UNTRUSTED_DATABASE_DATA
        ▼
LLM menyusun structured claims
        ▼
claim verification gate
        ▼
jawaban yang ditampilkan ke user
```

Structured response:

```json
{
  "answer": "Reconstructed only from verified claims.",
  "claims": [
    {
      "claim_id": "claim-001",
      "text": "Repeated authentication failures came from one IP.",
      "status": "fact",
      "supporting_evidence_ids": ["event-uuid"],
      "confidence": 0.95,
      "limitations": [],
      "required_additional_evidence": []
    }
  ]
}
```

Backend memeriksa evidence existence, active-case ownership, claim status, minimum support untuk inference/hypothesis, entity consistency, count consistency, limitations, dan overclaim seperti compromise atau attribution. Jawaban final dibangun ulang dari claims yang lolos.

#### Struktur runtime agentic VIGIL

VIGIL (*Verified Investigation Graph & Evidence Loop*) adalah supervisor
single-agent yang mengatur model, tools, state, evidence, dan verifier. Model
tidak menjadi sumber kebenaran tunggal. Model hanya mengusulkan langkah; policy
dan executor backend yang mengizinkan serta menjalankan langkah tersebut.

```text
                         +----------------------+
                         | Investigator question|
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         | FastAPI case boundary|
                         | auth, membership,    |
                         | active case, audit   |
                         +----------+-----------+
                                    |
                                    v
                 +----------------+----------------+
                 |       VIGIL Supervisor           |
                 | goal + plan + lifecycle + state   |
                 +--------+---------------+-----------+
                          |               |
                  policy check       LLM gateway
                          |               |
                          v               v
                 +--------+-------+  +----+---------+
                 | Tool Policy    |  | Model         |
                 | allowlist,     |  | tool choice,  |
                 | case scope,    |  | hypothesis,   |
                 | budget, state  |  | structured JSON|
                 +--------+-------+  +----+---------+
                          |               |
                          +-------+-------+
                                  v
                         +----------------------+
                         | ToolRegistry          |
                         | local DB tools / MCP  |
                         | read-only executor    |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         | Observation envelope |
                         | untrusted data,       |
                         | redaction, truncation |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         | State + evidence      |
                         | ledger + provenance   |
                         | gap + hypothesis      |
                         +----------+-----------+
                                    |
                         +----------+----------+
                         |                     |
                         v                     v
                  next action/replan    Claim Verification Gate
                                               |
                              +----------------+----------------+
                              |                                 |
                              v                                 v
                     verified claims                  repair <= 2 / abstain
                              |                                 |
                              +----------------+----------------+
                                               v
                                      answer + audit + stop state
```

#### Komponen dan tanggung jawab agent

| Komponen | Implementasi | Tanggung jawab |
|---|---|---|
| Goal boundary | FastAPI `case_id` dan `AgentRun.question` | Mengikat pertanyaan ke case aktif dan membership investigator |
| Plan/state | `backend/app/vigil.py` | Membuat plan, hypothesis, evidence gap, next action, provenance, dan stop state |
| Policy engine | `backend/app/vigil_policy.py` | Memvalidasi lifecycle transition, tool allowlist, budget, repetition, replan, repair, dan stop |
| Model gateway | `backend/app/llm_gateway.py` | Mengirim policy/state terpilih ke model, menjalankan loop, retry terbatas, checkpoint, dan redaction |
| Tool executor | `backend/app/agent_tools.py` | Menjalankan query case-scoped yang terstruktur; tidak menerima arbitrary SQL/DSL/command |
| External adapter | `external_sources.py`, `mcp_server.py` | Mencari telemetry OpenSearch/Splunk/Wazuh secara read-only dan membuat snapshot lokal |
| Observation boundary | untrusted data envelope | Memisahkan data log dari instruksi system dan menandai prompt-injection signal |
| Evidence ledger | `AgentStep`, `EvidenceLedger`, `external_evidence` | Mencatat evidence yang benar-benar diamati dan asal provenance-nya |
| Claim verifier | `backend/app/claim_verifier.py` | Menolak claim invalid, unsupported, lintas case, atau terlalu kuat |
| Replay | `backend/app/replay.py` | Membuat snapshot run dan replay deterministik tanpa memanggil model |

#### Lifecycle agent

State machine VIGIL menggunakan state berikut:

```text
INITIALIZED
    -> PLANNING
    -> INVESTIGATING
    -> EVIDENCE_REVIEW
    -> VERIFYING
    -> COMPLETED       (claim lolos)
    -> ABSTAINED       (bukti tidak cukup)
    -> FAILED          (provider/runtime failure)

INVESTIGATING <-> EVIDENCE_REVIEW
VERIFYING -> REPAIRING -> INVESTIGATING
INVESTIGATING/VERIFYING -> PAUSED -> INVESTIGATING
INVESTIGATING/VERIFYING -> CANCELLED
```

State terminal tidak dapat berjalan kembali secara normal. Resume hanya
diizinkan dari run `paused` atau `failed`, lalu state dipulihkan dari checkpoint
terakhir. Setiap transisi menyimpan alasan, timestamp, versi state machine, dan
history sehingga investigator dapat memahami mengapa run berhenti.

#### Siklus model--tool--observation--state

1. **Initialize goal.** Backend membuat `AgentRun` dengan `case_id`, question,
   prompt version, model version, graph version, dan state schema.
2. **Create plan.** `create_investigation_plan()` membuat step deterministik
   berdasarkan fokus pertanyaan, misalnya authentication, timeline,
   correlation, disconfirming evidence, dan verification. Model boleh
   mengusulkan revisi, tetapi maksimal tiga revisi dan hanya memakai tool yang
   ada di allowlist.
3. **Select action.** Model melihat system policy, public state summary, plan
   step, dan tool schema. Model memilih tool; model tidak mengirim SQL atau
   koneksi database.
4. **Authorize action.** `InvestigationPolicy` memeriksa current state, active
   case, nama tool, jumlah call, pengulangan, precondition, dan remaining
   budget. Operasi ilegal ditolak sebelum executor berjalan.
5. **Execute tool.** `ToolRegistry` mengambil event, timeline, correlation,
   raw evidence, summary, atau external snapshot dari database secara
   deterministik. Maksimal row dan window dibatasi.
6. **Observe safely.** Hasil dibungkus sebagai data tidak tepercaya, dipotong
   jika terlalu besar, secret di-redact, dan prompt-injection pattern hanya
   menjadi signal keamanan—bukan instruksi yang harus diikuti.
7. **Update state.** Evidence ID yang diamati masuk ledger. State memperbarui
   hypothesis, evidence quality, contradiction matrix, gap, provenance edge,
   progress, cost, dan next action.
8. **Replan atau lanjut.** Jika gap belum terjawab, agent dapat memilih tool
   berikutnya. Jika hypothesis suspicious belum diuji, policy mengarahkan
   `search_disconfirming_evidence` untuk mencari maintenance, scanner, atau
   alternatif benign.
9. **Draft claim.** Model mengembalikan JSON yang berisi answer, claims,
   hypotheses, limitations, required additional evidence, dan stop reason.
10. **Verify and repair.** Backend memeriksa setiap kalimat sebagai unit
    claim. Claim yang repairable dapat meminta evidence tambahan atau downgrade
    maksimal dua kali. Tidak ada claim yang langsung ditampilkan sebelum gate.
11. **Stop.** Run menjadi completed bila claim terverifikasi, abstained bila
    bukti tidak cukup, atau failed/paused/cancelled sesuai kondisi runtime.

#### Isi durable state `vigil-state-v2`

```text
AgentRun.state
├── lifecycle + transition_history
├── investigation_goal + open_questions
├── plan + revision_history
├── hypotheses + hypothesis_competition
├── epistemic_state
│   ├── confirmed_facts
│   ├── active_hypotheses / rejected_hypotheses
│   ├── unknowns / alternative_explanations
│   └── evidence_gaps / observed_evidence_ids
├── case_memory (case_id scoped)
├── provenance edges
├── collected_evidence_ids + action_history
├── candidate_actions + action_ranking
├── repair_state + verification_summary
├── cost_accounting + remaining_tool_budget
└── stop_state + reason
```

State ini bukan chain-of-thought. Ia adalah state operasional yang dibutuhkan
untuk audit, pause/resume, deterministic replay, dan evaluasi trajectory.

#### Batas kerja LLM dan backend

| LLM/model | Backend deterministik |
|---|---|
| Memilih tool dan urutan pencarian | Menentukan parser, canonical event, timestamp, timeline, correlation, detection, dan risk |
| Mengusulkan hypothesis dan alternatif | Mengikat semua query ke case aktif |
| Menginterpretasikan observation terstruktur | Mengizinkan/menolak lifecycle dan tool call |
| Menyusun fact, inference, atau hypothesis | Memvalidasi UUID evidence, ownership, entity, count, semantic support, dan limitation |
| Mengusulkan replan atau stop | Menyimpan state, ledger, audit, hash, checkpoint, dan stop reason |

Artinya, agentic autonomy berada pada **pemilihan langkah investigasi dan
adaptasi terhadap evidence**, bukan pada perubahan sistem eksternal. TraceLens
tetap single-agent karena scope-nya adalah investigasi read-only yang dapat
direplay; menambah banyak agent tidak otomatis membuat reasoning lebih benar.

#### Contoh trajectory konkret

Pertanyaan investigator: *"Apakah ada login sukses setelah rentetan login
gagal dari IP yang sama?"*

```text
1. Plan: authentication -> timeline -> correlation -> disconfirm -> verify
2. search_events: ambil failure/success, source_ip, username, timestamp
3. build_timeline: ambil urutan stabil dari database
4. correlate_entities: ambil relasi source_ip dan alasan window waktu
5. get_surrounding_events/get_raw_evidence: cocokkan raw line sumber
6. search_disconfirming_evidence: cari maintenance/scanner/benign context
7. Draft claim: fact/inference/hypothesis dengan evidence UUID
8. Verifier: terima, downgrade, repair, atau tolak claim
9. Stop: GOAL_SATISFIED atau INSUFFICIENT_EVIDENCE
```

Pada trajectory ini LLM tidak menghitung apakah lima event benar-benar berada
di window sepuluh menit; engine correlation yang menghitungnya. LLM menjelaskan
hasil dan memilih konteks tambahan. Jika hanya terdapat event gagal tanpa event
success, sistem tidak boleh mengubahnya menjadi fakta "login berhasil".

### 8. AI guardrails dan konfigurasi

Konfigurasi penting:

```env
LLM_PROVIDER=groq
LLM_ENDPOINT=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-120b
LLM_MAX_TOOL_ROUNDS=8
LLM_MAX_TOOL_CALLS=20
LLM_MAX_TOOL_RESULT_CHARACTERS=8000
LLM_TIMEOUT_SECONDS=60
ALLOW_RAW_LOG_TO_EXTERNAL_PROVIDER=false
```

`LLM_MAX_TOOL_CALLS=20` membatasi jumlah tool call per pertanyaan agar agent tidak loop dan biaya tetap terkendali. Ini bukan ukuran akurasi model.

Raw log dianggap untrusted data, diberi delimiter unik, secret redaction, truncation, dan instruksi agar model mengabaikan perintah apa pun di dalam log. Provider raw evidence sharing dimatikan secara default.

### 9. Security architecture

- PBKDF2-SHA256 dengan salt untuk password.
- Random session token disimpan sebagai hash.
- HttpOnly dan SameSite session cookie.
- CSRF protection pada mutation endpoint.
- Role dan membership check untuk semua case resource.
- UUID internal untuk evidence filename.
- Path traversal, absolute path, extension, MIME, size, UTF-8, dan content validation.
- SHA-256 integrity verification.
- Audit log untuk upload, chat, citation, export, dan integrity check.
- Rate limit untuk login, upload, dan chat menggunakan Redis fixed-window limiter.
- Docker production baseline: non-root, read-only filesystem, drop capabilities, dan no-new-privileges.

### 10. API surface utama

```text
POST /auth/login
POST /auth/logout
GET  /auth/me

POST /cases
POST /cases/{case_id}/logs
GET  /cases/{case_id}/logs
GET  /cases/{case_id}/jobs/{job_id}
POST /cases/{case_id}/logs/{evidence_file_id}/verify

GET  /cases/{case_id}/events
GET  /cases/{case_id}/events/{event_id}
GET  /cases/{case_id}/timeline
GET  /cases/{case_id}/entities
GET  /cases/{case_id}/findings
POST /cases/{case_id}/chat
POST /cases/{case_id}/exports
```

### 11. Deployment topology

Development dijalankan dengan Docker Compose:

```text
postgres:16-alpine
redis:7-alpine
backend: FastAPI + Alembic
worker: Celery worker
scheduler: Celery Beat
frontend: Next.js
```

Host port default:

- frontend `localhost:3001`;
- backend `localhost:8002`;
- PostgreSQL dan Redis tetap berada di network Compose.

Production overlay menambahkan hardening container. Untuk production sungguhan masih dibutuhkan TLS/WAF, managed secrets, private database/object storage, centralized immutable audit retention, backup restore drill, SLO alerting, DAST, dan independent security assessment.

### 12. Arsitektur target terbaik yang direkomendasikan

Arsitektur terbaik untuk TraceLens bukan memecah sistem menjadi banyak agent.
Pilihan yang paling kuat adalah **bounded single-agent di atas deterministic
analysis plane**, dengan pemisahan data, reasoning, policy, dan execution.

```text
                    +-----------------------------+
                    | Investigator / SOC reviewer |
                    +--------------+--------------+
                                   | HTTPS + session/CSRF
                                   v
                    +-----------------------------+
                    | Next.js Investigator UI     |
                    | case, evidence, trace,      |
                    | findings, report            |
                    +--------------+--------------+
                                   | REST/JSON/multipart
                                   v
                    +-----------------------------+
                    | FastAPI Case Boundary       |
                    | authz, membership, API,     |
                    | audit, orchestration        |
                    +--+----------+----------+----+
                       |          |          |
                SQL/ORM |     enqueue      policy
                       v          v          v
             +---------+--+  +----+-----+  +--+------------------+
             | PostgreSQL |  | Redis     |  | VIGIL Supervisor   |
             | system of  |  | broker,   |  | goal, plan, state, |
             | record     |  | lock, RL  |  | repair, stop       |
             +------+-----+  +----+------+  +--+------------------+
                    |             |            |
                    |             v            v read-only tools
                    |       +-----+------+  +--+------------------+
                    |       | Celery     |  | Tool Policy        |
                    |       | parser +   |  | allowlist, case    |
                    |       | analysis   |  | scope, budget      |
                    |       +-----+------+  +--+------------------+
                    |             |            |
                    v             v            v
             +------+-----+  +----+------+  +--+------------------+
             | Evidence   |  | Canonical |  | Private MCP        |
             | storage    |  | events,   |  | OpenSearch/Splunk/ |
             | UUID+hash  |  | timeline, |  | Wazuh read-only    |
             +------------+  | findings  |  +---------------------+
                              +-----------+
                                   |
                                   v
                    +-----------------------------+
                    | Claim Verification Gate     |
                    | evidence, semantics, status |
                    | limitation, fail-closed     |
                    +--------------+--------------+
                                   |
                                   v
                    +-----------------------------+
                    | Verified answer + audit     |
                    | human approval before any   |
                    | future write action         |
                    +-----------------------------+
```

#### Alasan desain ini paling tepat

1. **Deterministic substrate tetap menjadi sumber kebenaran operasional.**
   Parsing, timestamp, timeline, correlation, detection, dan risk tidak boleh
   diserahkan ke model probabilistik.
2. **Agent diberi autonomy secukupnya.** Agent dapat memilih urutan pencarian,
   memperbarui hypothesis, mencari evidence yang membantah, dan berhenti saat
   bukti kurang; agent tidak dapat mengubah sistem eksternal.
3. **Case boundary menjadi batas keamanan utama.** Semua query, evidence ID,
   memory, external snapshot, dan report harus terikat case aktif.
4. **MCP berada di belakang Tool Policy.** Model tidak menerima arbitrary DSL,
   credential, atau koneksi langsung ke SIEM.
5. **Verifier berada setelah LLM dan sebelum UI.** Draft model tidak pernah
   menjadi jawaban final tanpa pemeriksaan evidence dan semantic support.
6. **Human-in-the-loop tetap eksplisit.** Jika kelak ditambahkan action tool,
   tool tersebut harus berada pada capability tier R1/R2/R3 dan memerlukan
   approval manusia, audit, serta rollback.

#### Critical path yang harus dipertahankan

```text
Upload
  -> validate + SHA-256 + UUID evidence
  -> enqueue asynchronous job
  -> parser deterministic
  -> canonical event
  -> timeline/correlation/detection/risk
  -> investigator question
  -> VIGIL plan + read-only tool calls
  -> evidence ledger + hypothesis/gap update
  -> structured claim
  -> verification gate
  -> verified answer atau abstention
```

Kegagalan di setiap tahap harus fail-closed: file malformed masuk quarantine
atau gagal, provider LLM gagal menjadi provider failure, evidence tidak cukup
menjadi abstention, dan claim unsupported tidak ditampilkan.

#### Target non-functional requirement bertahap

| Area | Target staging/beta | Cara verifikasi |
|---|---|---|
| Availability API | 99,5% bulanan | Prometheus/SLO dan error budget |
| Read latency | p95 endpoint read < 500 ms | load test terukur |
| Agent latency | p95 bounded run < 60 s tanpa provider outage | trace latency dan timeout test |
| Upload | 50 MiB default dengan streaming limit | security/integration test |
| Evidence durability | RPO <= 1 jam, RTO <= 4 jam | backup/restore drill |
| Isolation | cross-case leakage target 0 | authorization matrix dan RLS/E2E |
| Safety | unauthorized write action target 0 | capability test; saat ini write tool tidak tersedia |
| Audit | semua upload, tool, claim, export tercatat | audit completeness test |

Target tersebut adalah acceptance criteria yang harus diukur, bukan klaim bahwa
semuanya sudah terpenuhi pada local development.

#### Keputusan arsitektur yang ditolak

- **LLM sebagai parser utama:** ditolak karena menurunkan reproducibility dan
  mempersulit provenance.
- **Multi-agent kosmetik:** ditolak karena menambah trust boundary tanpa bukti
  peningkatan kualitas pada scope penelitian saat ini.
- **Model mengakses database langsung:** ditolak karena membuka arbitrary query,
  IDOR, dan credential blast radius.
- **Active response default:** ditolak karena konsekuensi tinggi; hanya boleh
  muncul setelah approval gate dan rollback tersedia.
- **External SIEM sebagai sumber citation langsung:** ditolak; hasil harus
  disnapshot, di-hash, dan diberi UUID lokal terlebih dahulu.

#### Tahapan menuju production

1. **R0 — Research/demo:** Compose, local evidence volume, read-only agent,
   golden fixture, claim gate, dan audit aplikasi.
2. **R1 — Staging:** managed PostgreSQL/Redis, object storage terenkripsi,
   secret manager, TLS, backup drill, user quota, RLS defense-in-depth,
   provider fixture/replay, dan adversarial test.
3. **R2 — Beta terbatas:** external append-only audit, load/soak test,
   gate-off/on comparison, corpus eksternal, independent red-team, SLO alert,
   dan signed release checklist.
4. **R3 — Action-enabled ops (opsional):** capability token, approval manusia
   minimal dua pihak untuk action berisiko, dry-run, rollback, dan audit
   immutable. Tahap ini tidak diperlukan untuk tujuan MVP investigasi read-only.

Dengan struktur tersebut, TraceLens tetap sederhana untuk dipelajari namun
memiliki jalur evolusi yang jelas ke beta operasional tanpa mengorbankan
evidence grounding, keamanan case, atau auditability.

### 13. VIGIL Phase 2: reliability dan evaluasi

Implementasi Phase 2 menambahkan state machine eksplisit dan policy engine
deterministik di antara LLM gateway dan executor. Agent hanya mengusulkan
operasi; policy memeriksa transisi lifecycle, allowlist tool, case boundary,
budget, repair, replan, hypothesis update, dan stop reason.

State operasional juga menyimpan evidence quality (integrity, parser,
timestamp, directness, source, corroboration), contradiction matrix
`SUPPORTS/CONTRADICTS/NEUTRAL/UNKNOWN`, hypothesis revision history,
candidate action ranking, estimated cost, useful evidence, no-progress, serta
stop state. Nilai quality bukan probabilitas serangan.

Setiap run selesai disnapshot dengan hash kanonik. Endpoint deterministic replay
tidak memanggil model; model re-evaluation belum diaktifkan karena memerlukan
provider fixture yang dibekukan. Run diff bersifat deskriptif dan tidak memilih
run yang lebih benar secara otomatis. Evaluasi offline disimpan bersama fixture
dan test di `backend/evals/`, sehingga dapat direproduksi tanpa provider live.

### 14. Review arsitektur terbaru

#### Verdict

Arsitektur ini sudah tepat untuk **beta operasional read-only** dan layak
digunakan sebagai arsitektur referensi saat presentasi. Nilai indikatif untuk
arsitektur teknis saat ini adalah **9,0/10**. Nilai ini bukan sertifikasi
keamanan, bukan jaminan availability, dan tidak boleh dipakai sebagai bukti
forensic-grade.

#### Bentuk final yang direkomendasikan

```text
Investigator / SOC reviewer
        |
        v HTTPS + session/CSRF
Next.js Investigator UI
        |
        v REST / multipart
FastAPI Case Boundary
        |-- PostgreSQL: system of record
        |-- Redis/Celery: queue, lock, retry, watchdog
        |-- Evidence storage: UUID + SHA-256 + immutable bytes
        |-- Deterministic analysis plane
        |     parser -> canonical event -> timeline -> correlation
        |     -> detection -> risk -> findings
        `-- VIGIL Supervisor
              |-- goal, plan, lifecycle, budget, stop state
              |-- Tool Policy: allowlist + case scope + capability
              |-- local read-only tools / private MCP adapters
              |-- untrusted observation + evidence ledger
              |-- hypothesis, contradiction, gap, replanning
              `-- Claim Verification Gate
                    |-- verified claims -> UI/report/audit
                    `-- unsupported -> repair <= 2 atau abstention
```

LLM berada di dalam VIGIL Supervisor sebagai komponen pengusul langkah. LLM
tidak pernah menjadi parser, sumber urutan timeline, pemilik koneksi database,
atau pemanggil write action. Executor deterministik dan policy engine tetap
menentukan apakah usulan model boleh dijalankan.

#### Kekuatan yang terverifikasi di repository

1. Boundary deterministic dan probabilistic terpisah dengan jelas.
2. Semua tool agent allowlisted, bounded, read-only, dan case-scoped.
3. Evidence memiliki provenance, ledger, quality metadata, dan snapshot hash.
4. VIGIL memiliki lifecycle transition, budget, no-progress, hypothesis
   revision, contradiction matrix, repair bounded, dan structured stop.
5. Claim gate berada di antara model dan UI; claim unsupported tidak ditampilkan.
6. Replay trace bersifat deterministic dan tidak memanggil model.
7. Default Compose telah diselaraskan dengan runtime saat ini: schema `0007`,
   frontend `3001`, backend `8002`, serta Groq sebagai provider aktif.

#### Batas keamanan yang wajib dipertahankan

- Raw log, URL, user-agent, dan hasil SIEM selalu diperlakukan sebagai data
  tidak tepercaya.
- Model tidak boleh menerima arbitrary SQL, DSL, credential, atau `case_id`
  yang dapat mengganti case aktif.
- External evidence harus di-snapshot, di-hash, dan diberi UUID lokal sebelum
  boleh menjadi citation.
- Jika provider gagal, budget habis, evidence berkontradiksi, atau verifier
  gagal, sistem harus berhenti dengan status yang jujur.
- Evidence quality dan risk score adalah kualitas dukungan/indikasi rule, bukan
  probabilitas attacker atau bukti kompromi.

#### Gap yang masih mencegah label 10/10

1. Belum ada model re-evaluation replay dengan provider fixture yang dibekukan.
2. Red-team independen, corpus eksternal berlabel, dan uji gate-off/on reviewer
   masih harus diperluas.
3. Load/soak, concurrency/idempotency, backup-restore RPO/RTO, dan HA belum
   dibuktikan pada deployment staging.
4. TLS/WAF, secret manager, PostgreSQL RLS, object storage terenkripsi, dan
   audit append-only eksternal masih merupakan gate deployment.
5. Provider eksternal default off; live Groq/MCP bukan dependency demo yang
   dapat diandalkan.

#### Keputusan review

Pertahankan **bounded single-agent di atas deterministic analysis plane**.
Jangan menambah multi-agent kosmetik atau active response sebelum ada
capability token, approval manusia, rollback, dan audit immutable. Prioritas
berikutnya adalah staging hardening, replay/evaluation yang dapat diaudit,
tamper-evident audit sink, serta pengukuran NFR—bukan menambah jumlah agent.

Dokumen prompt agent: [TRACELENS_AGENT_PROMPTS_ID.md](TRACELENS_AGENT_PROMPTS_ID.md).
