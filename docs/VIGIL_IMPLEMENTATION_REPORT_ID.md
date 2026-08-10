# Laporan Implementasi TraceLens AI / VIGIL

Status: hasil audit dan hardening implementasi saat ini  
Tanggal: 10 Agustus 2026  
Status produk: production-oriented beta foundation untuk riset, demo, dan staging terbatas. Belum forensic-grade dan bukan pengganti SOC analyst.

Dokumen ini merangkum implementasi VIGIL berdasarkan source code, migration,
test, evaluation harness, frontend, dan dokumentasi repository. Klaim hasil
dibedakan antara pemeriksaan lokal yang benar-benar dijalankan dan pekerjaan
yang masih memerlukan environment atau studi lanjutan.

## A. Penilaian arsitektur

TraceLens mempertahankan pemisahan deterministic analysis plane dan agent
reasoning plane:

~~~text
Investigator
  -> Next.js UI
  -> FastAPI case boundary
  -> evidence intake + SHA-256 + immutable storage
  -> Celery parser worker
  -> canonical events
  -> deterministic timeline/correlation/detection/risk
  -> VIGIL bounded single-agent supervisor
       -> explicit plan
       -> allowlisted read-only tools / private MCP
       -> untrusted observation envelope
       -> hypothesis + evidence gap + disconfirming search
       -> structured claims
       -> Claim Verification Gate
       -> repair terbatas atau fail-closed stop
  -> human review dan evidence-referenced report
~~~

LLM tidak mengambil alih parser, normalisasi timestamp, sorting timeline,
correlation, detection, atau risk scoring. Agent mengatur investigasi pertanyaan
terbuka, memilih konteks, memperbarui rencana secara terbatas, menyusun
hipotesis, dan menjelaskan hasil yang melewati verifier.

Klasifikasi autonomy yang digunakan adalah Level 3 bounded adaptive
single-agent. Tools yang tersedia read-only. Tidak ada command execution,
perubahan firewall, isolasi host, disable account, atau active response otomatis.

## B. File dan komponen relevan

### Core backend dan agent

- backend/app/vigil.py — state vigil-state-v2, plan, hypothesis, evidence gap,
  next action, memory, provenance, disconfirming evidence, dan stop state.
- backend/app/llm_gateway.py — bounded model-tool-observation loop, checkpoint,
  compaction, retry, repair maksimal dua kali, fail-closed, redaction.
- backend/app/agent_tools.py — registry tools read-only, case-scoped, bounded.
- backend/app/claim_verifier.py — validasi evidence ownership, semantic support,
  status epistemik, reason code, dan fallback insufficient evidence.
- backend/app/engine.py — timeline, correlation, detection, explainable risk.
- backend/app/tasks.py — ingestion asynchronous, lock per case, watchdog,
  dan integrity task.
- backend/app/external_sources.py — adapter OpenSearch, Splunk, Wazuh read-only
  dengan snapshot evidence lokal.
- backend/app/mcp_server.py — private MCP adapter telemetry eksternal.
- backend/app/main.py — API, chat orchestration, run detail, export, dan laporan
  dengan hypothesis evidence links serta verification rejection reasons.

### Data, migration, frontend, evaluasi

- backend/app/models.py dan backend/app/schemas.py — model database dan kontrak state.
- backend/alembic/versions/0004_external_evidence.py — external evidence.
- backend/alembic/versions/0005_agent_runs_and_canonical_external_events.py —
  durable agent run/step/ledger dan canonical event eksternal.
- backend/alembic/versions/0006_production_hardening.py — production hardening.
- frontend/app/cases/[caseId]/chat/page.tsx — UI chat, plan, hypothesis, gap,
  next action, stop, verification, dan detail step.
- backend/tests/test_vigil.py, test_agent.py, test_external_sources.py —
  regression state, security, checkpoint, dan external scope.
- backend/evals/run_vigil_eval.py dan run_detection_eval.py — golden evaluation
  internal.

Perubahan final pada siklus ini menutup dua gap traceability: detail tool-step
di UI dan evidence/rejection detail pada export Markdown. Core policy, parser,
canonical event, dan deterministic analysis tidak diubah.

## C. Kapabilitas VIGIL

### Planner

Planner membuat goal investigasi dan plan eksplisit dengan objective, allowed
tool, expected evidence, status step, dan stop condition. Plan memiliki
version/schema, menggunakan tool allowlist, dan revisinya dibatasi serta
dicatat sebagai state transition.

### Hypothesis Registry

Hypothesis durable memiliki identifier, statement, status, confidence,
supporting evidence, contradicting evidence, limitation, alternative
explanation, dan required evidence. Lifecycle: proposed, investigating,
supported, weakened, refuted, unresolved. Hypothesis bukan finding forensik;
statusnya tetap memerlukan human review.

### Evidence Gap Analyzer dan Next Action

Analyzer membandingkan goal/hypothesis dengan evidence yang telah dikumpulkan.
Gap diberi jenis/prioritas dan menjadi dasar next action. State menyimpan action
terstruktur yang dibatasi policy, misalnya menjalankan plan step, mengambil
konteks event, atau mencari evidence yang melemahkan hypothesis. UI menampilkan
action dan reason code tanpa chain-of-thought.

### Contradiction Search

Tool search_disconfirming_evidence mencari event benign, maintenance,
kontradiksi outcome, atau konteks alternatif dalam case scope. Hasilnya masuk
evidence ledger/provenance dan dapat memperbarui hypothesis menjadi weakened
atau refuted. Ini mitigasi false-positive, bukan jaminan seluruh alternatif
ditemukan.

### Verifier Repair

Verifier memeriksa UUID evidence, case ownership, status fact/inference/
hypothesis, jumlah evidence, semantic support, entity consistency, limitation,
dan confidence hypothesis. Gateway boleh melakukan repair maksimal dua kali.
Claim yang tetap gagal tidak ditampilkan sebagai claim terverifikasi. Gate
mengurangi penerimaan claim unsupported; gate tidak menghilangkan hallucination
secara matematis.

### Stop Policy, Provenance, dan Case Memory

Stop reason terstruktur meliputi GOAL_SATISFIED, INSUFFICIENT_EVIDENCE,
VERIFICATION_FAILED, PROVIDER_FAILURE, BUDGET_EXHAUSTED, TIMEOUT, CANCELLED,
dan PAUSED.

Provenance menghubungkan agent step, evidence ledger, canonical event,
correlation, finding, external snapshot, hash, dan source identifier lokal.
Citation memakai UUID evidence lokal; ini bukan chain-of-custody legal formal.

Memory dibatasi pada case aktif. State dari case lain tidak dipakai, evidence
memory tidak menjadi global, dan informasi yang disimpan memiliki provenance.
Defense-in-depth authorization tetap diperlukan di deployment produksi.

## D. Migration dan persistensi

Agent state, plan, steps, ledger, external evidence, dan canonical external
event disimpan durable, bukan hanya di RAM. Alembic revision 0004, 0005, dan
0006 menyediakan schema untuk resume, audit, export, dan replay.

Readiness perlu memeriksa database, Redis, evidence storage, dan schema revision.
Validasi penuh terhadap container tidak dapat dijalankan pada environment saat
laporan ini dibuat karena Docker Desktop tidak tersedia.

Tidak ada migration baru yang diperlukan untuk perubahan UI trace dan format
export; keduanya memakai state/verification JSON yang sudah ada.

## E. API dan kontrak runtime

Kontrak yang dipertahankan:

- POST /cases/{case_id}/chat untuk bounded agent run.
- GET /cases/{case_id}/agent-runs untuk daftar run.
- GET /cases/{case_id}/agent-runs/{run_id} untuk state, steps, ledger,
  verification, dan stop state.
- POST pause, cancel, dan resume untuk durable control.
- Endpoint event/timeline/finding sebagai deterministic substrate.
- Endpoint export Markdown/PDF dengan evidence references.

Tidak ada endpoint write ke firewall, endpoint/host, akun, atau SIEM. Semua
tool agent/MCP case-scoped, allowlisted, bounded, dan read-only.

## F. Perubahan UI dan laporan

Halaman AI Investigator sekarang menampilkan trace operasional tanpa
chain-of-thought:

- run ID, status, jumlah step, tipe/nama step;
- status, latency, evidence count, reason code, plan step ID, error code;
- goal dan plan aktif;
- hypothesis status;
- supporting/contradicting evidence IDs;
- missing evidence dan alternative explanation;
- evidence gap, next action, verification count, rejection reason;
- stop reason dan stop detail.

Export Markdown sekarang memuat plan, hypothesis registry, supporting,
contradicting, missing evidence, alternative explanations, verification count,
repair attempts, rejection reasons, dan evidence references.

## G. Jaminan keamanan yang dapat diklaim

1. Upload divalidasi melalui filename, extension/MIME, UTF-8, ukuran, dan
   content detector.
2. File disimpan dengan UUID dan SHA-256; raw evidence diberi guard immutable
   serta mode read-only pada volume.
3. Query dan citation dibatasi case aktif serta membership.
4. Agent tidak menerima database connection atau arbitrary SQL/DSL/SPL.
5. Tool eksternal read-only dan hasilnya disnapshot sebagai evidence lokal.
6. Raw tool output dibungkus sebagai untrusted data; prompt injection pada log
   tidak boleh mengubah system policy.
7. Session/CSRF, rate limit, security headers, request ID, retry budget, dan
   fail-closed behavior tersedia.
8. Provider failure, timeout, budget exhaustion, dan verification failure
   menghasilkan status jujur, bukan fabricated result.
9. Human-in-the-loop tetap mengambil keputusan eskalasi dan tindakan.

Batas penting: tidak ada jaminan zero hallucination; log bisa tidak lengkap;
audit database belum tamper-evident external; belum ada MFA/SSO, secret manager,
full tenant isolation, malware sandbox, WORM/object storage multi-AZ, atau
formal digital signature; tidak ada active response; risk score bukan
probabilitas serangan.

## H. Test dan evaluation

Perintah lokal yang dijalankan:

~~~powershell
cd backend
pytest -q
python evals/run_vigil_eval.py
python evals/run_detection_eval.py

cd ..\frontend
npm run typecheck
npm run build
~~~

Hasil:

- pytest -q: 77 passed.
- VIGIL offline evaluation: 6/6 passed, pass rate 1.0.
- Detection golden evaluation: 6/6 passed, precision 1.0, recall 1.0, F1 1.0
  pada corpus internal kecil.
- Frontend TypeScript typecheck: lulus.
- Frontend production build: berhasil.

Hasil tersebut adalah regression/golden test internal, bukan validasi
generalisasi atau bukti keunggulan dibanding human analyst, SOAR, atau copilot.

Validasi Docker pada siklus ini belum dijalankan karena Docker Desktop tidak
tersedia (engine named pipe tidak ditemukan). Karena itu tidak ada klaim baru
dari siklus ini tentang health, ready, Celery, PostgreSQL, Redis, migration
runtime, atau E2E container. Pemeriksaan Docker historis harus diulang pada
environment target.

## I. Limitasi tersisa

1. Belum ada gate-off versus gate-on study dengan model, prompt, budget, corpus,
   dan reviewer manusia yang sama.
2. Corpus VIGIL/detection kecil dan internal; belum ada corpus SOC eksternal
   berlabel dengan kasus benign, timestamp ambigu, konflik evidence, dan
   provider nyata.
3. Belum ada independent red-team untuk prompt injection, cross-case IDOR,
   provider poisoning, secret leakage, dan malicious upload.
4. Belum ada load/soak/concurrency benchmark atau idempotency proof pada skala
   SOC.
5. Backup/restore evidence-inclusive, RPO/RTO, failover, dan HA belum signed
   off pada staging.
6. Audit belum dipindahkan ke external append-only atau hash-chained sink.
7. Secure cookie/TLS, secret manager, MFA/SSO, WAF, RLS defense-in-depth, dan
   full tenant isolation masih menjadi deployment hardening.
8. Parser tetap terbatas pada format yang didukung; EVTX, PCAP, provider cloud
   khusus, dan streaming realtime berada di luar scope.
9. Repair loop memeriksa struktur dan evidence support, bukan independent
   semantic proof.
10. Sistem masih bounded single-agent Level 3 dan belum melakukan autonomous
    response.

## J. Skenario demo reproducible

Gunakan fixture lokal agar demo tidak bergantung pada provider rate limit atau
SIEM publik. Fixture berisi failed login berulang, successful login sesudahnya,
event maintenance benign, raw line dengan prompt injection, dan evidence yang
sengaja hilang.

Alur:

1. Investigator membuat case dan upload fixture.
2. Parser membuat canonical event, timeline, correlation, dan finding.
3. Investigator bertanya: Investigasi rangkaian login ini. Apakah ada indikasi
   password guessing yang berhasil, bukti apa yang mendukung, konteks benign
   apa yang membantahnya, dan evidence apa yang masih diperlukan?
4. Agent membuat goal dan plan.
5. Agent memanggil timeline, search event, correlation, dan surrounding event.
6. Agent membuat hypothesis dan mencatat supporting evidence.
7. Agent menjalankan search_disconfirming_evidence dan menemukan maintenance.
8. Hypothesis berubah menjadi weakened atau unresolved; alternative explanation
   dan evidence gap ditambahkan.
9. Model membuat claim fact/inference/hypothesis.
10. Claim Verification Gate menerima claim dengan semantic support dan menolak
    claim yang terlalu kuat atau memakai evidence UUID salah.
11. UI menampilkan plan, tool step, evidence IDs, contradiction, verification,
    repair/stop reason, dan limitation.
12. Investigator membuka citation dan mengekspor report setelah human review.

Kesimpulan demo yang aman:

> Agent tidak menemukan attacker secara otomatis. Agent menunjukkan proses
> investigasi yang dapat direplay: memilih tools read-only, memperbarui
> hypothesis setelah evidence kontradiktif, menolak claim unsupported, dan
> berhenti jujur ketika bukti belum cukup.

## Kesimpulan implementasi

VIGIL sudah melewati batas chatbot biasa: ada plan, tool selection, observation
loop, durable state, checkpoint/resume, evidence ledger, disconfirming search,
hypothesis lifecycle, bounded repair, structured stop, provenance, dan
human-in-the-loop. Hardening final membuat trajectory dan hubungan
hypothesis-evidence terlihat pada UI serta report.

Skor produk tidak boleh dinaikkan menjadi 10/10 hanya berdasarkan golden test
kecil. Jalan menuju product-grade yang defensible adalah comparative gate-off/
on study, corpus eksternal, red-team independen, load/soak, backup/RPO/RTO,
audit sink tamper-evident, dan validasi Docker E2E pada deployment target.
