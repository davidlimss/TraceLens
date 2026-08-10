# VIGIL Phase 2 — Implementation Gap Map

Status: audit sebelum perubahan Phase 2; hasil implementasi dirangkum pada
`VIGIL_PHASE2_IMPLEMENTATION_REPORT_ID.md`  
Tanggal: 10 Agustus 2026

Klasifikasi ini dibuat dari source code, tests, migrations, evaluation harness,
frontend trace, dan dokumentasi repository. EXISTING berarti sudah tersedia dan
teruji pada level yang terlihat; PARTIAL berarti ada fondasi tetapi belum
memenuhi kontrak Phase 2; MISSING berarti belum tersedia.

| Fitur Phase 2 | Status | Bukti/gap |
|---|---|---|
| VIGIL durable state | EXISTING | AgentRun.state memakai vigil-state-v2. |
| Explicit plan dan allowlist | EXISTING | Plan, plan revision, dan suggested tool allowlist di vigil.py. |
| Formal deterministic state machine | PARTIAL | Ada status/stop_state, tetapi belum ada valid transition map dan transition history. |
| Central investigation policy engine | PARTIAL | Policy tersebar di gateway/vigil/registry; belum ada policy API terpadu. |
| Hypothesis lifecycle | EXISTING | proposed/investigating/supported/weakened/refuted/unresolved. |
| Competing hypotheses | PARTIAL | Registry mendukung beberapa item, tetapi relation/matrix dan ranking belum formal. |
| Hypothesis revision history | PARTIAL | History hanya status transition sederhana; belum trigger evidence/reason code/revision number. |
| Evidence provenance | EXISTING | Provenance edges dan evidence ledger tersedia. |
| Evidence quality | PARTIAL | Parser/timestamp confidence ada; belum ada quality object terstandar. |
| Contradictory evidence search | EXISTING | search_disconfirming_evidence tersedia. |
| Contradiction matrix | PARTIAL | Supporting/contradicting IDs ada; belum SUPPORTS/CONTRADICTS/NEUTRAL/UNKNOWN matrix. |
| Next action | EXISTING | select_next_action memilih gap/plan step secara bounded. |
| Next-best-action scoring | MISSING | Belum ada candidate score, cost, repeat penalty, atau rejected candidates. |
| Cost accounting | PARTIAL | Tool/round/latency tersimpan; usage tokens/provider cost belum dinormalisasi. |
| Evidence efficiency | MISSING | Belum ada useful evidence, duplicate ratio, no-progress ratio, unused evidence metric. |
| No-progress detection | PARTIAL | Fingerprint repetition ada; belum ada progress signal terstruktur. |
| Replay deterministic | MISSING | Belum ada replay endpoint/module yang memutar observation/state tanpa LLM. |
| Model re-evaluation | MISSING | Belum ada frozen snapshot re-run dengan run ID baru. |
| Run diff | MISSING | Belum ada comparator antar run/replay. |
| Trajectory quality | PARTIAL | VIGIL eval memeriksa plan/stop/status; belum required/optional/forbidden action metrics. |
| Golden dataset | PARTIAL | Ada 6 kasus internal; belum GC-001 sampai GC-010. |
| Adversarial suite | PARTIAL | Ada prompt injection/cross-case/claim tests; belum suite field-level dan failure injection lengkap. |
| Prompt-injection canary | PARTIAL | Envelope dan test dasar ada; belum corpus canary terukur. |
| Evaluation metrics | PARTIAL | Detection/VIGIL pass rate ada; metrik evidence/claim/stop/efficiency belum dihitung umum. |
| Gate-off/on ablation | MISSING | Belum ada controlled offline evaluator. |
| Contradiction ablation | MISSING | Belum ada evaluator search ON/OFF. |
| Planner ablation | MISSING | Belum ada direct-tool vs explicit-plan comparison. |
| Agent observability UI | PARTIAL | UI trace operasional ada; belum run overview/budget/coverage/replay/diff panel. |
| Provenance graph | PARTIAL | PostgreSQL/state edges ada; belum projection/why-claim view. |
| Why this claim | PARTIAL | Citation clickable ada; belum endpoint/structured provenance explanation. |
| Why not hypothesis | PARTIAL | Limitation/gap tersedia; belum dedicated explanation contract. |
| Case-bounded memory | EXISTING | State memory diisolasi dan ada regression test. |
| Immutable run snapshot | PARTIAL | Metadata ada di AgentRun; belum explicit frozen snapshot hash/schema. |
| Provider portability | EXISTING | OpenAI-compatible gateway/config provider abstraction. |
| Failure injection | PARTIAL | Provider/tool failure dasar ada; Redis/Celery/external/verification matrix belum lengkap. |
| Pause/resume | EXISTING | Endpoint dan test checkpoint/resume tersedia. |
| Documentation | PARTIAL | Arsitektur/VIGIL docs ada; Phase 2 contracts/evals/replay belum didokumentasikan. |

Prioritas implementasi:

1. state machine + policy engine karena menjadi guardrail dasar;
2. evidence quality + contradiction matrix + revision history;
3. action scoring + cost/progress metrics;
4. deterministic replay + run diff;
5. golden/adversarial/ablation evaluation;
6. observability UI, provenance explanation, dan dokumentasi.
