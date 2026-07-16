# Menambah Parser Format Baru

Format baru berada di luar scope MVP saat ini dan harus memperoleh persetujuan eksplisit terlebih dahulu. Setelah disetujui, parser tetap harus deterministik—tidak boleh memanggil LLM.

## Kontrak parser

1. Tambahkan modul di `backend/app/parsers/` yang menerima satu raw line dan mengembalikan `ParsedEvent`.
2. Gunakan regex/parser JSON yang bounded dan fail dengan `ParsingError` yang jelas untuk input malformed.
3. Jangan mengubah raw line. Worker akan menyimpannya sebagai `raw_log` bersama nomor baris asli.
4. Normalisasikan timestamp secara deterministik. Catat setiap asumsi pada `timestamp_assumptions` dan turunkan `timestamp_confidence`.
5. Jangan menghasilkan entity atau field yang tidak ada pada input tanpa menandainya sebagai asumsi.
6. Daftarkan parser dalam `backend/app/parsers/registry.py`.
7. Tambahkan signature content-based ke `backend/app/parsers/detector.py`; jangan mengandalkan extension.
8. Tambahkan extension/MIME yang benar-benar diperlukan ke allowlist upload. Content detector tetap menjadi validator utama.
9. Naikkan `PARSER_VERSION` di `backend/app/tasks.py` agar transformasi tercatat pada audit.

## Test wajib

- Minimal satu log valid untuk setiap variasi utama.
- Field opsional hilang.
- Timestamp invalid atau tanpa timezone/tahun.
- Baris malformed menghasilkan `ParsingError`, bukan crash atau silent skip.
- File besar/multi-line untuk mendeteksi regresi performa dasar.
- Format detector membedakan format baru dari Linux syslog, web access, JSON, dan CSV yang sudah ada.
- Verifikasi `raw_log` dan `raw_line_number` tetap identik dengan input.

Jalankan:

```powershell
cd backend
pytest
```
