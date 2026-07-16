# Release Process

## Versioning

The project intends to use Semantic Versioning (`MAJOR.MINOR.PATCH`) after the first tagged release. Pre-stable releases may use `0.x.y` and prerelease suffixes such as `-alpha.1`.

## Release candidate checklist

### Engineering

- [ ] Required CI checks pass on the candidate commit.
- [ ] Database migrations include forward and downgrade paths.
- [ ] Evaluation and detection quality gates pass.
- [ ] Critical workflow and failure-path tests pass.
- [ ] Dependency and container scans have no unapproved critical/high findings.

### Security and evidence

- [ ] Secret scan passes.
- [ ] Threat model reflects material changes.
- [ ] Case isolation and evidence-integrity tests pass.
- [ ] Security waivers have owner, expiry, and compensating controls.

### Operations

- [ ] Backup and restore are rehearsed for production candidates.
- [ ] Metrics, alerts, SLOs, capacity, and runbooks are reviewed.
- [ ] Migration, rollback, and recovery instructions are documented.
- [ ] Named operator and escalation ownership is recorded.

### Product and documentation

- [ ] Acceptance criteria and known limitations are documented.
- [ ] README, configuration examples, support guidance, and changelog are current.
- [ ] Go/no-go approvers record the decision.

## Publish

1. Freeze the release candidate commit.
2. Complete the checklist and record waivers.
3. Update `CHANGELOG.md` with the version and date.
4. Create an annotated tag.
5. Publish GitHub release notes with upgrade, migration, rollback, and known limitations.
6. Monitor for 48–72 hours of release hypercare.
7. Complete a retrospective within two weeks for major releases.

No release should be described as production-ready solely because containers start successfully.
