# TraceLens AI — Test Evidence Report

Tanggal verifikasi: **11 Agustus 2026**  
Source revision: **`2bf0ca2cc06b0dc8dbec49eccdce7debcd24fbf3`**  
Environment: Windows development host, Docker Desktop/WSL2, Python 3.12, Node.js 22, Docker Compose.

Dokumen ini adalah bukti engineering yang dapat direproduksi untuk proposal dan demo. Hasil di bawah membuktikan bahwa regression path yang tersedia berjalan pada revision tersebut. Hasil ini bukan klaim generalisasi pada corpus SOC besar, bukan independent red-team, dan bukan sertifikasi forensic-grade.

### Catatan rerun setelah review-hardening

Pada 13 Agustus 2026, regression suite di working tree setelah upgrade
goal-aware VIGIL dan case-memory hydration menghasilkan **95 passed, 1 warning** dengan perintah
`python -m pytest -q -o addopts=''`. Seluruh evaluator offline juga diulang:
claim `5/5`, VIGIL `6/6`, Phase 2 `10/10`, adversarial `11/11`, dan detection
`6/6`. Rerun ini belum memiliki commit/tag baru sehingga tidak menggantikan
source revision baseline di atas; setelah merge/release, SHA baru wajib
ditambahkan ke laporan ini. Runtime Docker pada tabel berikut tetap merujuk
pada baseline yang sudah dijalankan. Pada rerun Docker yang sama, image
backend/frontend berhasil dibangun, `/health` dan `/ready` lulus dengan schema
`0007_vigil_replay_snapshots`, dan load smoke readiness menghasilkan 200/200
request berhasil pada concurrency 20, p50 130.99 ms, p95 424.26 ms, dan
maximum 470.82 ms. Angka load smoke ini hanya smoke check lokal, bukan SLO
availability produksi. Frontend container juga merespons HTTP `200` pada port
`3002` pada rerun ini.

## 0. Prosedur Docker-only

Jalankan dari root repository menggunakan PowerShell. Perintah berikut tidak
membutuhkan Python atau Node.js yang terpasang di host; dependency test diambil
dari image/container.

```powershell
cd D:\SEM-6\AI\loginvestigator-x

docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose build backend frontend

docker compose run --rm backend pytest -q -o addopts=''
docker compose run --rm backend python evals/run_eval.py
docker compose run --rm backend python evals/run_vigil_eval.py
docker compose run --rm backend python evals/run_phase2_eval.py
docker compose run --rm backend python evals/run_adversarial_eval.py
docker compose run --rm backend python evals/run_detection_eval.py

# Build frontend menjalankan production compile di Dockerfile builder.
# Next.js akan memvalidasi TypeScript selama build karena tidak ada
# ignoreBuildErrors pada next.config.
docker compose build frontend

docker compose up -d
docker compose ps
Invoke-RestMethod http://localhost:8002/health
Invoke-RestMethod http://localhost:8002/ready
```

Jika host port `3001` sedang dipakai container lain, backend tetap dapat diuji.
Jalankan frontend demo pada port alternatif tanpa menghentikan container lain:

```powershell
docker compose run -d --name tracelens-frontend-demo -p 3002:3000 frontend
```

Buka `http://localhost:3002`. Setelah selesai, hapus hanya container demo yang
dibuat untuk pengujian:

```powershell
docker rm -f tracelens-frontend-demo
```

Jangan menggunakan `docker compose down -v` karena perintah tersebut menghapus
database dan evidence volume.

## 1. Ringkasan hasil

| Area | Perintah/artefak | Hasil | Status |
|---|---|---:|---|
| Backend regression | `cd backend; pytest -q -o addopts=''` | 95 passed, 1 warning | PASS |
| Claim/evidence evaluator | `python backend/evals/run_eval.py` | 5/5, pass rate 1.0 | PASS |
| VIGIL offline evaluator | `python backend/evals/run_vigil_eval.py` | 6/6, pass rate 1.0 | PASS |
| VIGIL Phase 2 | `python backend/evals/run_phase2_eval.py` | 10/10, pass rate 1.0 | PASS |
| Adversarial policy smoke | `python backend/evals/run_adversarial_eval.py` | 11/11, pass rate 1.0 | PASS |
| Detection golden set | `python backend/evals/run_detection_eval.py` | 6/6; precision 1.0, recall 1.0, F1 1.0 | PASS |
| Frontend type safety | `npm run typecheck` | TypeScript exit code 0 | PASS |
| Frontend production build | `npm run build` | Next.js 15.5.23 build exit code 0 | PASS |
| Compose validation | `docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet` | Exit code 0 | PASS |
| Runtime API | `GET /health`, `GET /ready` | health `ok`; DB/Redis/storage `ok`; schema `0007_vigil_replay_snapshots` | PASS |
| Runtime ingestion smoke | login → case → upload → worker → timeline/findings | login 200; case 201; upload 202; file parsed; 8 events; 3 findings | PASS |
| Frontend container smoke | isolated port `3002` | HTTP 200; Next server ready | PASS |

Warning pytest berasal dari deprecation dependency (`reportlab`/`pytest-asyncio`) dan tidak menyebabkan test gagal. Warning tersebut dicatat sebagai technical-debt item, bukan disembunyikan.

## 2. Evidence VIGIL dan claim gate

`run_phase2_eval.py` menghasilkan ringkasan berikut:

| Metrik | Gate off | Gate on |
|---|---:|---:|
| Unsupported claim rate | 0.8889 | 0.0000 |
| Task completion | 1.0000 | 1.0000 |
| Evidence recall | 1.0000 | 1.0000 |
| Evidence precision | 1.0000 | 1.0000 |
| Contradiction discovery rate | 1.0000 | 1.0000 |
| Forbidden-tool violation rate | 0.0000 | 0.0000 |

Interpretasi yang sah: pada **golden harness offline** ini, gate menahan candidate claim yang tidak memiliki dukungan yang diterima oleh ground truth. Interpretasi yang tidak sah: menyebut angka tersebut sebagai akurasi produksi atau bukti bahwa model selalu benar. Harness Phase 2 tidak memanggil provider/model live; ia menguji state, policy, verifier, dan trajectory fixture secara deterministik.

Kasus yang tercakup meliputi repeated failures, failure-then-success, maintenance contradiction, prompt injection sebagai data, insufficient evidence, cross-case citation, duplicate ingestion, timestamp ambiguity, shared NAT source IP, dan external-source failure.

## 3. Evidence security dan adversarial

Sebelas smoke case policy/envelope lulus:

`direct injection`, `indirect injection`, `secret redaction`, `arbitrary tool`, `arbitrary SQL`, `cross-case tool`, injection pada username/URL/user-agent, oversized observation, dan UUID spoof.

Scope-nya adalah deterministic policy/envelope smoke test. Ini belum menggantikan penetration test, DAST, independent red-team, atau pengujian provider yang dikompromikan.

## 4. Evidence runtime end-to-end

Runtime Docker berhasil menjalankan PostgreSQL, Redis, FastAPI backend, Celery worker, dan scheduler. Hasil readiness:

```json
{
  "status": "ready",
  "database": "ok",
  "redis": "ok",
  "evidence_storage": "ok",
  "schema_revision": "0007_vigil_replay_snapshots",
  "parser_version": "1.1.0",
  "risk_version": "risk-v1.1"
}
```

Smoke ingestion memakai `samples/demo-linux-auth.log` dan menghasilkan:

1. login berhasil;
2. case baru berhasil dibuat;
3. upload diterima sebagai `202 queued`;
4. Celery menyelesaikan file menjadi `parsed`;
5. 8 event canonical tersimpan tanpa malformed line;
6. endpoint timeline mengembalikan 8 event;
7. endpoint findings mengembalikan 3 finding.

## 5. Penjelasan error “Failed to fetch”

Pada saat smoke Compose, backend, PostgreSQL, Redis, worker, dan scheduler berhasil hidup. Frontend gagal di-bind pada port host `3001` karena port tersebut sedang dipakai container proyek lain (`pulih_id_codex_pack-admin-web-1`). Jadi error tersebut adalah **environment/port collision**, bukan bukti bahwa route Next.js atau API TraceLens rusak.

Verifikasi isolasi pada port `3002` menghasilkan HTTP 200 dan log Next.js `Ready`. Solusi demo:

```powershell
docker ps --filter publish=3001
docker stop <container-yang-memakai-3001>
docker compose up -d
```

Jangan menghentikan container proyek lain tanpa memastikan bahwa container tersebut memang tidak sedang digunakan. Alternatif aman adalah memakai port frontend lain dan menyesuaikan `FRONTEND_PORT` serta `CORS_ORIGINS`.

## 6. Cara memasukkan ke proposal

Tempatkan dokumen ini sebagai **Lampiran F — Evaluator dan Hasil Eksperimen** atau jadikan bukti pendukung pada Lampiran G. Di naskah utama, tulis hasil dengan format:

> Pada working tree setelah upgrade goal-aware VIGIL dan case-memory hydration, regression suite backend menghasilkan 95 test lulus. Evaluasi offline VIGIL menghasilkan 10/10 golden case, adversarial policy smoke 11/11, detection golden set 6/6 dengan precision, recall, dan F1 sebesar 1.0, serta production build frontend lulus. Hasil tersebut merupakan validasi engineering internal pada corpus terbatas dan tidak diposisikan sebagai generalisasi produksi.

Versi proposal yang sudah memasukkan hasil aktual tersebut dibuat sebagai
`PROPOSAL_TRACELES_AI_DAVID_SAM_LIMBONG_III_IEEE_BUKTI_PENGUJIAN.docx`.
Versi lanjutan yang sudah menyematkan tujuh screenshot Docker/UI pada Lampiran
H dibuat sebagai
`PROPOSAL_TRACELES_AI_DAVID_SAM_LIMBONG_III_IEEE_BUKTI_DOCKER_UI.docx`.
Setelah field dan daftar isi diperbarui dengan Microsoft Word, versi pertama
berisi 47 halaman dan versi dengan screenshot berisi 52 halaman (sekitar 8.651
kata). Angka halaman dapat berubah bila template, font, atau margin kampus
berbeda.

Lampirkan juga file JSON yang sudah ada di repository:

- `backend/eval-results.json`;
- `backend/phase2-eval-results.json`;
- `backend/adversarial-eval-results.json`;
- `backend/detection-eval-results.json`.

## 7. Yang masih harus diuji sebelum klaim produk penuh

- gate-off/gate-on dengan annotator manusia dan confidence interval;
- corpus eksternal yang lebih besar dan benign/conflicting cases;
- concurrency, idempotency ingestion, load/soak, dan queue backlog;
- backup/restore drill dengan RPO/RTO terukur;
- TLS/WAF, secret manager, object storage terenkripsi, dan audit append-only;
- independent security assessment/red-team;
- screenshot UI final pada deployment yang port-nya tidak bentrok.
