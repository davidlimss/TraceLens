# Dataset demo TraceLens

Seluruh file di folder ini sintetis dan aman digunakan untuk demonstrasi.

- `demo-bruteforce.csv`: lima login gagal diikuti login berhasil dari IP yang sama.
- `demo-linux-auth.log`: SSH brute-force, login root berhasil, lalu aktivitas sudo.
- `demo-web-access.log`: percobaan login web, akses `/admin`, dan path traversal.
- `demo-application.jsonl`: password recovery, kegagalan MFA, MFA dinonaktifkan, dan token dibuat.
- `sample-app.csv`: contoh CSV minimal.

Untuk demo paling lengkap, unggah keempat file `demo-*` ke case yang sama menggunakan mode
`strict`. Timestamp sengaja berada pada 16 Juli 2026 agar timeline lintas file mudah dibaca.

Pertanyaan AI yang disarankan:

1. Apa rangkaian kejadian paling penting pada case ini?
2. IP mana yang muncul pada login gagal dan perubahan keamanan akun?
3. Apakah ada login berhasil setelah kegagalan berulang?
4. Bukti apa yang mendukung dugaan brute-force?
5. Apakah bukti cukup untuk menyatakan sistem telah dikompromikan?
