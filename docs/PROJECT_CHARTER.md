# TraceLens Project Charter

## Objective

Deliver an evidence-grounded security-log investigation platform that reduces analyst effort while preserving deterministic processing, evidence provenance, and human accountability.

## Measurable outcomes

1. Every displayed substantive AI claim cites evidence owned by the active case.
2. Supported log formats produce reproducible normalized events and timelines.
3. Security and quality CI passes before a release candidate is approved.
4. Production candidates meet documented readiness, backup, monitoring, and rollback gates.

## Scope

### In scope

- Batch upload and analysis of supported security logs.
- Case management, investigation workflow, findings, timelines, and reports.
- Deterministic correlation, detection, risk scoring, and provenance.
- GitHub Models-assisted investigation through constrained read-only tools.
- Containerized deployment, monitoring baseline, tests, and runbooks.

### Out of scope for the current phase

- Autonomous containment or remediation.
- Real-time SIEM ingestion and high-availability multi-region operation.
- Native EVTX/PCAP processing.
- Formal regulatory certification or legal-grade chain of custody.
- Enterprise identity federation and commercial SLA support.

## Workstreams and DRIs

| Workstream | DRI | Responsibilities |
|---|---|---|
| Product and program | Repository owner (`@davidlimss`) | Scope, milestones, prioritization, go/no-go |
| Backend and evidence | Repository owner / assigned maintainer | API, parsers, integrity, data model |
| AI assurance | Assigned maintainer | Tools, prompts, claim verification, evaluations |
| Frontend and UX | Assigned maintainer | Investigation workflow and accessibility |
| Security and operations | Assigned reviewer | Threat model, CI, deployment, monitoring, runbooks |

Named maintainers should replace generic roles as the team grows.

## Delivery phases

| Phase | Exit gate |
|---|---|
| Discover | Scope, architecture, threats, and success measures approved |
| Build | Core workflows integrated with automated tests |
| Harden | Security, performance, backup, restore, and failure tests pass |
| Release candidate | Documentation, changelog, migration, rollback, and approval complete |
| Steady state | Ownership, support, monitoring, and retrospective established |

## Success metrics

- Claim citation validity: 100% for displayed claims.
- Critical/high unresolved security findings at release: 0 unless explicitly time-bound and waived.
- Required CI checks passing on the release commit: 100%.
- Backup/restore rehearsal completed before production designation.
- Detection evaluation changes report precision, recall, and F1 impact.

## Governance cadence

- Review roadmap and RAID register at least once per milestone.
- Record material scope, architecture, security, and release decisions in the decision log.
- Conduct a named go/no-go review for production candidates.
