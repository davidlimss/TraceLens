# Threat Model MVP

## Aset yang dilindungi

- File evidence asli, hash SHA-256, dan metadata chain-of-custody.
- Event kanonik beserta hubungan ke baris log asli.
- Temuan, correlation, jawaban agent, citation, dan audit trail.
- GitHub Models token, session pengguna, dan kredensial PostgreSQL/Redis.

## Trust boundaries

1. Browser ke FastAPI menerima input tidak tepercaya: UUID case, pertanyaan chat, filter, filename, MIME, dan bytes upload.
2. Celery membaca evidence dari shared volume dan menulis transformasi deterministik ke PostgreSQL.
3. GitHub Models menerima pertanyaan dan hasil tool read-only. Raw log tidak dikirim secara default; jika operator mengaktifkannya, isi log tetap diperlakukan sebagai data tidak tepercaya.
4. PostgreSQL dan Redis berada di jaringan Compose internal, tetapi operator database/container tetap privileged.

## Mitigasi yang sudah diterapkan

- Upload maksimum default 50 MiB, dapat dikonfigurasi melalui `MAX_UPLOAD_BYTES`.
- Allowlist extension dan MIME, validasi UTF-8, serta deteksi format dari konten sebelum enqueue.
- Filename dinormalisasi dan path separator, NUL, absolute path, serta traversal ditolak.
- File evidence disimpan dengan UUID pada canonical path di bawah evidence root, bukan memakai filename user.
- Evidence dihitung SHA-256 saat streaming dan dibuat read-only pada filesystem.
- Raw event memiliki ORM guard dan trigger PostgreSQL untuk mencegah perubahan evidence fields.
- Semua query resource child memerlukan `case_id`; event/evidence dari case lain menghasilkan 404.
- Session HttpOnly, CSRF double-submit, global role, dan membership per-case membatasi akses. Bootstrap admin hanya untuk inisialisasi lokal.
- Agent tools mengunci case aktif dan menolak `case_id` tool call yang berbeda.
- Upload dan chat memiliki fixed-window rate limiting per alamat IP. Redis menjadi shared counter; fallback process-local digunakan saat Redis tidak tersedia.
- Tool output dan raw log dibungkus sebagai `UNTRUSTED_DATABASE_DATA`; instruction-like content ditandai.
- Claim gate menghapus claim tanpa status valid dan `evidence_id` yang terdapat dalam case aktif.
- Upload berhasil/ditolak, jawaban agent, evidence IDs jawaban, kegagalan agent, dan pembuatan export dicatat ke audit log.
- React melakukan escaping teks secara default dan aplikasi tidak memakai `dangerouslySetInnerHTML`.

## Keterbatasan yang belum dimitigasi

- Belum tersedia UI/flow self-service untuk membuat pengguna, merotasi password, recovery, MFA, SSO, atau mengelola membership. Bootstrap admin harus diamankan secara operasional.
- Rate limiting masih per-IP, bukan per-user. Di belakang reverse proxy, konfigurasi jaringan harus memastikan `request.client.host` merepresentasikan boundary yang benar. Fallback process-local tidak konsisten antar-replica dan lebih lemah daripada Redis.
- MIME berasal dari metadata request dan dapat dipalsukan. Deteksi konten/actual parser adalah validasi utama; belum ada libmagic, antivirus, atau malware scanning.
- Tidak ada compressed archive support, sehingga zip bomb tidak diproses. File besar dibatasi bytes, tetapi event yang sangat banyak masih dapat memakai CPU/memori worker secara signifikan.
- Evidence read-only tidak melindungi dari root/container administrator atau storage administrator. Audit log juga belum cryptographically signed/WORM dan dapat diubah oleh database administrator.
- Claim gate memverifikasi bahwa evidence ID valid, tetapi belum membuktikan secara formal bahwa makna claim benar-benar mengikuti evidence. Investigator tetap harus membuka citation dan memeriksa raw log.
- Prompt-injection defense mengurangi risiko tetapi tidak menjamin model tidak pernah terpengaruh. Read-only tools dan claim gate membatasi dampak.
- Belum ada TLS termination/HSTS di Docker Compose. Production harus ditempatkan di belakang reverse proxy HTTPS.
- Secret masih berasal dari environment variables; production sebaiknya memakai secret manager dan rotasi.
- Export PDF menggunakan browser print dialog. Audit mencatat bahwa export dibuat/diminta, tetapi server tidak dapat mengetahui apakah user menyelesaikan atau membatalkan penyimpanan PDF.
- Belum ada SIEM, threat intelligence eksternal, real-time ingestion, multi-tenancy, atau format di luar scope MVP.

## Prioritas sebelum production

1. Tambahkan lifecycle user lengkap (password rotation/recovery, MFA/SSO, dan UI membership) serta policy test end-to-end multi-user.
2. Terapkan TLS, trusted-proxy configuration, serta rate limit per-user dan global circuit breaker.
3. Gunakan object storage immutable/WORM, audit signing, secret manager, dan backup terenkripsi.
4. Tambahkan job memory/time limits, observability, dependency/container scanning, dan retention policy.
5. Lakukan adversarial evaluation berkala untuk prompt injection dan semantic evidence entailment.
