# Changelog

All notable user-facing changes will be documented here. The project follows
Semantic Versioning. A version listed as a candidate is not a published release
until the release checklist and tag have been completed.

## [Unreleased]

### Repository quality

- Added an MIT `LICENSE` and a review-response document that records scope,
  evidence, limitations, and follow-up actions.
- Linked reproducible test evidence and release governance from the README.
- Expanded CI to run all offline claim, VIGIL, Phase 2, adversarial, and
  detection evaluators in addition to the backend test suite.

### Added

- Professional repository governance, issue intake, pull-request controls, roadmap, RAID register, decision log, and release process.
- Production-oriented SOC investigation platform with deterministic parsing, evidence-grounded AI, formal reports, and operational documentation.
- Goal-aware VIGIL playbooks for authentication, web activity, execution/persistence, evidence integrity, and general investigations.
- `investigation-plan-v2` success contracts that expose expected observations, disconfirming-search requirements, and claim prerequisites to the bounded agent.
- `case-memory-v2` hydration across completed runs in the same case, restricted to curated operational summaries and local evidence IDs.
- Case-memory trust boundary: only completed runs with verified claims can hydrate a later run; abstained, failed, and provider-error runs are excluded.

### Security

- Secret-safe environment templates and ignored local configuration.
- Claim verification, case-scoped tools, upload validation, CSRF controls, audit records, and evidence integrity checks.
