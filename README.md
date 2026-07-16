# TraceLens AI

Evidence-grounded, agentic security-log investigation for defensive operations.

[![Security and Quality](https://github.com/davidlimss/TraceLens/actions/workflows/security-quality.yml/badge.svg)](https://github.com/davidlimss/TraceLens/actions/workflows/security-quality.yml)
[![Project Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#project-status)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](backend/pyproject.toml)
[![Node.js 22](https://img.shields.io/badge/node-22-339933.svg)](frontend/package.json)
[![License: Not declared](https://img.shields.io/badge/license-not%20declared-lightgrey.svg)](#license)

TraceLens converts heterogeneous raw logs into normalized events, deterministic timelines, correlated entities, findings, risk scores, and AI-assisted conclusions that remain traceable to original evidence.

> TraceLens is an investigation aid, not an autonomous incident-response authority. Human review remains required for high-impact decisions.

## Project status

TraceLens is currently an **alpha-stage research and engineering project**. The repository includes a production-oriented baseline, but it is not yet certified for unattended production use. Release readiness is governed through documented quality, security, operations, and evidence-integrity gates.

| Area | Current state | Source of truth |
|---|---|---|
| Product scope | Active development | [Project charter](docs/PROJECT_CHARTER.md) |
| Delivery plan | Milestone-based roadmap | [Roadmap](docs/ROADMAP.md) |
| Risks and decisions | Reviewed as repository changes | [RAID register](docs/RAID.md) and [decision log](docs/DECISIONS.md) |
| Quality | Automated CI and local validation | [Security and Quality workflow](.github/workflows/security-quality.yml) |
| Production readiness | Conditional; gaps remain | [Production readiness](docs/PRODUCTION_READINESS.md) |
| Releases | SemVer-oriented documented process | [Release process](docs/RELEASE_PROCESS.md) |

## Core principles

- Parsing, timestamp normalization, ordering, correlation, detection, and risk scoring are deterministic.
- The LLM selects read-only investigation tools and interprets structured evidence.
- Every accepted AI claim must cite valid evidence from the active case.
- Claims are explicitly classified as `fact`, `inference`, or `hypothesis`.
- Unsupported claims are removed by the backend before display.
- Raw evidence retains its source line number and is protected against mutation.
- Insufficient evidence produces an explicit insufficient-evidence response.

## Capabilities

### Investigation workspace

- Case-based access control and membership.
- Evidence upload with integrity metadata and SHA-256 hashes.
- Asynchronous parsing through Redis and Celery.
- Deterministic cross-file timelines.
- Searchable event explorer with surrounding context.
- Entity correlation across IP addresses, users, sessions, hosts, and processes.
- Detection findings with MITRE ATT&CK mappings.
- Explainable risk scoring with versioned component breakdowns.
- Evidence-grounded AI investigator with clickable citations.
- Formal Markdown and monochrome PDF reports.
- Audit records for security-sensitive operations.

### Supported log formats

| Format | Typical input | Coverage |
|---|---|---|
| Linux authentication | `auth.log`, `secure` | SSH, authentication, sudo, users, and source IPs |
| Web access | Apache/Nginx combined logs | Request method, path, status, client IP, and user agent |
| Generic application CSV | Header plus one record per line | Common timestamp, level, message, user, and IP aliases |
| Generic JSON/JSONL | Object per line | Structured application and security events |
| Cowrie JSON | `cowrie.json` | Honeypot login, commands, sessions, IPs, and users |
| Windows/Sysmon JSON | Exported JSON | Authentication, process, file, and service events |
| AWS CloudTrail JSONL | Event per line | Identity, source IP, API activity, and error outcomes |
| Suricata EVE JSON | `eve.json` | Network alerts, endpoints, protocol, and severity |
| Logfmt | Go and Ollama-style logs | Timestamp, level, service, message, session, and endpoint |
| Plain text | UTF-8 text logs | Conservative fallback parsing |

Format detection is content-based. A file extension is only one validation signal and does not select a parser by itself.

Binary EVTX, PCAP, compressed archives, live SIEM streaming, and real-time tailing are not natively supported. Export those sources to JSON, JSONL, CSV, or text first.

## Architecture

```text
Browser
  |
  v
Next.js frontend :3001
  |
  v
FastAPI backend :8002 ----> PostgreSQL
  |                         cases, events, findings,
  |                         users, sessions, and audit
  |
  +----> Redis ----> Celery worker / Celery Beat
  |                  parsing, analysis, integrity jobs
  |
  +----> Evidence volume
  |      immutable source files and hashes
  |
  +----> GitHub Models
         tool selection and evidence interpretation
```

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| API | FastAPI, Pydantic, SQLAlchemy |
| Database | PostgreSQL 16 |
| Queue | Redis 7, Celery |
| Scheduler | Celery Beat |
| LLM provider | GitHub Models |
| Deployment | Docker Compose |
| Monitoring | Prometheus metrics and SLO rules |

See [ARCHITECTURE.md](ARCHITECTURE.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed design decisions.

## Repository layout

```text
TraceLens/
├── backend/                 FastAPI API, parsers, detection engine, and tests
│   ├── app/
│   │   ├── parsers/         Content detection and canonical parsers
│   │   ├── agent_tools.py   Read-only investigation tools
│   │   ├── llm_gateway.py   Provider controls and context compaction
│   │   ├── claim_verifier.py
│   │   ├── engine.py        Correlation, detection, and risk scoring
│   │   └── security.py      Upload validation and rate limiting
│   ├── alembic/             Database migrations
│   ├── evals/               Agent and detection evaluation harnesses
│   └── tests/
├── frontend/                Next.js investigation console
├── monitoring/              Prometheus and SLO configuration
├── scripts/                 Validation, backup, restore, and load smoke tests
├── samples/                 Safe demonstration logs
├── docs/                    Design, readiness, threat model, and runbooks
├── docker-compose.yml       Development stack
└── docker-compose.prod.yml  Hardened production baseline
```

## Quick start

### Prerequisites

- Docker Desktop with Docker Compose.
- Git.
- A GitHub Models token with permission to use the configured model.
- At least 4 GB of available memory is recommended.

### 1. Clone and configure

```bash
git clone https://github.com/davidlimss/TraceLens.git
cd TraceLens
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Set secure values in `.env`, especially:

```dotenv
POSTGRES_PASSWORD=replace-with-a-long-random-password
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=replace-with-a-long-random-password
GITHUB_MODELS_TOKEN=your-github-models-token
GITHUB_MODELS_MODEL=openai/gpt-4.1-mini
```

Never commit `.env`. It is excluded by `.gitignore`.

### 2. Start the stack

```bash
docker compose up -d --build
docker compose ps
```

Open:

- Frontend: http://localhost:3001
- Backend API: http://localhost:8002
- API documentation: http://localhost:8002/docs
- Health: http://localhost:8002/health
- Readiness: http://localhost:8002/ready

Follow service logs with:

```bash
docker compose logs -f backend worker frontend
```

Stop without deleting data:

```bash
docker compose down
```

Do not use `docker compose down -v` unless permanent removal of the local database and evidence volumes is intended.

## Investigation workflow

1. Sign in using the bootstrap account configured in `.env`.
2. Create a case from the home page.
3. Upload one or more supported log files.
4. Select parsing mode:
   - `strict`: reject the file when malformed records are encountered.
   - `quarantine`: preserve malformed lines separately while processing valid events.
5. Monitor parsing and analysis status.
6. Review dashboard summaries, findings, timeline, and event details.
7. Ask the AI investigator focused questions.
8. Verify every claim through its evidence citation.
9. Review limitations and required additional evidence.
10. Export the formal report.

Example questions:

```text
What happened in this case?
Which source IPs generated repeated authentication failures?
Build a concise incident timeline and cite the supporting evidence.
Which findings require immediate analyst review?
What additional telemetry is needed to confirm the leading hypothesis?
```

## Deterministic analysis pipeline

```text
Upload
  -> content validation
  -> SHA-256 hashing
  -> format detection
  -> parser selection
  -> canonical event normalization
  -> timestamp provenance
  -> stable ordering
  -> entity correlation
  -> detection rules
  -> risk scoring
  -> findings and report data
```

Canonical events preserve the original timestamp, normalized timestamp, timezone assumptions, source identity, entities, raw line number, parser version, confidence, and tags.

Timeline ordering uses deterministic tie-breakers so identical timestamps produce reproducible output.

## AI investigator and claim verification

The LLM does not query the database directly. It can only call registered, read-only tools scoped to the active case.

Expected model output is structured:

```json
{
  "answer": "A response reconstructed from verified claims.",
  "claims": [
    {
      "claim_id": "claim-001",
      "text": "Repeated failed authentication events targeted the root account.",
      "status": "fact",
      "supporting_evidence_ids": ["event-uuid"],
      "contradicting_evidence_ids": [],
      "entities": {"username": "root"},
      "confidence": 0.95,
      "reasoning_summary": null,
      "limitations": [],
      "required_additional_evidence": []
    }
  ]
}
```

The backend independently verifies:

- claim status;
- evidence existence and active-case ownership;
- minimum support for inferences and hypotheses;
- required reasoning, limitations, and additional-evidence fields;
- entity, outcome, and basic count consistency;
- overclaims involving compromise, attribution, malware, or data theft.

Provider context is bounded. Oversized tool history is compacted and retried automatically when GitHub Models returns HTTP 413.

## Security controls

- PBKDF2-SHA256 password hashing with per-password salt.
- Random session tokens stored as hashes.
- HttpOnly session cookies and CSRF protection.
- Role and case-membership authorization.
- Child resources scoped by `case_id`.
- Upload size, filename, extension, MIME, UTF-8, and content validation.
- Path traversal and absolute-path rejection.
- UUID-based evidence filenames.
- Raw-event ORM guard and PostgreSQL immutability trigger.
- Secret redaction for PATs, bearer tokens, JWTs, private keys, passwords, and cookies.
- External raw-log sharing disabled by default.
- Agent timeout, tool-call budget, repetition guard, and no-progress guard.
- Audit events for authentication, uploads, agent activity, integrity checks, and exports.

Read [SECURITY.md](SECURITY.md) and [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) before exposing the service outside a trusted development environment.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `BACKEND_PORT` | `8002` | Backend port on the host |
| `FRONTEND_PORT` | `3001` | Frontend port on the host |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8002` | Browser-visible API URL |
| `CORS_ORIGINS` | `http://localhost:3001` | Allowed frontend origins |
| `SERVER_TIMEZONE` | `Asia/Jakarta` | Fallback timezone for incomplete logs |
| `GITHUB_MODELS_ENDPOINT` | `https://models.github.ai/inference` | Provider endpoint |
| `GITHUB_MODELS_MODEL` | `openai/gpt-4.1-mini` | Tool-capable investigation model |
| `LLM_MAX_TOOL_RESULT_CHARACTERS` | `8000` | Maximum result context per tool |
| `LLM_MAX_OUTPUT_TOKENS` | `2048` | Normal provider output budget |
| `ALLOW_RAW_LOG_TO_EXTERNAL_PROVIDER` | `false` | External raw-evidence policy |

See [.env.example](.env.example) for the complete list.

## Validation and testing

Run backend tests:

```bash
pytest -q backend/tests
```

Run the complete validation script on Windows:

```powershell
.\scripts\validate.ps1
```

Run offline evaluation harnesses:

```bash
python backend/evals/run_eval.py
python backend/evals/run_detection_eval.py
```

The CI workflow performs security and quality checks for pushes and pull requests.

## Production baseline

The production Compose file provides a hardened baseline:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Before production use:

- terminate TLS at a trusted reverse proxy or ingress;
- use a managed secret store;
- rotate all bootstrap and provider credentials;
- restrict network exposure;
- configure immutable backups and evidence retention;
- integrate centralized monitoring and alerting;
- review SLOs and launch gates;
- perform an independent security assessment;
- document incident-response ownership.

See [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md), [docs/SLO.md](docs/SLO.md), and [docs/runbooks/API_DEGRADATION.md](docs/runbooks/API_DEGRADATION.md).

## Troubleshooting

### `Failed to fetch`

Verify backend readiness and frontend API configuration:

```powershell
Invoke-RestMethod http://localhost:8002/ready
docker compose ps
docker compose logs --tail 100 backend frontend
```

Rebuild if the browser still references an outdated API URL:

```bash
docker compose up -d --build --force-recreate backend frontend
```

Then refresh the browser with `Ctrl+F5`.

### GitHub Models authentication error

- Confirm the token is active and permitted to use GitHub Models.
- Confirm `GITHUB_MODELS_MODEL` names a tool/function-calling model.
- Recreate the backend after changing `.env`:

```bash
docker compose up -d --force-recreate backend worker
```

Never print or commit the token while troubleshooting.

### Parsing job remains queued

```bash
docker compose ps redis worker
docker compose logs --tail 200 worker redis
```

### Reset local development data

The following command permanently deletes the local database and evidence volumes:

```bash
docker compose down -v
```

Use it only when all local development data may be discarded.

## Known limitations

- TraceLens is not a SIEM and does not provide native real-time ingestion.
- Native EVTX, PCAP, compressed archives, and external threat-intelligence enrichment are not included.
- MFA, SSO, self-service password recovery, and full identity lifecycle management are not yet implemented.
- Evidence storage and database audit records are not WORM or cryptographically signed.
- TLS termination, malware scanning, immutable object storage, and external secret management require deployment integration.
- PDF timelines are intentionally bounded to control report size and generation time.
- Risk scoring is heuristic and has not been calibrated against every production environment.
- Valid evidence citations prove traceability, not the absolute correctness of an interpretation.

Do not use TraceLens as the sole basis for legal conclusions, attacker attribution, or high-impact incident response without qualified human validation.

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Security policy](SECURITY.md)
- [Contribution guide](CONTRIBUTING.md)
- [Parser development](docs/ADDING_A_PARSER.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Production readiness](docs/PRODUCTION_READINESS.md)
- [Build validation report](docs/BUILD_VALIDATION_REPORT.md)
- [Implementation report](docs/IMPLEMENTATION_REPORT.md)
- [Project charter](docs/PROJECT_CHARTER.md)
- [Roadmap](docs/ROADMAP.md)
- [RAID register](docs/RAID.md)
- [Decision log](docs/DECISIONS.md)
- [Release process](docs/RELEASE_PROCESS.md)
- [Changelog](CHANGELOG.md)
- [Support guide](SUPPORT.md)

## Contributing

Contributions are welcome. Review [CONTRIBUTING.md](CONTRIBUTING.md), add tests for behavioral changes, and preserve evidence traceability and case isolation.

## License

No open-source license has been declared yet. Unless a license is added, all rights remain with the repository owner.
