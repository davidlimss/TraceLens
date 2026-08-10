# TraceLens AI / VIGIL Phase 2 — Laporan Implementasi

Status: implementasi lokal selesai dan tervalidasi pada 10 Agustus 2026  
Ruang lingkup: reliability agent, evaluasi, replay, adversarial smoke test,
observability, dan evidence provenance.  
Posisi produk: production-oriented beta foundation; bukan forensic-grade,
bukan pengganti SOC analyst, dan belum menjadi autonomous-response platform.

## 1. Ringkasan hasil

Phase 2 memperkuat VIGIL dari agent loop yang sudah memiliki plan dan state
menjadi supervisor yang mempunyai state machine eksplisit, policy gate
deterministik, evidence quality, contradiction matrix, revision history,
action ranking, cost/progress accounting, snapshot immutable, deterministic
replay, run diff, dan evaluasi adversarial.

LLM tetap hanya mengusulkan tool, update plan, hypothesis, atau stop reason.
Backend yang memutuskan apakah operasi tersebut legal. Parsing, normalisasi,
timeline, correlation, detection, dan risk score tetap berada di analysis plane
deterministik.

## 2. Peta gap dan status implementasi

| Area | Status | Implementasi |
|---|---|---|
| Durable state, plan, evidence gap, hypothesis | Ada | `backend/app/vigil.py` |
| State machine formal | Ada | `backend/app/vigil_policy.py`, persisted lifecycle history |
| Policy transition/tool/repair/replan/stop | Ada | `InvestigationPolicy` dan `PolicyDecision` |
| Evidence quality | Ada | integrity, parser, timestamp, directness, source, corroboration, flags |
| Competing hypotheses | Ada | Registry multi-hypothesis dengan `competition_group` dan ranking status/confidence |
| Contradiction matrix | Ada | SUPPORTS, CONTRADICTS, NEUTRAL, UNKNOWN |
| Hypothesis revision history | Ada | revision, trigger evidence, reason code, before/after status |
| Next-best-action scoring | Ada | candidate actions, score, estimated cost, reason codes |
| Cost dan progress accounting | Ada | model/tool calls, bytes, external calls, repairs, no-progress, useful evidence |
| Deterministic replay | Ada | `backend/app/replay.py`, replay endpoint |
| Model re-evaluation | Belum diaktifkan | Endpoint mengembalikan 501 sampai provider/model fixture dibekukan |
| Run diff | Ada | perbandingan trajectory, evidence, hypothesis, claims, stop, latency, cost |
| Golden cases | Ada | `backend/evals/phase2_golden_cases.json`, 10 kasus GC-001--GC-010 |
| Adversarial smoke | Ada | prompt canary, redaction, arbitrary tool, cross-case policy |
| Independent red-team | Belum | wajib sebelum klaim security production |
| Observability “why claim/why not” | Ada pada level operasional | UI claim details dan hypothesis evidence/rejection |
| Immutable run snapshot | Ada | migration `0007_vigil_replay_snapshots` |
| Failure injection suite | Parsial | no-progress/provider policy tercakup; chaos/load staging belum |

## 3. State machine dan policy

Lifecycle state yang dipersist:

```text
INITIALIZED -> PLANNING -> INVESTIGATING -> EVIDENCE_REVIEW -> VERIFYING
                                          |                   |
                                          v                   v
                                       PAUSED             REPAIRING
                                                              |
                                                              v
                                             INVESTIGATING / VERIFYING

VERIFYING -> COMPLETED | ABSTAINED | FAILED | PAUSED | CANCELLED
```

Setiap transisi menyimpan `previous_state`, `current_state`, alasan,
timestamp, transition version, dan state-machine version. Transisi terminal
tidak dapat dilanjutkan secara normal. Test invalid transition memastikan
attempt seperti `COMPLETED -> INVESTIGATING` ditolak.

Policy memeriksa:

- tool harus ada di allowlist dan sesuai active plan step;
- case ID tool harus sama dengan case aktif;
- budget tool dan pengulangan tool;
- repair/replan budget;
- status hypothesis dan kebutuhan evidence;
- stop reason dan terminal state.

## 4. Evidence quality dan contradiction handling

`evidence_quality` menyimpan deskripsi kualitas data, bukan probabilitas bahwa
serangan terjadi. Field utamanya adalah integrity status, parser quality,
timestamp quality, directness, source type, corroboration, dan quality flags.

`contradiction_matrix` memetakan hubungan evidence terhadap hypothesis. Status
yang tersedia adalah `SUPPORTS`, `CONTRADICTS`, `NEUTRAL`, atau `UNKNOWN`; data
yang belum mempunyai relasi eksplisit tidak dipaksa menjadi dukungan.

Hypothesis menyimpan revision history. Setiap perubahan mencatat nomor revisi,
status sebelum/sesudah, evidence pemicu, alasan perubahan, dan waktu. Dengan
demikian, investigator dapat membedakan perubahan hypothesis karena evidence
baru dari perubahan karena model mengulang narasi.

## 5. Action ranking, cost, dan progress

Candidate action diberi score deterministik berdasarkan priority gap, relevansi
hypothesis, expected evidence value, diversity/novelty bonus, estimated cost,
repeat penalty, dan remaining budget. Ranking hanya memilih langkah read-only;
tidak ada action eksternal yang dapat dieksekusi.

Cost accounting menyimpan model calls, tool calls, tool result bytes, input dan
output token jika provider mengirim usage, external source calls, repair count,
plan revision count, dan elapsed time. Progress menyimpan useful evidence,
resolved gaps, contradictions baru, signal count, dan no-progress count.

## 6. Replay dan run diff

Run completion membuat payload snapshot dengan hash kanonik. Snapshot berisi
versi parser/model/prompt/graph/risk/tool registry, state operasional, tool
trajectory, evidence ledger, verification summary, stop reason, dan claim IDs.

Endpoint:

```text
POST /cases/{case_id}/agent-runs/{run_id}/replay
GET  /cases/{case_id}/agent-runs/{run_id}/diff/{other_run_id}
```

Mode `deterministic_trace` mereplay observation yang sudah tersimpan tanpa
memanggil LLM. Mode `model_re_evaluation` sengaja belum aktif dan mengembalikan
501 sampai tersedia frozen provider/model, seed atau temperature policy,
prompt snapshot, dan environment yang dapat direproduksi.

Run diff bersifat deskriptif. Ia membandingkan jumlah/nama tool, evidence,
perubahan status hypothesis, claim IDs, stop reason, latency, dan cost. Diff
tidak menyatakan run mana yang “lebih benar” tanpa reviewer atau rubric.

## 7. Evaluasi yang tersedia

Perintah dari folder `backend/`:

```powershell
python evals/run_phase2_eval.py --output phase2-eval-results.json
python evals/run_adversarial_eval.py
python evals/run_vigil_eval.py
python evals/run_detection_eval.py --output detection-eval-results.json
```

Hasil lokal terakhir:

Raw output disimpan pada `backend/phase2-eval-results.json` dan
`backend/adversarial-eval-results.json`.

| Evaluasi | Hasil | Interpretasi |
|---|---:|---|
| Backend pytest | 82 passed | Regression/unit/integration path yang tersedia |
| VIGIL baseline | 6/6 | State dan plan corpus internal kecil |
| Detection golden | precision 1.0, recall 1.0, F1 1.0 | Corpus detection internal kecil |
| Phase 2 golden | 10/10 | Harness offline GC-001--GC-010 |
| Evidence recall/precision | 1.0 / 1.0 | Nilai pada anotasi golden, bukan corpus SOC eksternal |
| Contradiction discovery | 1.0 | Nilai pada anotasi golden |
| Gate-off unsupported claim rate | 0.8889 | Deskriptif dari fixture gate-off |
| Gate-on unsupported claim rate | 0.0 | Deskriptif dari fixture gate-on |
| Forbidden tool violation | 0.0 | Percobaan forbidden tool diblok policy |
| Adversarial smoke | 11/11 | Injection canaries, redaction, truncation, UUID spoof, tool allowlist, case boundary |
| Frontend typecheck/build | lulus | Build Next.js lokal |

Gate-off dan gate-on pada Phase 2 saat ini adalah evaluasi fixture/offline.
Parser, tools, case, dan schema tetap sama pada anotasi; perbedaan yang
direpresentasikan adalah penyaringan claim. Ini belum merupakan uji statistik
keunggulan agent atau gate pada model/provider nyata.

## 8. UI dan provenance

Chat menampilkan state lifecycle, tujuan dan langkah rencana, hypothesis,
evidence gap, next action, cost/progress, evidence quality, contradiction
matrix, verification summary, stop reason, serta trace agent tanpa chain of
thought.

Setiap claim memiliki panel “Mengapa claim ini ditampilkan?” yang menjelaskan
status, verification status, jumlah evidence, dan alasan verifier. Hypothesis
dengan evidence kontradiktif, bukti yang hilang, atau alternatif benign memiliki
panel “Mengapa belum dianggap fakta?”.

## 9. Batasan yang masih terbuka

1. Model re-evaluation belum aman direproduksi tanpa frozen provider fixture.
2. Golden corpus 10 kasus bukan validasi generalisasi atau SOC-scale.
3. Adversarial suite lokal bukan independent red-team.
4. Load/soak, chaos, concurrency ingestion, dan backup/restore drill perlu
   dijalankan di staging.
5. Audit aplikasi masih perlu external append-only/hash-chained sink untuk
   target deployment berisiko tinggi.
6. Rule semantic untuk menetapkan `NEUTRAL` secara otomatis masih perlu
   diperkaya; saat ini status tersebut dapat diberikan eksplisit pada hypothesis.
7. R1/R2/R3 approval dan rollback hanya perlu diaktifkan bila kelak write/action
   tools ditambahkan; saat ini seluruh tool tetap read-only.

## 10. Demo teknis yang disarankan

Gunakan fixture lokal GC-003 atau GC-004:

1. upload failed-login event dan maintenance/prompt-injection line;
2. ajukan tujuan investigasi;
3. tampilkan plan dan tool trajectory;
4. tampilkan contradiction matrix dan evidence quality;
5. tunjukkan hypothesis melemah atau claim ditolak;
6. buka “why claim/why not”, run snapshot, dan deterministic replay;
7. tutup dengan keterbatasan: read-only, human-in-the-loop, dan bukan
   forensic-grade.

Jangan menjadikan Groq, OpenSearch publik, atau koneksi internet sebagai
dependency utama demo. Live provider hanya bonus; replay fixture adalah jalur
yang dapat diulang.

## 11. Kesimpulan

Phase 2 berhasil menutup gap reliability dan auditability utama pada agent
investigasi bounded. Implementasi sekarang cukup kuat untuk demo teknis dan
staging terbatas, dengan bukti regression lokal yang jelas. Klaim produk tetap
harus dibatasi: sistem membantu investigator, bukan mengambil keputusan
insiden terakhir; claim gate mengurangi penerimaan claim unsupported, bukan
menghilangkan hallucination; dan nilai riset/produksi harus dibuktikan dengan
corpus eksternal, human review, red-team, load test, serta disaster-recovery
drill.
