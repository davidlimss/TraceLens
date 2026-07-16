# Decision Log

| ID | Date | Decision | Rationale | Owner | Status |
|---|---|---|---|---|---|
| D-001 | 2026-07-16 | Use deterministic code for parsing, ordering, correlation, detection, and risk scoring | Reproducibility and auditability must not depend on model behavior | Repository owner | Accepted |
| D-002 | 2026-07-16 | Require backend claim verification before displaying AI conclusions | Provider output is untrusted and may overclaim or cite invalid evidence | Repository owner | Accepted |
| D-003 | 2026-07-16 | Keep raw-log sharing with external providers disabled by default | Minimize data exposure and preserve operator control | Repository owner | Accepted |
| D-004 | 2026-07-16 | Treat Docker Compose as a production-oriented baseline, not proof of production certification | HA, immutable storage, enterprise identity, and external assurance remain gaps | Repository owner | Accepted |
| D-005 | 2026-07-16 | Do not declare an open-source license without an explicit owner decision | Licensing is a legal and governance choice | Repository owner | Accepted |

Add a new entry for material product, architecture, security, data-handling, or release decisions. Do not rewrite historical decisions; supersede them with a new entry.
