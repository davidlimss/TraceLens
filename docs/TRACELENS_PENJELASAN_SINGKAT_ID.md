# TraceLens AI
## Penjelasan Sederhana untuk Audiensi

### 1. TraceLens AI itu apa?

TraceLens AI adalah asisten investigasi keamanan. Sistem ini menerima log mentah, merapikannya, menyusun urutan kejadian, mencari pola mencurigakan, lalu membantu investigator memahami hasilnya.

Kalimat paling mudah:

> Log mentah menjadi timeline insiden yang bisa dijelaskan dan dibuktikan kembali ke baris log asli.

### 2. Masalah yang diselesaikan

Log biasanya berasal dari banyak aplikasi dan bentuknya berbeda. Investigator harus membaca ribuan baris, mencari urutan kejadian, dan menghubungkan IP atau akun yang sama.

TraceLens membantu tiga hal:

- mengubah log berbeda menjadi data yang seragam;
- menyusun kejadian berdasarkan waktu;
- memberi penjelasan AI yang tetap menunjuk ke bukti asli.

### 3. Cara kerja dalam enam langkah

```text
1. Buat case
       |
2. Upload file log
       |
3. Sistem membaca dan merapikan log
       |
4. Timeline dan hubungan antar-event dibuat
       |
5. Pola mencurigakan dan risk score dihitung
       |
6. AI menjelaskan hasil dengan citation bukti
```

### 4. Analogi sederhana

Bayangkan investigator memiliki ribuan rekaman CCTV.

- Parser adalah penerjemah rekaman menjadi catatan.
- Timeline adalah menyusun catatan sesuai waktu.
- Correlation adalah menghubungkan orang, lokasi, atau kendaraan yang sama.
- Risk score adalah menentukan kejadian mana yang harus diperiksa lebih dulu.
- AI adalah asisten yang menceritakan kembali hasil pemeriksaan.
- Evidence ID adalah nomor rekaman yang bisa dibuka untuk membuktikan cerita tersebut.

### 5. Contoh kasus

```text
10:01  Login gagal untuk admin dari 192.168.1.5
10:02  Login gagal untuk admin dari 192.168.1.5
10:03  Login gagal untuk admin dari 192.168.1.5
10:04  Login berhasil untuk admin dari 192.168.1.5
```

Sistem mengenali pola:

> Banyak login gagal diikuti login berhasil dari IP yang sama.

Ini disebut finding yang perlu diprioritaskan. Sistem tidak langsung menyatakan bahwa serangan pasti terjadi. Investigator tetap memeriksa bukti dan konteksnya.

### 6. Mana yang dikerjakan sistem dan mana yang dikerjakan AI?

#### Dikerjakan oleh kode deterministik

- deteksi format;
- parsing dengan regex;
- normalisasi timestamp;
- pengurutan timeline;
- correlation berdasarkan IP, user, dan session;
- deteksi brute force;
- risk score dan breakdown.

#### Dikerjakan oleh AI

- memilih tool database yang relevan;
- menjelaskan temuan dengan bahasa manusia;
- membuat interpretasi atau hipotesis;
- menjawab pertanyaan investigator.

AI tidak boleh mem-parsing atau mengarang event baru.

### 7. Mengapa jawaban AI bisa dipercaya?

Setiap klaim AI wajib memiliki:

- `evidence_id` yang valid;
- status `fact`, `inference`, atau `hypothesis`;
- hubungan ke case yang sedang dibuka.

Investigator dapat mengeklik citation untuk melihat raw log dan nomor baris aslinya.

Jika bukti tidak cukup, sistem harus menjawab:

> Data belum cukup untuk memastikan hal tersebut.

### 8. Perlindungan dasar

- Raw log disimpan dan tidak boleh ditimpa.
- File diberi hash SHA-256.
- Akses dibatasi berdasarkan `case_id`.
- Isi log dianggap data, bukan instruksi untuk AI.
- Upload dibatasi ukuran dan formatnya.
- Aktivitas upload, chat, dan export dicatat dalam audit log.

### 9. Arti `LLM_MAX_TOOL_CALLS=20`

Parameter ini membatasi AI maksimal memanggil tool database 20 kali untuk satu pertanyaan.

Tujuannya:

- mencegah AI berputar tanpa akhir;
- mengontrol biaya API;
- menjaga waktu respons;
- membatasi penggunaan resource.

Parameter ini bukan skor kecerdasan model.

### 10. Cara demo ke audiensi

1. Login ke aplikasi.
2. Buat case baru.
3. Upload sample log.
4. Tunjukkan format terdeteksi dan jumlah event.
5. Buka timeline.
6. Buka finding brute force.
7. Tanyakan kepada AI: `Apa yang terjadi pada case ini?`
8. Tunjukkan claim dan badge fact/inference/hypothesis.
9. Klik evidence ID dan buka raw log asli.
10. Tanyakan sesuatu yang tidak ada di log dan tunjukkan jawaban `belum cukup bukti`.

### 11. Kalimat presentasi siap pakai

> TraceLens AI bukan AI yang bebas menebak isi log. Sistem membaca dan menganalisis log secara deterministik, kemudian AI hanya membantu menjelaskan hasilnya. Setiap klaim AI wajib memiliki citation ke baris log asli, sehingga investigator dapat memeriksa kembali semua pernyataan.

### 12. Status proyek secara jujur

TraceLens sudah kuat untuk MVP, demo, penelitian, dan staging terbatas. Sebelum deployment production, masih perlu perbaikan migration database, concurrency worker, dependency security, login rate limiting, integration test, dan backup evidence.

### 13. Penutup

> Tujuan TraceLens bukan membuat AI terdengar paling yakin. Tujuannya adalah membuat setiap pernyataan AI dapat diperiksa kembali dari bukti asli.
