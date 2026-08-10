# TraceLens AI — Brief Instruksi Pengembangan Agentic AI

Dokumen ini adalah brief siap salin-tempel untuk AI engineering agent atau tim developer yang akan melanjutkan TraceLens AI. Tujuannya memperkuat sifat agentic secara nyata, bukan sekadar mengganti label chatbot menjadi “agent”.

## 1. Identitas sistem

TraceLens AI adalah asisten investigasi log keamanan siber berbasis evidence-grounded bounded single-agent.

Tujuan utama:

1. menerima log heterogen;
2. memproses log secara deterministik;
3. membangun timeline, correlation, finding, dan risk breakdown;
4. membolehkan LLM merencanakan investigasi dan memilih tool read-only;
5. menghasilkan claim fact, inference, atau hypothesis;
6. memastikan setiap claim dapat ditelusuri ke evidence valid;
7. menjaga investigator manusia sebagai pengambil keputusan akhir.

TraceLens bukan forensic-grade formal evidence system, bukan pengganti SOC analyst, dan bukan sistem autonomous response.

## 2. Arsitektur yang sudah tersedia

```text
SOC Investigator
      |
      v
Next.js Frontend :3001
      |
      | REST/JSON + session/CSRF
      v
FastAPI Backend :8002
      |
      +--> PostgreSQL 16
      |      cases, evidence_files, events, findings,
      |      correlations, agent_runs, agent_steps,
      |      evidence_ledgers, audit_logs
      |
      +--> Redis 7
      |      Celery broker, rate limiter, analysis lock
      |
      +--> Celery worker/scheduler
      |      parsing, normalization, rebuild analysis
      |
      +--> LLM Gateway
      |      Groq OpenAI-compatible API
      |      model: openai/gpt-oss-120b
      |
      +--> Private MCP layer
             OpenSearch / Splunk / Wazuh
             read-only, case-scoped, immutable snapshot
```

Konfigurasi LLM aktif:

```env
LLM_PROVIDER=groq
LLM_ENDPOINT=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-120b
LLM_MAX_TOOL_ROUNDS=8
LLM_MAX_TOOL_CALLS=20
```

API key tidak boleh ditulis di source code, commit, log, atau prompt.

## 3. Pipeline deterministik yang tidak boleh dipindahkan ke LLM

Bagian berikut harus tetap Python/regex/database biasa:

```text
upload
  -> validasi ukuran, MIME, extension, filename, UTF-8
  -> SHA-256
  -> deteksi format berdasarkan isi awal file
  -> parser deterministic
  -> canonical event
  -> timestamp normalization
  -> timezone/year assumptions
  -> stable timeline ordering
  -> correlation by IP/user/session
  -> brute-force detection
  -> explainable risk scoring
  -> findings
```

Format yang diproses:

- Linux auth.log/syslog;
- Nginx/Apache combined access log;
- JSON/JSONL aplikasi generik;
- CSV aplikasi/log yang sudah didukung implementasi.

LLM tidak boleh memparsing raw file lalu menyusun timeline sendiri. LLM hanya boleh membaca hasil tool dari database atau MCP snapshot.

## 4. Agent yang sudah tersedia

Runtime utama berada di `backend/app/llm_gateway.py`.

Agent saat ini sudah memiliki:

- model memilih dan mengurutkan function/tool secara dinamis;
- loop model -> tool -> observation -> model;
- batas `LLM_MAX_TOOL_ROUNDS`;
- batas `LLM_MAX_TOOL_CALLS`;
- batas pengulangan tool yang sama;
- timeout;
- checkpoint setelah model/tool step;
- status `running`, `complete`, `failed`, `paused`, dan `cancelled`;
- resume dari checkpoint;
- redacted trajectory;
- evidence ledger untuk evidence yang benar-benar diamati agent.

Tool lokal:

```text
search_events
get_surrounding_events
build_timeline
correlate_entities
get_raw_evidence
generate_case_summary
```

Tool external/MCP:

```text
get_external_source_status
search_external_events
```

Tool external tidak menerima arbitrary OpenSearch DSL atau SPL dari model. Query dibentuk oleh adapter backend, scope case wajib, dan hasilnya disimpan sebagai immutable `external_evidence` sebelum dapat dikutip.

## 5. Guardrail yang sudah wajib dipertahankan

### Claim Verification Gate

File utama: `backend/app/claim_verifier.py`.

Gate harus:

- memvalidasi status hanya `fact`, `inference`, atau `hypothesis`;
- memvalidasi evidence UUID;
- memvalidasi evidence berada pada case aktif;
- memvalidasi entity sesuai event;
- menolak fact yang sebenarnya overclaim interpretatif;
- meminta minimal dua evidence untuk inference;
- meminta limitation dan additional evidence untuk hypothesis;
- menolak claim tanpa support valid;
- mengembalikan “Belum cukup bukti...” jika semua claim gagal.

Gate mengurangi penerimaan claim unsupported. Gate tidak boleh diklaim menghilangkan hallucination.

### Prompt injection defense

Raw log selalu dibungkus sebagai data tidak tepercaya dengan delimiter. Instruksi apa pun yang muncul di raw log harus diabaikan sebagai perintah.

### Case isolation

Setiap query, tool, MCP search, event, evidence, finding, ledger, dan audit harus dibatasi oleh `case_id`. Tool harus menolak `case_id` yang berbeda dari active case.

### Immutability

Raw log dan external raw snapshot tidak boleh ditimpa. Transformasi hanya menghasilkan metadata/version/audit baru.

## 6. Status implementasi VIGIL

Fondasi VIGIL sudah diterapkan secara inkremental:

1. `AgentRun.state` memakai schema `vigil-state-v2` dan menyimpan plan eksplisit.
2. Plan memiliki objective, suggested tools, expected evidence, dependency,
   status, serta stop condition.
3. Hypothesis registry, lifecycle, alternative explanation, dan evidence gap
   disimpan di state dan dikembalikan melalui run detail.
4. Observation tool memperbarui evidence ledger, action history, epistemic
   state, dan next action secara bounded.
5. `search_disconfirming_evidence` tersedia sebagai tool read-only case-scoped.
6. Claim verifier mengembalikan reason code terstruktur dan gateway memiliki
   repair loop maksimum dua percobaan.
7. Stop reason disimpan dengan kode operasional seperti `GOAL_SATISFIED`,
   `INSUFFICIENT_EVIDENCE`, `PROVIDER_FAILURE`, dan `VERIFICATION_FAILED`.
8. UI menampilkan goal, plan, hypothesis, gap, verification count, dan stop
   reason tanpa menampilkan chain-of-thought.
9. Model aktif pada audit/report mengikuti provider yang benar-benar dikonfigurasi.

Pekerjaan lanjutan yang belum dianggap selesai: idempotency ingestion lintas
worker, rate-limit per user, migration production yang sepenuhnya formal,
trajectory golden evaluation yang lebih luas, dan backup evidence-inclusive.

## 7. Target agentic yang diinginkan

Target bukan multi-agent. Target adalah:

> Bounded single-agent investigator dengan explicit planning, deterministic tool execution, persistent state, MCP access, evidence ledger, verification-repair loop, human oversight, dan observable trajectory.

Flow target:

```text
Pertanyaan investigator
  -> intent/goal extraction
  -> explicit investigation plan
  -> validate plan against tool policy
  -> execute one tool step
  -> observe structured result
  -> record evidence ledger/checkpoint
  -> decide next step
  -> stop condition or next step
  -> draft claims
  -> claim verification gate
  -> repair with more evidence if needed
  -> final answer or insufficient evidence
```

## 8. Instruksi implementasi

### Tahap A — Explicit plan contract

Tambahkan schema plan minimal:

```json
{
  "goal": "string",
  "scope": {"case_id": "uuid"},
  "steps": [
    {
      "step_id": "string",
      "objective": "string",
      "allowed_tools": ["string"],
      "required_evidence": true,
      "expected_output": "string",
      "stop_condition": "string"
    }
  ],
  "global_stop_conditions": ["string"],
  "plan_version": "string"
}
```

Plan harus divalidasi sebelum dieksekusi. Plan tidak boleh mengandung tool write/action karena MVP hanya read-only investigation. Simpan plan di `AgentRun.state` terlebih dahulu agar tidak langsung membutuhkan migrasi tabel baru.

### Tahap B — Plan-aware execution

Setiap tool call harus dicek:

- tool diizinkan oleh current plan step;
- `case_id` cocok;
- precondition terpenuhi;
- tool tidak dipanggil berulang tanpa progress;
- output memiliki evidence atau alasan tidak ada evidence.

Jika model meminta tool di luar plan, backend harus menolak dan meminta model memilih tool yang diizinkan.

### Tahap C — Evidence-aware observation

Setiap observation harus menyimpan:

```json
{
  "step_id": "string",
  "tool_name": "string",
  "status": "completed|failed|empty",
  "evidence_ids": ["uuid"],
  "result_fingerprint": "sha256",
  "limitations": ["string"]
}
```

Tool yang mengembalikan nol event harus menghasilkan observation `empty`, bukan membuat agent mengarang.

### Tahap D — Verification repair loop

Jika claim gate menolak draft:

1. simpan alasan penolakan secara redacted;
2. agent memilih evidence tambahan yang relevan;
3. agent membuat draft baru;
4. gate memverifikasi ulang;
5. maksimum dua repair attempt;
6. jika tetap gagal, kembalikan insufficient evidence.

### Tahap E — Agent trajectory UI

Tampilkan di frontend:

- status agent;
- goal dan plan step aktif;
- tool yang dipanggil;
- jumlah evidence dikumpulkan;
- limitation;
- retry/repair count;
- stop reason;
- pause/resume/cancel.

Raw log tetap hanya tampil melalui citation/event viewer, bukan dicampur dengan narasi agent.

### Tahap F — Reliability dan rate limit

Implementasikan:

- exponential backoff dengan `Retry-After`;
- pause run ketika provider rate limit;
- resume setelah investigator meminta ulang;
- error provider yang berbeda dari error parser/tool;
- batas default free-tier yang hemat, misalnya 4 rounds dan 8 calls;
- audit model aktif, bukan nama provider legacy;
- idempotency pada analysis rebuild dan correlation insert.

### Tahap G — Evaluation

Buat golden cases untuk:

- brute force lalu successful login;
- web exploitation pattern;
- privilege escalation;
- evidence tidak cukup;
- prompt injection dalam raw log;
- external MCP scoped dan unscoped;
- provider timeout/rate limit;
- duplicate ingestion retry.

Metrik minimum:

- task success rate;
- valid evidence citation precision;
- unsupported claim rate;
- tool selection accuracy;
- average steps to completion;
- tool error rate;
- p95 latency;
- provider retry count;
- rate-limit recovery rate;
- gate off vs gate on.

## 9. Batasan yang tidak boleh dilanggar

Jangan melakukan hal berikut tanpa permintaan eksplisit dan threat model baru:

- mengganti parser deterministik dengan LLM;
- membiarkan LLM mengurutkan raw log;
- menghapus claim verification gate;
- memberi agent akses database langsung;
- mengizinkan arbitrary DSL/SPL;
- menambahkan active response seperti block IP atau disable account;
- mengubah raw evidence;
- mengirim raw log ke provider tanpa policy dan delimiter;
- membuat multi-agent hanya agar terlihat lebih canggih;
- mengklaim forensic-grade atau zero hallucination.

## 10. Definition of Done

Implementasi dianggap berhasil jika:

1. agent menghasilkan plan terstruktur sebelum tool execution;
2. setiap step tervalidasi terhadap plan dan active case;
3. setiap observation memiliki status, limitation, dan evidence ledger;
4. tool failure tidak membuat infinite loop;
5. rate limit dapat dipause dan di-resume;
6. claim unsupported otomatis ditolak atau diperbaiki;
7. UI menampilkan trajectory agent;
8. parser, timeline, correlation, risk, security, MCP, dan claim tests tetap pass;
9. gate off vs gate on dapat dibandingkan secara adil;
10. audit log mencatat prompt version, model version, tool trajectory, dan evidence IDs tanpa raw secret.

## 11. Prompt siap salin-tempel untuk AI developer

> Tingkatkan TraceLens AI menjadi bounded single-agent investigator yang benar-benar evidence-grounded. Pertahankan seluruh parsing, timestamp normalization, ordering, correlation, detection, dan risk scoring sebagai kode deterministik. Tambahkan explicit investigation plan, plan-aware tool policy, durable observation/checkpoint, verification-repair loop, MCP scope enforcement, rate-limit pause/resume, trajectory UI, dan golden trajectory evaluation. Jangan membuat multi-agent, active response, arbitrary query, atau menghapus claim verification gate. Setiap perubahan harus case-scoped, immutable-safe, audited, diuji, dan jujur terhadap insufficient evidence.
