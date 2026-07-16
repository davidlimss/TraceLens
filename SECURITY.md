# Security Policy

Do not disclose suspected vulnerabilities through public issues. Send a private report to the repository security contact with affected version, impact, reproduction steps, and suggested mitigation. Do not include real credentials or third-party personal data.

Production deployments must replace default credentials, use TLS and a managed secret store, restrict database/Redis/metrics to private networks, encrypt evidence at rest, and configure immutable audit retention. See `docs/PRODUCTION_READINESS.md`.

The AI output is advisory. Analysts must verify citations and evidence before containment, escalation, attribution, or legal action.
