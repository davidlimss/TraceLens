# Contributing to TraceLens

Thank you for improving TraceLens. Contributions must preserve evidence traceability, case isolation, deterministic processing, and honest AI output.

## Workflow

1. Search existing issues and open an issue for significant changes.
2. Create a focused branch using `feat/`, `fix/`, `docs/`, `security/`, or `chore/`.
3. Keep each pull request scoped to one concern.
4. Add or update tests and documentation.
5. Run `scripts/validate.ps1` before opening a pull request.
6. Complete every applicable section of the pull-request template.
7. Resolve CI failures and reviewer feedback before merge.

## Definition of done

- Acceptance criteria are met and demonstrated.
- Tests cover the changed behavior and meaningful failure paths.
- Documentation and configuration examples are current.
- Security, privacy, evidence-integrity, and migration impacts are documented.
- Rollback or recovery is described for operational changes.
- No credentials, personal data, real sensitive logs, `.env`, database dumps, or investigation reports are committed.
- The changelog is updated for user-visible changes.

## Change-specific requirements

- **Database:** include forward and downgrade Alembic migrations.
- **Detection:** add a golden-set case and report precision/recall impact.
- **Parser:** include valid, malformed, missing-field, and ambiguity tests.
- **AI:** include claim-verification and insufficient-evidence regression tests.
- **UI:** validate loading, empty, error, long-content, keyboard, and responsive states.
- **Operations:** update runbooks, metrics, alerts, and rollback instructions.

Security-sensitive changes require two-person review. Security-tooling waivers require an owner, rationale, compensating control, and expiry date.

## Commit and review guidance

Use concise imperative commit messages. Reviewers should prioritize correctness, security boundaries, evidence provenance, tests, operability, and maintainability over stylistic preference.

See [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md), [SECURITY.md](SECURITY.md), and [SUPPORT.md](SUPPORT.md).
