# TraceLens AI — Penjelasan Lengkap Aplikasi

Status dokumen: penjelasan teknis sistem yang berjalan saat ini  
Bahasa: Indonesia  
Audiens: developer, dosen/penguji, reviewer keamanan, dan investigator teknis  
Status produk: production-oriented beta foundation; belum forensic-grade dan belum menjadi pengganti SOC analyst

## 1. Ringkasan satu paragraf

TraceLens AI adalah aplikasi investigasi log keamanan siber berbasis case. Aplikasi menerima file log atau mengambil telemetry eksternal secara read-only, menyimpan sumber bukti secara immutable, menghitung hash SHA-256, mendeteksi format berdasarkan isi, lalu mem-parsing log dengan kode deterministik. Event hasil parsing dinormalisasi ke schema kanonik, diurutkan menjadi timeline, dihubungkan berdasarkan IP/user/session, dianalisis menggunakan rule detection dan risk scoring yang explainable, kemudian dapat ditanyakan melalui AI Investigator. LLM tidak mem-parsing atau mengurutkan log. LLM hanya memilih tool database, merencanakan langkah investigasi, menginterpretasikan hasil, dan menyusun claim. Claim yang tidak mempunyai evidence valid di case aktif akan ditolak oleh backend sebelum jawaban ditampilkan.

Kalimat singkat yang dapat digunakan saat presentasi:

> TraceLens AI adalah bounded single-agent investigation system yang menggabungkan pemrosesan log deterministik, evidence ledger, private MCP read-only, dan claim verification gate agar setiap kesimpulan AI tetap dapat ditelusuri ke bukti.

## 2. Masalah yang ingin diselesaikan

Log keamanan biasanya:

- berasal dari banyak format dan sumber;
- menggunakan timestamp dan timezone yang berbeda;
- berisi data mentah yang sulit dibaca sebagai kronologi;
- membutuhkan korelasi antara IP, user, session, host, atau proses;
- menghasilkan banyak alert yang harus diprioritaskan;
- membuat investigator harus berpindah antara file log, dashboard, dan SIEM;
- berisiko menghasilkan interpretasi AI yang tidak dapat ditelusuri ke bukti.

TraceLens memisahkan dua jenis pekerjaan:

1. **Pekerjaan yang harus objektif dan dapat diulang**, seperti parsing, normalisasi timestamp, sorting, correlation, detection, dan risk score. Pekerjaan ini dilakukan oleh Python, regex, parser JSON/CSV, SQL, dan rule engine.
2. **Pekerjaan yang membutuhkan bahasa dan penalaran**, seperti memilih data yang perlu dicari, menjelaskan konteks, menyusun hipotesis, dan menjawab pertanyaan investigator. Pekerjaan ini dilakukan oleh LLM dengan tool-calling dan dibatasi oleh verifier.

## 3. Tujuan aplikasi

1. Menyediakan workspace investigasi berbasis case.
2. Menjaga file bukti dan raw log agar dapat ditelusuri kembali.
3. Mengubah log heterogen menjadi event kanonik.
4. Membuat timeline lintas file secara deterministik.
5. Menemukan pola keamanan sederhana secara rule-based.
6. Menyediakan risk score beserta breakdown komponen.
7. Memungkinkan AI bertanya ke database melalui tools read-only.
8. Menampilkan claim AI dengan status fact, inference, atau hypothesis.
9. Menolak claim yang tidak memiliki bukti valid.
10. Menyediakan export laporan Markdown atau PDF sederhana.
11. Mencatat operasi penting pada audit log.

## 4. Batasan produk

### 4.1 Format yang didukung

Parser inti yang tersedia:

- Linux auth.log/syslog;
- Nginx/Apache combined access log;
- JSON/JSONL aplikasi generik;
- CSV aplikasi generik dengan header umum;
- logfmt dan generic text sebagai fallback terbatas;
- beberapa varian JSON keamanan yang dapat dipetakan ke field umum.

### 4.2 Di luar scope inti

Fitur berikut tidak boleh dianggap telah tersedia hanya karena inputnya berupa JSON atau teks:

- Windows EVTX native;
- PCAP dan network packet reassembly;
- Docker/Kubernetes runtime log khusus;
- cloud audit yang membutuhkan parser provider khusus;
- threat intelligence eksternal;
- real-time tailing atau streaming ingestion;
- active response, isolasi host, pemblokiran IP, atau eksekusi command;
- malware sandbox;
- entity graph interaktif;
- multi-agent untuk sekadar mengganti label chatbot;
- keputusan otomatis berdampak tinggi tanpa persetujuan manusia.

OpenSearch, Splunk, dan Wazuh yang tersedia di codebase adalah konektor telemetry eksternal read-only. Konektor tersebut bukan active response dan tidak membuat TraceLens menjadi SIEM.

## 5. Prinsip desain yang tidak boleh dilanggar

1. Parsing dan normalisasi tidak boleh memanggil LLM.
2. Sorting timeline dan correlation tidak boleh diserahkan kepada LLM.
3. Raw evidence tidak boleh diubah setelah tersimpan.
4. Semua transformasi penting diberi versi parser, model, prompt, graph, dan risk.
5. Semua query tool harus terikat pada case aktif.
6. LLM tidak boleh menerima database connection atau arbitrary SQL.
7. Raw log yang dikirim ke LLM harus diperlakukan sebagai data tidak tepercaya.
8. Claim wajib memiliki evidence ID yang valid dalam database.
9. Status claim harus fact, inference, atau hypothesis.
10. Jika bukti kurang, jawaban harus menyatakan bukti belum cukup.
11. Investigator manusia tetap menjadi pengambil keputusan akhir.
12. Sistem tidak boleh mengklaim zero hallucination atau forensic-grade formal evidence.

## 6. Arsitektur sistem saat ini

~~~mermaid
flowchart LR
    I[Investigator] --> FE[Next.js Frontend]
    FE -->|REST JSON / multipart| API[FastAPI Backend]
    API --> DB[(PostgreSQL)]
    API --> REDIS[(Redis)]
    API --> VOL[(Immutable Evidence Volume)]
    REDIS --> CEL[Celery Worker]
    CEL --> DB
    CEL --> VOL
    API --> AG[LLM Gateway]
    AG --> LLM[Groq OpenAI-compatible API]
    AG --> TOOLS[Tool Registry]
    TOOLS --> DB
    TOOLS --> MCP[Private MCP Adapter]
    MCP --> SIEM[OpenSearch / Splunk / Wazuh]
    MCP --> EXT[(External Evidence Snapshot)]
    EXT --> DB
    API --> AUDIT[(Audit Logs)]
~~~

### 6.1 Komponen dan tanggung jawab

| Komponen | Teknologi | Tanggung jawab |
|---|---|---|
| Frontend | Next.js 15, React 19, TypeScript | UI login, case, upload, timeline, event explorer, chat, findings, report |
| API | FastAPI, Pydantic | HTTP endpoint, auth, CSRF, case permission, validasi, orchestration |
| ORM | SQLAlchemy | Mapping object ke PostgreSQL dan query case-scoped |
| Database | PostgreSQL 16 | Cases, user, event, evidence, finding, agent run, audit |
| Queue | Redis 7 | Broker Celery dan fixed-window rate limit |
| Worker | Celery | Parsing, penyimpanan event, correlation, finding, integrity check |
| Scheduler | Celery Beat | Menandai job/agent stuck dan verifikasi hash periodik |
| Evidence volume | Docker named volume | File upload yang disimpan dengan nama UUID |
| LLM gateway | Python + httpx | Provider request, tool loop, checkpoint, retry, redaction |
| Model aktif | Groq, openai/gpt-oss-120b | Tool selection, interpretasi, hipotesis, jawaban JSON |
| External adapter | FastMCP + HTTP clients | Search read-only OpenSearch, Splunk, Wazuh |
| Monitoring | Prometheus | Request, latency, findings queue dan metrik operasi |
| Deployment | Docker Compose | Menjalankan frontend, backend, worker, scheduler, PostgreSQL, Redis |

Konfigurasi aktif di file .env saat ini menggunakan:

~~~dotenv
LLM_PROVIDER=groq
LLM_ENDPOINT=https://api.groq.com/openai/v1
LLM_MODEL=openai/gpt-oss-120b
LLM_MAX_TOOL_CALLS=20
NEXT_PUBLIC_API_URL=http://localhost:8002
BACKEND_PORT=8002
FRONTEND_PORT=3001
EXTERNAL_SOURCES_ENABLED=false
MCP_EXTERNAL_IN_PROCESS=true
ALLOW_RAW_LOG_TO_EXTERNAL_PROVIDER=false
~~~

API key tidak ditulis di dokumen ini dan tidak boleh di-commit ke Git.

## 7. Struktur repository

~~~text
TraceLens/
├── backend/
│   ├── app/
│   │   ├── main.py              HTTP API, report, endpoint orchestration
│   │   ├── models.py            SQLAlchemy models dan immutable trigger
│   │   ├── schemas.py           Pydantic request/response
│   │   ├── auth.py              session cookie, CSRF, permission
│   │   ├── security.py          upload validation dan rate limiter
│   │   ├── tasks.py             Celery parsing dan scheduler task
│   │   ├── engine.py            timeline, correlation, detection, risk
│   │   ├── agent_tools.py       tool registry dan MCP bridge
│   │   ├── llm_gateway.py       bounded agent loop
│   │   ├── claim_verifier.py    post-processing claim gate
│   │   ├── external_sources.py  OpenSearch/Splunk/Wazuh adapters
│   │   ├── mcp_server.py        private FastMCP server
│   │   └── parsers/             detector dan parser deterministik
│   ├── alembic/                 migration database
│   ├── tests/                   parser, engine, agent, security, MCP
│   └── evals/                   golden cases dan evaluation harness
├── frontend/
│   ├── app/
│   │   ├── login/
│   │   └── cases/[caseId]/
│   ├── components/
│   └── lib/
├── samples/                     log demo aman
├── monitoring/                  Prometheus dan SLO
├── scripts/                     validation, smoke test, backup, restore
├── docs/                        desain dan dokumentasi
├── docker-compose.yml
└── docker-compose.prod.yml
~~~

## 8. Alur lengkap dari upload sampai finding

~~~mermaid
sequenceDiagram
    actor U as Investigator
    participant FE as Next.js
    participant API as FastAPI
    participant FS as Evidence Volume
    participant DB as PostgreSQL
    participant R as Redis
    participant W as Celery Worker
    U->>FE: Pilih case dan file
    FE->>API: POST /cases/{case_id}/logs
    API->>API: Validasi filename, MIME, ukuran, UTF-8, isi
    API->>API: Streaming SHA-256
    API->>FS: Simpan dengan UUID
    API->>DB: Simpan evidence_files + audit upload
    API->>R: Enqueue evidence_file_id
    API-->>FE: 202 queued
    R->>W: Jalankan parse_evidence_file
    W->>FS: Baca file read-only
    W->>W: Deteksi format dari baris awal
    W->>W: Parse dan normalisasi tiap baris
    W->>DB: Insert event / quarantine
    W->>W: Rebuild timeline, correlation, finding
    W->>DB: Simpan audit parsing dan hasil analysis
    FE->>API: Poll status job
    API-->>FE: parsed / parsed_with_warnings / failed
~~~

### 8.1 Upload

Endpoint upload menerima file multipart dan parsing_mode:

- strict: satu baris malformed menyebabkan parsing file gagal dan tidak menghasilkan event parsial;
- quarantine: baris malformed disimpan ke quarantined_lines, baris valid tetap dapat diproses, dan status file menjadi parsed_with_warnings.

Validasi upload:

- nama file wajib ada;
- path traversal, slash, backslash, null byte, dan nama titik ditolak;
- extension harus termasuk allowlist;
- MIME harus termasuk allowlist;
- isi harus UTF-8;
- ukuran maksimum default 50 MiB;
- deteksi format harus cocok dengan pola isi;
- file disimpan menggunakan UUID, bukan nama pengguna.

SHA-256 dihitung saat streaming upload. File kemudian diberi mode read-only pada filesystem container. Database menyimpan hash, ukuran, path, format terdeteksi, status job, dan progress.

### 8.2 Parsing asynchronous

Celery worker membaca file secara read-only, mendeteksi format, memanggil parser, lalu membuat Event. Worker mempertahankan:

- raw line persis seperti sumber;
- nomor baris asli;
- nama parser;
- confidence parser;
- timestamp asli dan normalisasi;
- asumsi tahun/timezone;
- case ID dan evidence file ID.

Setelah event disimpan, worker mengambil Redis lock per case sebelum rebuild analysis. Lock ini mencegah dua ingestion bersamaan menulis correlation dan finding yang saling menimpa.

## 9. Deteksi format dan parser deterministik

Detector memeriksa maksimal 20 baris non-kosong awal. Skor dihitung dari pola isi:

| Format | Sinyal utama | Parser |
|---|---|---|
| Linux syslog | Regex hostname/process dan timestamp syslog | parse_linux |
| Web access | Regex combined access log | parse_access |
| JSON | json.loads menghasilkan object | parse_json_app |
| CSV | Header umum dan jumlah kolom konsisten | parse_csv_app |
| Logfmt | Pasangan key=value | parse_logfmt |
| Generic text | Fallback UTF-8 dengan confidence rendah | parse_text |

Extension bukan sumber kebenaran utama. File ber-extension .log tetap ditolak jika isi tidak cocok dengan format yang didukung.

### 9.1 Linux authentication/syslog

Fokus parser:

- login SSH gagal;
- login SSH sukses;
- sudo;
- privilege escalation;
- event authentication umum.

Field yang dapat diisi meliputi username, source IP, process, event action, outcome, severity, host, dan session jika tersedia.

### 9.2 Nginx/Apache combined access

Parser mengambil client IP, timestamp, HTTP method, URL path, status HTTP, bytes, referrer, dan user-agent sesuai field yang tersedia. URL path dan raw log tetap disimpan untuk rule web exploitation.

### 9.3 JSON/JSONL aplikasi

Parser fleksibel terhadap key umum seperti:

- timestamp, time, @timestamp, datetime;
- level, severity;
- message, msg;
- user, username;
- ip, source_ip, client_ip;
- event, action, status, host.

Field yang hilang tidak dibuat-buat. Parser memberi nilai None, default aman, atau confidence sesuai informasi yang tersedia.

### 9.4 CSV generik

CSV membutuhkan header dan satu record per baris. Alias header dipetakan ke schema kanonik. Baris dengan jumlah kolom tidak sama dianggap malformed. Multiline quoted CSV belum menjadi target utama.

### 9.5 Timestamp

Timestamp memiliki provenance:

- timestamp_original: nilai asli dari log;
- timestamp_normalized: nilai timezone-aware untuk sorting;
- timezone: timezone yang digunakan;
- timestamp_confidence: confidence normalisasi;
- timestamp_assumptions: daftar asumsi;
- year_source: sumber tahun, misalnya upload year;
- timezone_source: sumber timezone, misalnya server timezone.

Jika syslog tidak menyimpan tahun, sistem memakai tahun waktu upload dan menurunkan confidence. Jika timestamp tidak memiliki timezone, sistem memakai SERVER_TIMEZONE dan menandainya sebagai asumsi.

## 10. Canonical Event

Event adalah unit utama yang dibaca timeline dan AI tools. Field penting:

| Kelompok | Field | Fungsi |
|---|---|---|
| Identity | event_id, case_id | Identitas event dan isolasi case |
| Provenance | evidence_file_id, external_evidence_id, event_origin | Sumber lokal atau eksternal |
| Timestamp | timestamp_original, timestamp_normalized, timezone | Waktu asli dan waktu yang dapat diurutkan |
| Timestamp provenance | timestamp_confidence, timestamp_assumptions, year_source, timezone_source | Menjelaskan kualitas waktu |
| Source | source_type, source_name, host | Asal event |
| Semantics | event_category, event_action, event_outcome, severity | Makna terstruktur |
| Entities | username, source_ip, destination_ip, session_id | Bahan correlation |
| Process/file | process_name, parent_process_name, file_name, command_line, file_hash | Konteks aktivitas |
| Network/web | source_port, destination_port, protocol, http_method, http_status, url_path, user_agent | Analisis web/network |
| Traceability | raw_log, raw_line_number, parser_name, parser_confidence, tags | Bukti dan provenance |

raw_log dan raw_line_number dilindungi oleh database trigger/guard agar tidak ditimpa. Untuk external snapshot, raw_line_number=0 berarti tidak berlaku karena sumber eksternal tidak mempunyai nomor baris file lokal.

Dalam konteks AI, event_id dipakai sebagai evidence_id lokal. External evidence mempunyai UUID lokal sendiri dan harus masuk database sebelum dapat menjadi citation.

## 11. Timeline engine

Timeline dibangun menggunakan event yang sudah berada di database. LLM tidak melakukan sorting.

Urutan deterministik saat ini mempertimbangkan:

1. event dengan timestamp_normalized valid lebih dahulu;
2. timestamp normalized;
3. timestamp confidence lebih tinggi;
4. evidence file atau external evidence ID;
5. raw line number;
6. event ID sebagai stabilizer terakhir.

Dengan demikian, event dari beberapa file dapat digabungkan, sedangkan event dengan waktu sama tetap memiliki urutan stabil. Endpoint timeline juga mengembalikan correlation yang melekat pada event tersebut.

## 12. Correlation engine

Correlation rule-based dibuat untuk:

- source_ip;
- username;
- session_id.

Untuk session, namespace mempertimbangkan host dan source type agar session ID yang sama dari sumber berbeda tidak langsung dianggap sama.

Aturan default:

- window correlation: 10 menit;
- hanya event dengan timestamp valid yang dikorelasikan;
- event diurutkan secara deterministik;
- setiap event dihubungkan ke predecessor terdekat dalam entity yang sama;
- relasi duplikat deduplicated sebelum insert.

Setiap correlation menyimpan:

- entity_type;
- entity_value;
- event_id;
- related_event_id;
- time_delta_seconds;
- correlation_reason.

Contoh reason:

> shared source_ip within 10 minutes (0.5 minutes apart)

Reason tersebut penting karena investigator harus tahu mengapa dua event dianggap berhubungan, bukan hanya melihat angka skor.

## 13. Detection dan findings

Detection berjalan setelah event dan correlation tersedia.

### 13.1 Brute force

Rule mencari beberapa login gagal dari source IP yang sama dalam window tertentu. Threshold default adalah 5 kegagalan dalam 10 menit.

### 13.2 Login sukses setelah kegagalan

Rule mencari login sukses dari IP yang sama setelah rentetan login gagal. Finding menyimpan event kegagalan dan event sukses sebagai evidence.

### 13.3 Rule tambahan

Engine saat ini juga memiliki pola:

- password spraying: satu IP menargetkan beberapa username;
- distributed password guessing: satu username menerima kegagalan dari beberapa IP;
- suspicious PowerShell;
- potential web exploitation;
- persistence/service install;
- privilege escalation.

Rule tambahan ini tetap bersifat indikatif. Rule tidak menyatakan bahwa kompromi benar-benar terjadi. Investigator tetap harus meninjau konteks, false positive consideration, dan evidence tambahan.

### 13.4 MITRE mapping

Finding menyimpan pemetaan teknik/taktik MITRE ATT&CK sebagai konteks analisis, misalnya:

- T1110.001 untuk password guessing;
- T1110.003 untuk password spraying;
- T1078 untuk valid accounts;
- T1059.001 untuk PowerShell;
- T1190 untuk potential exploit;
- T1548 untuk privilege escalation.

Mapping bukan bukti bahwa teknik tersebut pasti dilakukan. Mapping adalah label rule yang memudahkan prioritisasi dan diskusi.

## 14. Risk scoring dan confidence

Risk score dihitung dengan formula explainable:

~~~text
risk_score =
    severity_score    * 0.30
  + frequency_score   * 0.20
  + privilege_score   * 0.25
  + correlation_score * 0.15
  + novelty_score     * 0.10
~~~

Semua komponen dinormalisasi ke 0–1. Correlation memakai count yang dicap pada CORRELATION_CAP=20. Finding menyimpan:

- nilai setiap komponen;
- weight;
- contribution;
- raw correlation count;
- risk level;
- risk_version;
- threshold_version;
- calibration status.

Level default:

- low < 0.40;
- medium 0.40–0.69;
- high 0.70–0.84;
- critical >= 0.85.

Risk score saat ini adalah heuristik explainable dan belum dikalibrasi terhadap dataset berlabel. Karena itu, skor tidak boleh dipresentasikan sebagai probabilitas insiden.

Risk dan confidence berbeda. Confidence finding menggunakan:

~~~text
confidence =
    parser_quality    * 0.40
  + timestamp_quality * 0.20
  + evidence_support  * 0.25
  + source_diversity  * 0.15
~~~

Confidence menjelaskan kualitas dukungan data, bukan peluang bahwa attacker benar-benar ada.

## 15. AI Investigator: mengapa ini agentic

TraceLens bukan sekadar chatbot yang menerima prompt lalu mengeluarkan teks. Agent memiliki:

1. tool selection: model memilih tool yang diperlukan berdasarkan pertanyaan;
2. environment interaction: tool mengambil data terstruktur dari database atau konektor read-only;
3. observation loop: hasil tool dikembalikan sebagai observation/data, lalu model dapat memilih langkah berikutnya;
4. bounded autonomy: jumlah round dan tool call dibatasi;
5. durable state: agent_runs menyimpan state, current step, open questions, hypothesis, collected evidence, dan next action;
6. checkpoint: state disimpan setelah model step dan tool step;
7. control: investigator dapat pause, cancel, atau resume run tertentu;
8. evidence ledger: evidence yang benar-benar dilihat agent dicatat per run;
9. verification gate: draft model tidak langsung ditampilkan;
10. human-in-the-loop: manusia tetap memutuskan apakah finding perlu ditindaklanjuti.

Bentuknya adalah single agent dengan banyak tools, bukan multi-agent. Pembatasan ini disengaja supaya trajectory, sumber keputusan, dan evaluasi tetap mudah diaudit pada MVP.

### 15.1 Alur agent

~~~mermaid
sequenceDiagram
    actor U as Investigator
    participant API as FastAPI
    participant A as LLM Gateway
    participant M as Groq
    participant T as Tool Registry
    participant DB as PostgreSQL
    participant G as Claim Gate
    U->>API: POST /cases/{id}/chat
    API->>A: question + active case
    A->>M: system policy + tool schemas
    M-->>A: tool call
    A->>T: validate name and arguments
    T->>DB: case-scoped deterministic query
    DB-->>T: structured observation
    T-->>A: untrusted data envelope
    A->>M: observation
    M-->>A: more tools or final JSON
    A->>G: draft claims
    G->>DB: verify evidence ownership and semantics
    G-->>API: verified claims only
    API-->>U: answer + claims + run ID
~~~

### 15.2 Tools internal

| Tool | Fungsi | Batasan |
|---|---|---|
| search_events | Mencari event terstruktur | Filter allowlist, maksimal 100 row |
| get_surrounding_events | Mengambil konteks sebelum/sesudah event | Window 1–20 |
| build_timeline | Mengambil timeline deterministik | Tidak boleh sorting manual model |
| correlate_entities | Mengambil relasi IP/user/session | Entity type allowlist |
| get_raw_evidence | Mengambil raw line immutable | Case scoped; raw log dapat ditahan dari provider |
| generate_case_summary | Mengambil finding dan risk summary | Hasil dari database |

### 15.3 Budget dan fail-closed behavior

Konfigurasi agent membatasi:

- maximum tool rounds;
- maximum tool calls;
- pengulangan tool yang sama;
- no-progress limit;
- timeout agent;
- ukuran context tool result;
- output token model.

Gateway juga melakukan:

- retry terbatas untuk 429 dan 5xx;
- context compaction bila payload terlalu besar;
- redaction token/password/private key pada trace;
- fail-closed saat run timeout, tool budget habis, atau provider gagal;
- persist status failed/paused/cancelled agar run tidak tertinggal dalam status running.

Rate limit provider seperti Groq adalah batas eksternal. Jika terlampaui, sistem mengembalikan error yang jujur; restart Docker tidak otomatis menghapus kuota provider.

## 16. Claim Verification Gate

Model harus mengembalikan JSON terstruktur:

~~~json
{
  "answer": "...",
  "claims": [
    {
      "claim_id": "claim-001",
      "text": "Satu kalimat yang dapat diverifikasi.",
      "status": "fact",
      "supporting_evidence_ids": ["UUID"],
      "contradicting_evidence_ids": [],
      "entities": {},
      "confidence": 0.8,
      "reasoning_summary": null,
      "limitations": [],
      "required_additional_evidence": []
    }
  ]
}
~~~

Backend memeriksa:

1. status harus fact, inference, atau hypothesis;
2. evidence ID harus UUID valid;
3. evidence harus ada dalam case aktif;
4. inference minimal memiliki dua evidence ID;
5. inference wajib memiliki reasoning summary dan limitations;
6. hypothesis wajib memiliki limitations dan evidence tambahan yang dibutuhkan;
7. confidence hypothesis tidak boleh lebih dari 0.79;
8. entity yang disebut claim harus konsisten dengan evidence;
9. kata-kata seperti berhasil, gagal, dan login harus didukung oleh field event yang sesuai;
10. angka yang disebut tidak boleh melebihi jumlah evidence yang mendukung;
11. setiap kalimat dipisah dan diverifikasi sebagai unit tersendiri.

Jika tidak ada claim yang lolos:

> Belum cukup bukti untuk menjawab pertanyaan ini.

Gate ini tidak menghilangkan hallucination secara matematis. Gate dirancang untuk mengurangi penerimaan claim yang tidak memiliki evidence, status, atau semantic support yang sesuai.

## 17. Fact, inference, dan hypothesis

| Status | Arti | Syarat praktis |
|---|---|---|
| Fact | Pernyataan langsung dari event atau finding | Minimal satu evidence langsung |
| Inference | Kesimpulan yang ditarik dari beberapa fakta | Minimal dua evidence, alasan, limitation |
| Hypothesis | Dugaan yang masih perlu dibuktikan | Evidence, confidence terbatas, limitation, additional evidence |

Contoh:

- Fact: “IP 10.0.0.5 menghasilkan login gagal.” Ini dapat ditunjukkan langsung oleh event.
- Inference: “Rentetan login gagal tersebut berkorelasi dengan login sukses berikutnya.” Ini perlu beberapa event dan reason waktu/IP.
- Hypothesis: “Aktivitas tersebut mungkin merupakan password guessing yang berhasil.” Ini belum boleh disebut fakta tanpa bukti tambahan.

## 18. Prompt-injection defense

Raw log diperlakukan sebagai konten tidak tepercaya. Gateway:

- membungkus hasil tool dengan delimiter acak;
- menambahkan security notice bahwa payload hanya DATA;
- memberi sinyal bila teks terlihat seperti prompt injection;
- memotong result terlalu besar;
- melakukan redaction terhadap token dan secret;
- menolak tool yang tidak ada di allowlist;
- mengikat query ke case aktif;
- memverifikasi claim setelah model selesai.

Contoh isi log “ignore previous instructions” tidak boleh mengubah system policy. Deteksi pattern adalah sinyal tambahan, bukan satu-satunya pertahanan.

Jika ALLOW_RAW_LOG_TO_EXTERNAL_PROVIDER=false, tool get_raw_evidence menahan raw log asli dari provider LLM. Investigator tetap dapat membuka evidence dari UI melalui endpoint backend.

## 19. MCP dan external telemetry

TraceLens memiliki private MCP server bernama tracelens-external-evidence. Implementasinya dapat dijalankan melalui stdio atau streamable HTTP, dan default saat ini memakai bridge in-process dari agent tool.

Tool MCP:

- list_external_sources;
- search_external_events_mcp;
- get_external_evidence_mcp.

Provider yang didukung:

- OpenSearch;
- Splunk;
- Wazuh Indexer.

MCP tidak menerima arbitrary OpenSearch DSL atau arbitrary SPL dari model. Backend membangun query terbatas berdasarkan filter yang diizinkan dan selalu memasukkan scope case, misalnya field tracelens.case_id.

Alur external evidence:

1. agent mengecek status source;
2. agent memilih provider yang tersedia;
3. adapter melakukan search read-only;
4. setiap hit diberi content hash dan query hash;
5. hit disimpan sebagai immutable external_evidence;
6. hit diproyeksikan menjadi canonical Event;
7. timeline, correlation, dan detection deterministic dapat dibangun ulang;
8. citation memakai UUID evidence lokal, bukan ID attacker-controlled dari SIEM.

Jika EXTERNAL_SOURCES_ENABLED=false, agent menggunakan event lokal dari upload. Jika provider gagal, sistem tidak boleh mengarang hasil eksternal.

## 20. Model database

### 20.1 Case dan access control

- cases: identitas investigasi, nama, deskripsi, waktu dibuat.
- users: username, password hash PBKDF2, global role, status aktif.
- user_sessions: session token hash, CSRF hash, expiry.
- case_memberships: hubungan user-case dan role.

Role case:

- viewer: read;
- investigator: read, upload, chat, export;
- reviewer: read, export;
- admin: akses global yang diizinkan.

### 20.2 Bukti dan provenance

- evidence_files: file upload, hash, ukuran, status parsing, job, progress, completeness, integrity status.
- quarantined_lines: raw line malformed pada mode quarantine.
- external_evidence: snapshot immutable dari OpenSearch/Splunk/Wazuh.

### 20.3 Analysis

- events: canonical event.
- correlations: hubungan dua event dan alasan.
- findings: detection, evidence IDs, risk breakdown, confidence, MITRE, false positives, workflow status.

### 20.4 Agent observability

- agent_runs: pertanyaan, status, state JSON, checkpoint, model/prompt/graph version.
- agent_steps: trace redacted per model/tool step, latency, status, evidence IDs.
- evidence_ledgers: evidence yang benar-benar diamati agent per run.

### 20.5 Audit

audit_logs mencatat operasi seperti:

- login/logout;
- case creation;
- upload diterima/ditolak;
- parsing selesai/gagal/retry/stuck;
- evidence integrity check;
- external evidence search;
- agent answer dan evidence ID;
- report export;
- finding workflow update.

## 21. API yang tersedia

### 21.1 System dan auth

| Method | Endpoint | Fungsi |
|---|---|---|
| GET | /health | Liveness |
| GET | /ready | Database dan versi parser/risk |
| GET | /metrics | Prometheus metrics |
| POST | /auth/login | Membuat session dan CSRF cookie |
| POST | /auth/logout | Menghapus session |
| GET | /auth/me | User aktif |
| GET | /external-sources/status | Status provider tanpa secret |

### 21.2 Case dan evidence

| Method | Endpoint | Fungsi |
|---|---|---|
| POST | /cases | Membuat case |
| POST | /cases/{case_id}/logs | Upload dan enqueue parsing |
| GET | /cases/{case_id}/logs | Daftar file evidence |
| GET | /cases/{case_id}/logs/{evidence_file_id} | Status file |
| GET | /cases/{case_id}/jobs/{job_id} | Status parsing job |
| POST | /cases/{case_id}/jobs/{job_id}/retry | Retry job failed/stuck |
| POST | /cases/{case_id}/logs/{evidence_file_id}/verify | Verifikasi SHA-256 |

### 21.3 Analysis

| Method | Endpoint | Fungsi |
|---|---|---|
| GET | /cases/{case_id}/events | Pagination dan filter event |
| GET | /cases/{case_id}/events/{event_id} | Event dan context before/after |
| GET | /cases/{case_id}/timeline | Timeline dengan correlation |
| GET | /cases/{case_id}/entities | Ringkasan IP/user/session |
| GET | /cases/{case_id}/findings | Finding dan risk breakdown |
| PATCH | /cases/{case_id}/findings/{finding_id} | Workflow finding |
| POST | /cases/{case_id}/analysis/rebuild | Rebuild deterministic analysis |

### 21.4 Agent dan report

| Method | Endpoint | Fungsi |
|---|---|---|
| POST | /cases/{case_id}/chat | Pertanyaan investigator |
| GET | /cases/{case_id}/agent-runs | Daftar run |
| GET | /cases/{case_id}/agent-runs/{run_id} | Run, steps, ledger |
| POST | /cases/{case_id}/agent-runs/{run_id}/pause | Pause |
| POST | /cases/{case_id}/agent-runs/{run_id}/cancel | Cancel |
| POST | /cases/{case_id}/agent-runs/{run_id}/resume | Resume checkpoint |
| POST | /cases/{case_id}/exports | Markdown/PDF dan audit export |

Semua endpoint case-scoped memeriksa membership sebelum query data. case_id dari URL tidak boleh diganti oleh case_id yang diminta model di dalam tool.

## 22. Frontend dan pengalaman investigator

Frontend berada di frontend/ dan menggunakan Next.js App Router.

Halaman per case:

1. **Command Center** — ringkasan case, jumlah event, finding, risk, host/user/IP.
2. **Evidence Intake** — upload drag-and-drop, progress, format, status parsing, strict/quarantine.
3. **Attack Timeline** — event terurut dan correlation reason.
4. **Event Explorer** — search/filter, raw log, context before/after.
5. **AI Investigator** — pertanyaan, narasi terverifikasi, claim badge, citation clickable, limitation, required evidence, durable agent trace.
6. **Findings / Reports** — risk breakdown, false positive considerations, workflow update, export.

Citation pada chat dapat diklik untuk mengambil event atau external evidence dari backend. Evidence block sengaja dipisahkan dari narasi AI supaya investigator tidak mencampur fakta sumber dengan interpretasi.

## 23. Report dan chain-of-custody

Export tersedia dalam:

- Markdown;
- PDF sederhana;
- formal PDF layout yang menyertakan ringkasan case, timeline, findings, risk, dan evidence references.

Report bukan pengganti bukti legal formal. Sistem belum menyediakan digital signature, WORM storage, trusted timestamping, atau prosedur forensik formal. Hash SHA-256 dan audit log adalah kontrol chain-of-custody level aplikasi untuk MVP.

## 24. Keamanan yang sudah diterapkan

| Risiko | Kontrol |
|---|---|
| Path traversal | Filename normalization dan UUID storage path |
| File terlalu besar | Streaming size limit |
| File bukan log | MIME, extension, UTF-8, content detector |
| Session dicuri | HttpOnly session cookie, expiry, CSRF token |
| Unauthorized case access | Membership role dan case-scoped query |
| Query model berbahaya | Tool allowlist dan filter allowlist |
| Prompt injection | Untrusted data envelope dan claim gate |
| Raw evidence berubah | DB immutability trigger/guard dan file read-only |
| Chat/upload abuse | Redis fixed-window rate limit per IP |
| Secret masuk trace | Redaction regex dan withholding raw log |
| External provider outage | Timeout, retry terbatas, circuit breaker |

Keterbatasan keamanan:

- rate limit default per IP, bukan per user;
- deployment lokal default belum memakai secure cookie/TLS;
- .env tetap harus dijaga oleh operator;
- belum ada malware scanning/sandbox;
- audit log belum tamper-evident di luar database;
- belum ada multi-tenant isolation penuh;
- prompt injection tidak mungkin dianggap selesai hanya dengan delimiter.

## 25. Menjalankan aplikasi

Prasyarat:

- Docker Desktop dan Docker Compose;
- file .env;
- token provider LLM yang valid jika ingin memakai chat;
- minimal memory Docker yang memadai.

PowerShell:

~~~powershell
cd D:\SEM-6\AI\loginvestigator-x
Copy-Item .env.example .env
# edit .env dan isi LLM_API_KEY serta password lokal
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8002/health
Invoke-RestMethod http://localhost:8002/ready
~~~

URL:

- frontend: http://localhost:3001;
- API: http://localhost:8002;
- Swagger: http://localhost:8002/docs;
- health: http://localhost:8002/health;
- readiness: http://localhost:8002/ready.

Log service:

~~~powershell
docker compose logs -f backend worker frontend
~~~

Stop tanpa menghapus data:

~~~powershell
docker compose down
~~~

Jangan menggunakan docker compose down -v kecuali database dan evidence volume memang ingin dihapus permanen.

## 26. Cara menggunakan alur demo

1. Login menggunakan BOOTSTRAP_ADMIN_USERNAME dan BOOTSTRAP_ADMIN_PASSWORD.
2. Buat case.
3. Buka Evidence Intake.
4. Upload salah satu sample di samples/.
5. Tunggu status berubah menjadi parsed atau parsed_with_warnings.
6. Buka Command Center untuk melihat ringkasan.
7. Buka Attack Timeline untuk melihat urutan event dan correlation.
8. Buka Findings / Reports untuk melihat risk breakdown.
9. Tanyakan AI, misalnya:

~~~text
Apa rangkaian kejadian penting pada case ini?
IP mana yang menghasilkan kegagalan authentication berulang?
Apakah ada login sukses setelah rentetan kegagalan?
Evidence apa yang masih diperlukan untuk menguatkan hypothesis?
~~~

10. Klik setiap citation dan cocokkan raw log.
11. Export Markdown atau PDF setelah investigator meninjau hasil.

## 27. Testing dan evaluasi

Parser test mencakup:

- event valid;
- optional field hilang;
- malformed line;
- content-based format detection;
- timestamp tanpa tahun/timezone;
- file besar dan deterministic parsing.

Engine test mencakup:

- timeline lintas file;
- tie-break ordering;
- correlation reason;
- correlation deduplication;
- brute force sampai login sukses;
- password spray dan distributed guessing;
- signature finding.

Security test mencakup:

- path traversal;
- MIME/extension berbahaya;
- oversized upload;
- rate limit;
- cross-case event/evidence access;
- membership authorization;
- report audit.

Agent test mencakup:

- setiap sentence jawaban memiliki evidence ID valid;
- claim gate menolak evidence invalid;
- fact/inference/hypothesis memenuhi syarat;
- prompt injection dari raw log tidak diikuti;
- insufficient evidence menghasilkan jawaban jujur;
- context compaction;
- audit evidence IDs;
- checkpoint dan resume;
- provider failure tidak membocorkan exception internal.

Perintah:

~~~powershell
docker compose exec backend pytest
docker compose exec frontend npm run typecheck
docker compose exec frontend npm run build
~~~

Evaluation offline:

~~~powershell
docker compose exec backend python evals/run_eval.py
docker compose exec backend python evals/run_detection_eval.py
~~~

Metrik yang perlu dibedakan:

- parser correctness;
- detection precision/recall/F1;
- timeline ordering correctness;
- correlation correctness;
- risk explanation completeness;
- claim evidence validity;
- insufficient-evidence honesty;
- agent tool trajectory;
- latency dan provider failure rate.

## 28. Di mana letak agentic-nya?

| Chatbot biasa | TraceLens |
|---|---|
| Menjawab dari prompt dan context statis | Memilih tool berdasarkan kebutuhan investigasi |
| Tidak punya state durable | Memiliki agent_runs, checkpoints, steps, dan ledger |
| Dapat mengarang citation | Backend memverifikasi citation ke database |
| Tidak mengetahui batas data | Tool terikat pada case aktif |
| Satu respons teks | Loop model → tool → observation → tool/final |
| Tidak ada kontrol | Investigator dapat pause, cancel, resume |
| Raw log dianggap context biasa | Raw log diperlakukan sebagai untrusted data |
| Umumnya tidak dapat diaudit | Tool trajectory, model, prompt, evidence, dan audit dicatat |

TraceLens tetap bounded. Agent tidak boleh menjalankan command, mengubah firewall, menghapus event, atau memutuskan containment secara otomatis.

## 29. Status VIGIL dan pekerjaan lanjutan

Fondasi agentic VIGIL kini berjalan di atas single-agent yang sama. `AgentRun.state`
menyimpan plan eksplisit versi `vigil-state-v2`, hypothesis registry, epistemic
state, evidence gap, case-bounded memory, provenance edges, repair state, dan
structured stop state. Tool observation memperbarui state serta evidence ledger;
`search_disconfirming_evidence` membantu mencari konteks benign atau kontradiktif.
Verifier mengembalikan reason code dan gateway dapat melakukan maksimal dua
repair attempt sebelum fail-closed. UI menampilkan goal, plan, hypothesis,
evidence gap, verification count, dan stop reason tanpa chain-of-thought.

Pekerjaan lanjutan yang belum selesai:

1. Idempotency ingestion lintas worker dan incremental analysis.
2. Migration production formal menggantikan startup DDL tambahan.
3. Rate limiting per user, secret manager, TLS, secure headers, dan backup
   evidence-inclusive.
4. Golden evaluation trajectory yang lebih luas, termasuk tool efficiency,
   contradiction discovery, repair success, dan stop decision accuracy.
5. Kalibrasi risk weight terhadap corpus berlabel serta audit tamper-evident.

Pekerjaan tersebut tidak boleh mengubah prinsip bahwa LLM bukan parser dan bukan
pengambil keputusan insiden terakhir.

## 30. Batas klaim saat presentasi

Gunakan klaim berikut:

- “Sistem membantu investigator mengubah log menjadi timeline dan finding yang dapat ditelusuri.”
- “Pemrosesan dasar dilakukan deterministik sehingga dapat diuji ulang.”
- “AI memakai tools read-only dan claim gate memeriksa evidence ID.”
- “MCP digunakan sebagai adapter telemetry eksternal read-only.”
- “Risk score explainable, tetapi belum dikalibrasi sebagai probabilitas.”
- “Human-in-the-loop tetap wajib.”

Hindari klaim berikut:

- “Sistem menghilangkan hallucination.”
- “Sistem otomatis menemukan attacker.”
- “Sistem menggantikan SOC analyst.”
- “Sistem sudah forensic-grade.”
- “Risk score adalah peluang serangan.”
- “MCP dapat melakukan active response.”
- “Semua format log sudah didukung.”

## 31. Script penjelasan untuk audiensi teknis

### Versi 30 detik

TraceLens AI menerima log, menyimpan hash dan raw evidence, mem-parsingnya secara deterministik, lalu membangun event kanonik, timeline, correlation, finding, dan risk breakdown. AI tidak memproses log mentah secara bebas; AI hanya menggunakan tools read-only untuk mencari data di case aktif. Jawaban AI dikembalikan sebagai fact, inference, atau hypothesis, kemudian backend memverifikasi setiap evidence ID sebelum menampilkannya.

### Versi 3 menit

Pertama, investigator membuat case dan upload log. Backend memvalidasi file, menghitung SHA-256, menyimpan file dengan UUID, dan mengantrekan parsing ke Celery. Worker mendeteksi format dari isi file dan memanggil parser Python. Setiap event menyimpan raw log dan nomor baris asli. Setelah parsing, engine mengurutkan event, membuat correlation berdasarkan IP/user/session, menjalankan detection rule, dan menghitung risk score explainable.

Kedua, investigator dapat membuka timeline, event explorer, finding, dan report. Ketiga, ketika investigator bertanya ke AI, gateway membuat agent run. Model memilih tool seperti search event, surrounding event, timeline, correlation, raw evidence, atau summary. Tool mengembalikan data terstruktur dari database. Data tersebut dibungkus sebagai untrusted data dan tidak dapat mengubah system policy. Setelah model menghasilkan draft claim, claim gate memeriksa UUID evidence, ownership case, status claim, semantic support, dan syarat inference/hypothesis. Hanya claim yang lolos yang ditampilkan.

Jika telemetry eksternal diaktifkan, agent dapat mencari OpenSearch, Splunk, atau Wazuh melalui MCP read-only. Hasil pencarian di-snapshot ke database lokal dan diberi evidence UUID sebelum dapat dikutip. Manusia tetap memutuskan apakah finding valid dan tindakan apa yang perlu dilakukan.

## 32. Brief untuk AI developer yang akan melanjutkan sistem

AI developer yang melanjutkan repository harus membaca dokumen ini dan AGENTIC_UPGRADE_BRIEF.md. Instruksi teknis utamanya:

1. Inspect code dan tests sebelum mengubah perilaku.
2. Jangan memindahkan parsing, sorting, correlation, atau detection ke LLM.
3. Pertahankan single-agent bounded architecture.
4. Tambahkan explicit plan, bukan multi-agent kosmetik.
5. Persist plan dan next action di AgentRun.state.
6. Setiap tool tetap read-only, case-scoped, bounded, dan observable.
7. Claim repair hanya boleh terbatas dan tetap melewati verifier.
8. Jangan menampilkan raw evidence provider jika data policy melarangnya.
9. Tambahkan regression test untuk evidence gate, prompt injection, cross-case access, dan insufficient evidence.
10. Perbarui version dan audit bila parser, prompt, model, graph, atau risk formula berubah.
11. Jangan menambahkan active response atau fitur di luar scope tanpa persetujuan eksplisit.
12. Laporan akhir wajib menjelaskan apa yang benar-benar diuji dan apa yang belum.

## 33. Kesimpulan

TraceLens AI sudah memiliki fondasi kuat untuk MVP investigasi log: ingestion asynchronous, canonical event, deterministic analysis, explainable finding, authenticated case workspace, evidence citation, agent state, private MCP, dan claim verification gate. Keunggulan utamanya bukan bahwa AI dapat melakukan semua hal sendiri, melainkan bahwa AI ditempatkan di atas data yang sudah diproses secara terkontrol dan setiap outputnya dipaksa melewati pemeriksaan evidence.

Arah pengembangan yang benar adalah menjadikan agent lebih terencana, dapat diaudit, dapat dilanjutkan, dan lebih efisien memilih tools—bukan membiarkan LLM mengambil alih parser, database, atau keputusan respons insiden.

Dokumen terkait:

- [Brief upgrade agentic](AGENTIC_UPGRADE_BRIEF.md)
- [Arsitektur ringkas](ARCHITECTURE.md)
- [Threat model](THREAT_MODEL.md)
- [Panduan menambah parser](ADDING_A_PARSER.md)
- [External MCP integration](EXTERNAL_MCP_INTEGRATION_ID.md)
- [README project](../README.md)
