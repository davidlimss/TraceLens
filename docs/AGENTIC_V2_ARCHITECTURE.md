# TraceLens VIGIL — Arsitektur Agentic V2 yang Diimplementasikan

Status: implementasi inkremental di atas single-agent TraceLens AI.

VIGIL (*Verified Investigation Graph & Evidence Loop*) memperkuat agent agar
memiliki rencana operasional, state epistemik, hypothesis registry, evidence
gap, bounded next-best action, dan loop perbaikan claim. Perubahan ini tidak
memindahkan parsing, sorting, correlation, detection, atau risk scoring ke
LLM.

## Kontrak runtime

State investigasi disimpan di `AgentRun.state` dengan schema
`vigil-state-v2`. State tersebut berisi:

- `plan`: lima langkah investigasi deterministik dengan objective, suggested
  tools, expected evidence, dependency, status, dan stop conditions;
- `hypotheses`: statement, status lifecycle (`proposed`, `investigating`,
  `supported`, `weakened`, `refuted`, `unresolved`), evidence pendukung dan
  kontradiktif, confidence, limitation, serta history perubahan;
- `evidence_gaps`: gap terbuka, prioritas, kandidat tool, hypothesis terkait,
  dan status;
- `epistemic_state`: evidence yang telah diamati, unknowns, alternatif, budget,
  dan action berikutnya;
- `repair_state`: alasan penolakan verifier dan jumlah repair attempt;
- `stop_state`: structured stop reason dan detail aman;
- `action_history` dan `collected_evidence_ids` yang dibatasi ukurannya.

State lama dimigrasikan secara aman di JSON oleh `ensure_vigil_state`; tidak
ada reset state diam-diam ketika run di-resume.

## Loop agent

```text
question
  -> initial_vigil_state()
  -> model memilih read-only tool
  -> case-scoped ToolRegistry
  -> observation + evidence ledger + next_action
  -> model dapat memilih tool berikutnya
  -> draft JSON
  -> verifier detailed reasons
  -> (maks. 2x) search evidence tambahan atau rewrite/downgrade
  -> verified answer / insufficient evidence
  -> structured stop reason
```

`search_disconfirming_evidence` adalah tool tambahan yang bounded. Tool hanya
mencari event terstruktur pada case aktif dengan filter entity/time allowlist;
tool tidak menerima arbitrary SQL, OpenSearch DSL, atau SPL.

## Stop policy

Run menyimpan salah satu kode berikut ketika berhenti:

`GOAL_SATISFIED`, `EVIDENCE_EXHAUSTED`, `INSUFFICIENT_EVIDENCE`,
`TOOL_BUDGET_EXHAUSTED`, `TIME_BUDGET_EXHAUSTED`, `NO_PROGRESS`,
`USER_PAUSED`, `USER_CANCELLED`, `PROVIDER_FAILURE`, atau
`VERIFICATION_FAILED`.

Stop reason adalah status operasional, bukan keputusan containment. Investigator
tetap menentukan apakah finding ditindaklanjuti.

## Verification-repair loop

`verify_claims_detailed` mengembalikan `verification_summary` dengan jumlah
claim lolos/ditolak dan `reason_code` terstruktur, misalnya
`MISSING_SUPPORT`, `SEMANTIC_MISMATCH`, `ENTITY_MISMATCH`, dan
`CONTRADICTORY_EVIDENCE_IGNORED`. Reason tersebut tidak berisi chain-of-thought
atau raw secret.

Untuk penolakan yang dapat diperbaiki, gateway dapat meminta model:

1. mengumpulkan evidence tambahan, termasuk evidence yang berpotensi
   membantah hypothesis; atau
2. menulis ulang claim menjadi status yang lebih tepat atau menyatakan bukti
   belum cukup.

Setelah maksimum dua attempt, sistem fail-closed. Gate tidak menghilangkan
hallucination secara matematis; gate mengurangi penerimaan claim yang tidak
memenuhi evidence dan semantic support.

## Observability dan UI

`AgentStep` mencatat model/tool/repair step, plan step, reason code, output
redacted, latency, dan evidence IDs. Endpoint run detail mengembalikan state
summary, investigation summary, steps, dan evidence ledger. Frontend Chat
menampilkan goal, plan status, hypotheses, evidence gap, verification count,
dan stop reason. Chain-of-thought tidak ditampilkan.

## Batasan yang tetap berlaku

- single-agent; tidak ada multi-agent kosmetik;
- tools read-only, bounded, dan case-scoped;
- raw evidence tetap immutable dan dianggap untrusted data;
- manusia tetap pengambil keputusan akhir;
- TraceLens bukan forensic-grade formal evidence dan bukan pengganti SOC
  analyst;
- risk score tetap heuristik, bukan probabilitas kompromi;
- provider rate limit atau outage dapat mengakhiri run dengan
  `PROVIDER_FAILURE`.

## Versi yang diaudit

- state schema: `vigil-state-v2` dengan case memory `case-memory-v2`; hanya
  summary dari run yang memiliki claim terverifikasi yang boleh dihidrasi;
- plan schema: `investigation-plan-v2` dengan goal profile dan success contract;
- prompt: `agent-investigator-vigil-v5`;
- graph: `investigation-graph-v3`;
- tool schema: `tools-v3-vigil`.

Perubahan pada parser, prompt, model, graph, risk, atau tool schema harus
menaikkan versi dan ditulis ke audit log.

## Evaluasi dan laporan

`backend/evals/run_vigil_eval.py` menjalankan enam golden state cases:
brute-force tanpa success, failure-followed-by-success, contradiction dari
maintenance benign, prompt-injection sebagai data, insufficient evidence, dan
cross-case policy state. Harness memeriksa next action, status hypothesis,
stop reason, state version, serta plan-tool allowlist; authorization lintas case
sendiri diuji pada suite security dengan database. Report Markdown/PDF
secara opsional menyertakan goal, plan, hypotheses, evidence gaps, verification
count, dan stop reason dari run terakhir; metadata tersebut bukan chain-of-thought.
