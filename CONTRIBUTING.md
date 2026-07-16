# Contributing

1. Create a focused branch and keep changes scoped to one concern.
2. Add or update tests for parser, detection, security, schema, or report behavior.
3. Run `scripts/validate.ps1` before opening a pull request.
4. Describe user impact, security impact, migration/rollback, and evidence of testing in the PR.
5. Never commit credentials, real sensitive logs, generated evidence, `.env`, database dumps, or investigation reports.

Database changes require a forward and downgrade Alembic migration. Detection changes require a golden-set case and must report precision/recall impact. UI changes must include loading, empty, error, long-content, keyboard and responsive checks.

Security-sensitive changes require two-person review. Findings waived by security tooling require an owner, rationale, compensating control, and expiry date.
