# Laporan Peningkatan TraceLens AI

## Ringkasan

Peningkatan ini memindahkan aplikasi dari demonstrator analisis log menjadi fondasi investigasi keamanan yang lebih dapat diaudit. Parser dan event model telah diperkaya, aturan deteksi ditambah, temuan diberi pemetaan MITRE ATT&CK dan confidence terpisah dari risk, laporan diperbaiki, serta evaluasi deterministik ditambahkan.

## Peningkatan yang Selesai

1. **Normalisasi keamanan**
   - Field event untuk event code, command line, parent process, port, protokol, HTTP, URL, user agent, dan file hash.
   - Normalisasi JSON untuk Cowrie, Windows Security, Sysmon, AWS CloudTrail, dan Suricata.
   - Dukungan access log, logfmt, JSON aplikasi, dan fallback teks generik tetap tersedia.

2. **Deteksi dan korelasi**
   - Brute force, password spraying, distributed password guessing.
   - Successful login after failures.
   - Suspicious PowerShell, indikasi eksploitasi web, persistence change, dan privilege escalation.
   - Pemetaan MITRE ATT&CK, pertimbangan false positive, dan rekomendasi query lanjutan.

3. **Penilaian temuan**
   - Risk score dan confidence score dipisahkan.
   - Confidence memiliki breakdown berdasarkan kualitas parser, timestamp, dukungan event, dan keragaman sumber.
   - Temuan lama dapat dihitung ulang melalui tombol **Analisis Ulang**.

4. **Dashboard dan laporan**
   - Grafik severity, outcome, sumber event, Top Source IP, dan cakupan MITRE ATT&CK.
   - Rundown deterministik berbasis event.
   - PDF formal monokrom dengan grafik, tabel yang membungkus teks, rekomendasi, confidence, MITRE, false-positive guidance, dan query tindak lanjut.

5. **Operasional dan validasi**
   - Endpoint `/health` dan `/ready` dengan pemeriksaan database dan versi engine.
   - Migrasi Alembic `0002_security_enrichment`.
   - Unit test backend, production build frontend, Docker build, dan smoke test service.
   - Golden-set benchmark untuk precision, recall, dan F1 deteksi.

## Bukti Pengujian

| Pemeriksaan | Hasil |
|---|---:|
| Backend test | 52 passed |
| Frontend production build | Passed |
| Internal detection golden set | Precision 1.00, Recall 1.00, F1 1.00 |
| Backend health/readiness | OK / ready |
| Frontend HTTP smoke test | 200 |
| Database migration | `0002_security_enrichment (head)` |

Nilai benchmark berasal dari golden set internal yang kecil dan terkontrol. Nilai tersebut menguji regresi aturan, bukan bukti performa pada seluruh log dunia nyata.

## Cara Menjalankan

```powershell
cd D:\SEM-6\AI\loginvestigator-x
docker compose up -d --build
```

- Web: `http://localhost:3001`
- API: `http://localhost:8002`
- Kesiapan API: `http://localhost:8002/ready`

Pengujian lokal:

```powershell
cd backend
pytest -q
python evals/run_detection_eval.py

cd ..\frontend
npm run build
```

## Batasan dan Tahap Berikutnya

Fitur berikut belum boleh dianggap selesai untuk penggunaan enterprise:

- parser biner native untuk EVTX dan PCAP;
- kalibrasi detection threshold menggunakan dataset eksternal berlabel dan multi-lingkungan;
- browser E2E otomatis untuk seluruh critical user journey;
- load/stress test dengan target SLO terukur;
- metrik Prometheus, tracing terdistribusi, backup/restore drill, dan incident runbook;
- workflow SOC lengkap seperti assignment, SLA, disposition, suppression, dan feedback tuning;
- pengujian keamanan independen dan deployment hardening produksi.

## Penilaian Setelah Peningkatan

Secara engineering, aplikasi sekarang memiliki **production-oriented SOC baseline**: workflow triage/disposition, audit trail, Prometheus metrics, SLO, burn alert, hardening Compose, CI security gates, backup/restore tooling, dan concurrency smoke harness. Ini meningkatkan kelayakan engineering di atas prototype biasa.

Namun, istilah **production-grade** tetap memerlukan sign-off lingkungan: secret manager, TLS/WAF, managed database/object storage, immutable audit retention, restore drill, staging E2E/soak/DAST, alert routing/on-call, serta security assessment independen. Detailnya tercatat di `docs/PRODUCTION_READINESS.md`.
