# RAID Register

RAID means Risks, Actions, Issues, and Decisions. Update this file when an item affects scope, critical path, security posture, or release readiness.

## Open risks

| ID | Risk | Likelihood | Impact | Mitigation | Trigger | Owner | Status |
|---|---|---:|---:|---|---|---|---|
| R-001 | Heuristic risk scoring may not generalize to every environment | Medium | High | Calibrate with labeled datasets and show component breakdowns | Material false-positive/negative trend | AI assurance DRI | Open |
| R-002 | Local evidence storage is not immutable/WORM | Medium | High | Restrict access; plan immutable object storage | Production designation | Security DRI | Open |
| R-003 | External LLM availability or context limits degrade AI assistance | Medium | Medium | Bounded tools, compaction, retries, deterministic non-AI workflow | Elevated provider errors | Backend DRI | Mitigated |
| R-004 | Single-instance Compose deployment lacks HA | High | Medium | Document limitation and design HA target architecture | Multi-user production demand | Operations DRI | Open |

## Actions

| ID | Action | Owner | Target milestone | Status | Evidence of completion |
|---|---|---|---|---|---|
| A-001 | Add critical-path browser E2E tests | Frontend DRI | Beta | Planned | CI test results |
| A-002 | Rehearse backup and restore | Operations DRI | Release candidate | Planned | Signed rehearsal record |
| A-003 | Select and declare a repository license | Repository owner | Before public stable release | Open | `LICENSE` file |

## Active issues

| ID | Issue | Impact | Owner | Resolution target | Status |
|---|---|---|---|---|---|
| I-001 | No formal tagged release exists | Users cannot reference a stable version | Repository owner | Alpha release | Open |

## Decisions

Material decisions are summarized in [DECISIONS.md](DECISIONS.md). Closed RAID entries should retain evidence and closure date.
