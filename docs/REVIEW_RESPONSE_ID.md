# Respons terhadap Review Capstone

Dokumen ini mencatat tindak lanjut repository TraceLens terhadap review
capstone yang diterima pada 13 Agustus 2026. Tujuannya adalah membuat bukti
perbaikan dapat diaudit oleh dosen, reviewer, dan kontributor berikutnya.

## Ringkasan review

| Item | Hasil review |
|---|---|
| Nilai | 87/100 |
| Confidence reviewer | 8/10 |
| Status | Sangat Baik |
| Fokus penilaian | Latar belakang, efektivitas solusi, manajemen kode/repository, dan novelty |

Review menilai TraceLens kuat karena memisahkan pemrosesan deterministik dari
reasoning LLM, menggunakan agent read-only yang case-scoped, menerapkan claim
verification, serta menyediakan dokumentasi dan kontrol keamanan yang cukup
jelas. Review juga mencatat tiga area yang dapat diperbaiki: lisensi belum
tersedia, riwayat commit di repository publik terlihat tipis, dan cakupan
format seperti EVTX/PCAP/real-time SIEM belum tersedia.

## Tindak lanjut yang dilakukan

### 1. Lisensi repository

Status: **selesai**.

Repository sekarang memiliki [LICENSE](../LICENSE) dengan lisensi MIT. Lisensi
ini memperjelas hak penggunaan kode aplikasi. Dependency pihak ketiga tetap
mengikuti lisensinya masing-masing dan evidence milik operator tidak menjadi
bagian dari lisensi aplikasi.

### 2. Bukti pengujian dan reproducibility

Status: **diperjelas dan ditautkan dari README**.

Hasil regression, evaluator offline, build frontend, runtime smoke, dan
readiness dicatat pada [TEST_EVIDENCE_REPORT_ID.md](TEST_EVIDENCE_REPORT_ID.md).
Dokumen tersebut mencantumkan revision source, perintah, hasil, serta batas
interpretasi. Corpus internal yang kecil tidak dipresentasikan sebagai bukti
generalisasi produksi.

CI juga menjalankan seluruh evaluator utama agar perubahan yang masuk ke
`main` tidak hanya melewati unit test, tetapi juga melewati pemeriksaan claim,
VIGIL, Phase 2, adversarial policy, dan detection golden set.

### 3. Riwayat commit dan manajemen repository

Status: **diperbaiki secara proses, tanpa memalsukan histori**.

Riwayat lama tidak ditulis ulang karena hal tersebut akan mengurangi
auditability. Mulai dari perubahan ini, kontribusi mengikuti pull request,
review, changelog, test evidence, dan release checklist. Commit berikutnya
sebaiknya kecil, tematik, dan menjelaskan perubahan perilaku atau dokumentasi.
Dokumen yang menjadi acuan:

- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [RELEASE_PROCESS.md](RELEASE_PROCESS.md)
- [CHANGELOG.md](../CHANGELOG.md)
- [PROJECT_CHARTER.md](PROJECT_CHARTER.md)

Jumlah commit bukan metrik kualitas teknis. Yang dapat diverifikasi adalah
diff, test, review, provenance, dan release artifact yang dihasilkan.

### 4. Batasan format dan integrasi

Status: **dipertahankan sebagai batas scope yang jujur**.

EVTX native, PCAP, cloud audit provider khusus, dan real-time SIEM ingestion
belum diklaim sebagai fitur selesai. README dan threat model menyebutkan
batas ini secara eksplisit. Menambahkan parser besar tanpa corpus, test,
provenance, dan resource isolation akan lebih berisiko daripada menyatakan
fitur tersebut sebagai roadmap.

### 5. Memory poisoning pada agent

Status: **diperkeras dan diuji**.

Memory antar-run tetap dibatasi pada case aktif dan hanya membawa ringkasan
operasional. Selain filter case boundary, gateway sekarang hanya menghidrasi
memory dari run yang mempunyai `verification_summary.verified_count > 0` dan
`final_claim_ids`. Run abstain, gagal, atau provider-error tidak dapat menjadi
sumber konteks untuk investigasi berikutnya. Regression test khusus memastikan
entity dari memory yang tidak terverifikasi tidak ikut masuk ke state baru.

## Bukti verifikasi saat ini

Angka berikut adalah bukti regression dan smoke path repository pada corpus
internal terkontrol, bukan sertifikasi keamanan atau jaminan performa produksi:

- 88 backend test pada baseline report, 91 test pada review-hardening awal, dan
  95 test pada rerun setelah goal-aware playbook serta case-memory hydration;
- claim/evidence evaluator 5/5;
- VIGIL evaluator 6/6;
- Phase 2 evaluator 10/10;
- adversarial policy/envelope 11/11;
- detection golden 6/6;
- frontend typecheck dan production build;
- Compose/readiness/runtime ingestion smoke;
- load smoke readiness 200 request, success rate 100%, p95 424.26 ms pada
  concurrency 20 (smoke lokal, bukan SLO produksi).

Rincian dan batasan tersedia di
[TEST_EVIDENCE_REPORT_ID.md](TEST_EVIDENCE_REPORT_ID.md). Nilai review tidak
diubah secara otomatis oleh dokumen ini dan tidak ada klaim bahwa TraceLens
sudah forensic-grade atau enterprise-ready.

Catatan reproduksi: rerun 95 test masih berasal dari working tree yang belum
ditag. Setelah merge/release, laporan bukti pengujian harus diperbarui dengan
commit SHA yang baru agar angka dan source revision kembali satu-ke-satu.

## Pekerjaan yang masih terbuka

1. Memperluas corpus dengan kasus benign, contradictory evidence, timestamp
   ambigu, dan format eksternal.
2. Menjalankan perbandingan gate-off/gate-on dengan anotator manusia.
3. Melakukan load/soak, concurrency/idempotency, dan backup-restore drill pada
   staging.
4. Menyediakan TLS/WAF, managed secrets, object storage terenkripsi, RLS, dan
   audit append-only eksternal sebelum deployment operasional.

Dokumen ini adalah catatan engineering, bukan jaminan bahwa semua pekerjaan
terbuka telah selesai.
