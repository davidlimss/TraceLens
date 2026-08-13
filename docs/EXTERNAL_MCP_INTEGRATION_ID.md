# Integrasi MCP Eksternal TraceLens

TraceLens sekarang memiliki jalur evidence eksternal yang read-only untuk OpenSearch, Splunk, dan Wazuh. Jalur ini tidak menerima DSL OpenSearch atau SPL mentah dari model. Agent hanya mengirim filter terbatas; backend menerjemahkan filter, menjalankan query, lalu menyimpan snapshot hasil ke tabel `external_evidence`.

## Alur data

```text
Agent
  -> search_external_events(provider, filters)
  -> ExternalSourceManager
  -> OpenSearch / Splunk / Wazuh indexer (read-only)
  -> normalize hit
  -> hash raw payload + query
  -> external_evidence (immutable)
  -> evidence_id dikembalikan ke agent
  -> claim verification gate
```

Dengan cara ini, external event tidak langsung dianggap bukti. Bukti harus lebih dulu menjadi snapshot lokal dengan `evidence_id`, hash isi, hash query, provider, dan waktu pengambilan.

Jika `EXTERNAL_SOURCES_ENABLED=true` dan provider tersedia, agent memeriksa status source lalu memprioritaskan pencarian external telemetry. Upload lokal tetap dipakai sebagai fallback dan sumber konteks tambahan. Jika semua provider gagal, agent harus mencatat evidence gap; kegagalan koneksi bukan bukti bahwa tidak ada insiden.

## Konfigurasi

> Salin bagian external source dari `.env.example` ke `.env` dan isi hanya koneksi yang digunakan.

```dotenv
EXTERNAL_SOURCES_ENABLED=true
EXTERNAL_CASE_FIELD=tracelens.case_id
EXTERNAL_MAX_RESULTS=100

OPENSEARCH_URL=https://...
OPENSEARCH_INDEX=security-logs-*
OPENSEARCH_API_KEY=...

SPLUNK_URL=https://...:8089
SPLUNK_INDEX=security
SPLUNK_TOKEN=...

WAZUH_INDEXER_URL=https://...
WAZUH_INDEX=wazuh-alerts-*
WAZUH_USERNAME=...
WAZUH_PASSWORD=...
```

`EXTERNAL_CASE_FIELD` wajib tersedia pada data eksternal. Filter tersebut disisipkan oleh backend pada setiap query sehingga agent tidak dapat mencari data di luar case aktif. Jika data tidak memiliki field case, konektor sebaiknya tidak diaktifkan sebelum pipeline sumber menambahkan scope tersebut.

## Menjalankan MCP server

Server MCP private tersedia melalui stdio:

```bash
docker compose exec backend python -m app.mcp_server
```

Tool MCP yang disediakan:

- `list_external_sources`
- `search_external_events_mcp`
- `get_external_evidence_mcp`

Pada agent backend, `get_external_source_status` dan `search_external_events` memanggil server MCP private ini melalui in-process bridge (`MCP_EXTERNAL_IN_PROCESS=true` secara default). Jadi jalur external yang dipilih model benar-benar melewati MCP tool handler, bukan hanya fungsi HTTP provider langsung.

Untuk deployment production, jalankan sebagai proses private di belakang backend/orchestrator yang melakukan autentikasi dan authorization. Jangan membuka database atau credential provider melalui MCP generik.

## Provider

- OpenSearch memakai `POST /{index}/_search` dengan body query yang dibatasi. Lihat [OpenSearch Search API](https://docs.opensearch.org/latest/api-reference/search-apis/search/).
- Splunk memakai endpoint `services/search/jobs/export`; query SPL dibentuk backend dari filter allowlist.
- Wazuh memakai Wazuh Indexer dengan index `wazuh-alerts-*`; dokumentasi Wazuh menjelaskan alert disimpan dan dicari melalui indexer API. Lihat [Wazuh indexer use cases](https://documentation.wazuh.com/current/user-manual/indexer-api/use-case.html).

## Batasan keamanan

- Semua konektor read-only; tidak ada active response, block IP, restart agent, atau delete-by-query.
- Credential hanya dibaca dari environment backend dan tidak dikirim ke LLM.
- Raw payload tidak masuk ke audit log; yang dicatat adalah provider, count, dan query hash.
- Hasil dibatasi maksimal 100 hit per panggilan.
- Query provider memakai timeout dan tidak menerima DSL/SPL bebas.
- Cross-case ditolak melalui `case_id` aktif dan exact external case field.
- Jika source tidak mendukung case scope, jangan mengaktifkannya untuk investigator multi-case.
- Ketersediaan provider adalah dependency eksternal; kegagalan koneksi harus diperlakukan sebagai evidence gap, bukan sebagai bukti tidak ada serangan.

## Pengujian

Unit test konektor menggunakan HTTP mock, tidak memerlukan server OpenSearch/Splunk/Wazuh:

```bash
cd backend
pytest -q tests/test_external_sources.py
```

Test wajib mencakup query case scope, normalisasi hit, credential failure, unsupported filter, limit, dan tidak adanya raw DSL/SPL injection.
