# TraceLens Production SLO

| User journey | SLI | Target | Window | Owner |
|---|---|---:|---:|---|
| API request | non-5xx responses / all responses | 99.9% | rolling 30 days | Platform/SRE |
| Interactive API latency | requests completed below 500 ms | 99% | rolling 30 days | Backend |
| Evidence ingestion | accepted jobs completed within 5 minutes | 99% | rolling 30 days | Detection Engineering |

Client errors (4xx), approved maintenance, and explicitly identified abusive traffic are excluded from the availability SLI. At 99.9%, the monthly error budget is approximately 43.8 minutes.

Policy: below 50% budget consumption permits normal delivery; 50–80% pauses risky releases; above 80% freezes non-remediation releases; exhaustion requires incident review and reliability work.
