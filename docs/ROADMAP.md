# Roadmap

This roadmap communicates intent, not a contractual delivery commitment. Priorities may change when evidence, security risk, or dependencies change.

## Now — Alpha hardening

- Stabilize supported parsers and canonical schema.
- Keep Alembic schema checks, dependency readiness, and login protection
  enforced in every deployment.
- Expand regression coverage for evidence and cross-case isolation.
- Keep AI claim verification and provider-limit handling deterministic and observable.
- Establish repository governance, CI gates, runbooks, and release discipline.
- Complete backup/restore and production-readiness rehearsals.

## Next — Beta readiness

- Add end-to-end browser tests for critical investigation journeys.
- Add performance baselines for upload, parsing, timeline, and report generation.
- Improve user lifecycle, password rotation, and administrative controls.
- Add object-storage and malware-scanning integration options.
- Calibrate risk scoring against a larger labeled corpus.
- Publish tagged pre-releases with migration and rollback evidence.

## Later — Operational maturity

- Enterprise authentication options such as OIDC/SSO and MFA.
- Immutable evidence storage and stronger audit assurance.
- Streaming ingestion adapters and broader parser ecosystem.
- High-availability deployment patterns and disaster-recovery objectives.
- External security review and documented assurance package.

## Explicit non-goals

- Offensive automation.
- Autonomous containment without analyst approval.
- Unverifiable AI conclusions.
- Replacing a full SIEM in the current product phase.
