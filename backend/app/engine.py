from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
import re
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Correlation, Event, Finding

TIMELINE_SORT_VERSION = "timeline-v1.2"
RISK_VERSION = "risk-v1.1"
RISK_THRESHOLD_VERSION = "threshold-v1"
CORRELATION_CAP = 20


@dataclass(frozen=True)
class RiskResult:
    score: float
    breakdown: dict


@dataclass(frozen=True)
class ConfidenceResult:
    score: float
    breakdown: dict


def calculate_confidence(events: list[Event]) -> ConfidenceResult:
    if not events:
        return ConfidenceResult(0.0, {"reason": "no evidence"})
    parser = sum(event.parser_confidence or 0 for event in events) / len(events)
    timestamp = sum(event.timestamp_confidence or 0 for event in events) / len(events)
    support = min(len(events) / 5, 1.0)
    sources = min(len({event.source_type for event in events}) / 2, 1.0)
    components = {"parser_quality": round(parser, 3), "timestamp_quality": round(timestamp, 3),
                  "evidence_support": round(support, 3), "source_diversity": round(sources, 3)}
    score = round(parser*.40 + timestamp*.20 + support*.25 + sources*.15, 2)
    level = "high" if score >= .8 else "medium" if score >= .55 else "low"
    return ConfidenceResult(score, {"formula": "parser*.40 + timestamp*.20 + support*.25 + sources*.15",
                                    "confidence_level": level, "components": components})


def make_finding(*, events: list[Event], finding_type: str, title: str, description: str,
                 entity_type: str, entity_value: str, risk: RiskResult, mitre_technique: str,
                 mitre_tactic: str, false_positives: list[str], queries: list[str]) -> Finding:
    confidence = calculate_confidence(events)
    return Finding(case_id=events[0].case_id, finding_type=finding_type, title=title, description=description,
                   entity_type=entity_type, entity_value=entity_value,
                   first_seen=min(event.timestamp_normalized for event in events if event.timestamp_normalized),
                   last_seen=max(event.timestamp_normalized for event in events if event.timestamp_normalized),
                   evidence_ids=[str(event.event_id) for event in events], risk_score=risk.score,
                   risk_breakdown=risk.breakdown, confidence_score=confidence.score,
                   confidence_breakdown=confidence.breakdown, mitre_technique=mitre_technique,
                   mitre_tactic=mitre_tactic, false_positive_considerations=false_positives,
                   recommended_queries=queries)


def timeline_sort_key(event: Event) -> tuple:
    """Deterministic ordering; evidence id makes equal line numbers stable across files."""
    return (
        event.timestamp_normalized is None,
        event.timestamp_normalized,
        -(event.timestamp_confidence or 0.0),
        str(event.evidence_file_id or event.external_evidence_id or ""),
        event.raw_line_number is None,
        event.raw_line_number if event.raw_line_number is not None else 0,
        str(event.event_id),
    )


def timeline_order_by() -> tuple:
    return (
        Event.timestamp_normalized.asc().nullslast(),
        Event.timestamp_confidence.desc(),
        Event.evidence_file_id.asc().nullslast(),
        Event.external_evidence_id.asc().nullslast(),
        Event.raw_line_number.asc().nullslast(),
        Event.event_id.asc(),
    )


def calculate_risk(
    *, severity_weight: float, frequency_score: float, privilege_weight: float,
    correlation_count: int, novelty_score: float,
) -> RiskResult:
    def unit(value: float) -> float:
        return max(0.0, min(float(value) / 100.0 if value > 1 else float(value), 1.0))

    severity_score = unit(severity_weight)
    normalized_frequency = unit(frequency_score)
    privilege_score = unit(privilege_weight)
    normalized_novelty = unit(novelty_score)
    correlation_score = min(max(correlation_count, 0) / CORRELATION_CAP, 1.0)
    components = {
        "severity": {"value": severity_score, "weight": 0.30, "contribution": severity_score * 0.30},
        "frequency": {"value": normalized_frequency, "weight": 0.20, "contribution": normalized_frequency * 0.20},
        "privilege": {"value": privilege_score, "weight": 0.25, "contribution": privilege_score * 0.25},
        "correlation": {"value": correlation_score, "raw_count": correlation_count, "cap": CORRELATION_CAP,
                        "weight": 0.15, "contribution": correlation_score * 0.15},
        "novelty": {"value": normalized_novelty, "weight": 0.10, "contribution": normalized_novelty * 0.10},
    }
    score = round(sum(item["contribution"] for item in components.values()), 2)
    level = "critical" if score >= 0.85 else "high" if score >= 0.70 else "medium" if score >= 0.40 else "low"
    return RiskResult(score=score, breakdown={
        "formula": "severity*0.3 + frequency*0.2 + privilege*0.25 + correlation*0.15 + novelty*0.1",
        "risk_version": RISK_VERSION, "threshold_version": RISK_THRESHOLD_VERSION,
        "risk_level": level, "calibration_status": "uncalibrated", "components": components,
    })


def build_correlations(events: Iterable[Event], window_minutes: int) -> list[Correlation]:
    window = timedelta(minutes=window_minutes)
    grouped: dict[tuple[str, str], list[Event]] = defaultdict(list)
    for event in events:
        session_namespace = (f"{event.host or '-'}|{event.source_type}|{event.session_id}"
                             if event.session_id else None)
        for entity_type, value in (("source_ip", event.source_ip), ("username", event.username),
                                   ("session", session_namespace)):
            if value and event.timestamp_normalized:
                grouped[(entity_type, value)].append(event)
    correlations: list[Correlation] = []
    seen_pairs: set[tuple[object, object, str]] = set()
    for (entity_type, value), related in grouped.items():
        ordered = sorted(related, key=timeline_sort_key)
        # Linking each event to its nearest predecessor preserves an explicit
        # evidence chain without generating O(n^2) pairs for dense log bursts.
        for previous, event in zip(ordered, ordered[1:]):
            delta = event.timestamp_normalized - previous.timestamp_normalized
            if delta <= window:
                pair_key = (previous.event_id, event.event_id, entity_type)
                # Duplicate event rows can occur when multiple ingestion jobs
                # are retried or a case is rebuilt concurrently.  Keep the
                # correlation deterministic and compatible with the database
                # uniqueness constraint instead of emitting duplicate inserts.
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                minutes = round(delta.total_seconds() / 60, 2)
                correlations.append(Correlation(
                    case_id=event.case_id, event_id=previous.event_id, related_event_id=event.event_id,
                    entity_type=entity_type, entity_value=value,
                    correlation_reason=f"shared {entity_type} within {window_minutes} minutes ({minutes} minutes apart)",
                    time_delta_seconds=int(delta.total_seconds()),
                ))
    return correlations


def _correlation_counts(correlations: Iterable[Correlation]) -> dict:
    counts = defaultdict(int)
    for correlation in correlations:
        counts[correlation.event_id] += 1
        counts[correlation.related_event_id] += 1
    return counts


def detect_auth_findings(
    events: Iterable[Event], correlations: Iterable[Correlation], *, threshold: int, window_minutes: int,
) -> list[Finding]:
    auth = [event for event in sorted(events, key=timeline_sort_key)
            if event.timestamp_normalized and event.event_action == "login" and event.source_ip]
    by_ip: dict[str, list[Event]] = defaultdict(list)
    for event in auth:
        by_ip[event.source_ip].append(event)
    counts = _correlation_counts(correlations)
    findings: list[Finding] = []
    window = timedelta(minutes=window_minutes)
    for source_ip, ip_events in by_ip.items():
        failures = [event for event in ip_events if event.event_outcome == "failure"]
        qualifying: list[Event] = []
        for failure in failures:
            current = [item for item in failures if timedelta(0) <= failure.timestamp_normalized - item.timestamp_normalized <= window]
            if len(current) >= threshold:
                qualifying = current
                break
        if not qualifying:
            continue
        correlation_count = sum(counts[event.event_id] for event in qualifying)
        risk = calculate_risk(severity_weight=90, frequency_score=100, privilege_weight=0,
                              correlation_count=correlation_count, novelty_score=100)
        findings.append(make_finding(events=qualifying, finding_type="brute_force",
            title="Possible brute-force authentication",
            description=f"{len(qualifying)} failed logins from {source_ip} within {window_minutes} minutes",
            entity_type="source_ip", entity_value=source_ip, risk=risk, mitre_technique="T1110.001",
            mitre_tactic="Credential Access",
            false_positives=["Authorized vulnerability scanner", "Shared NAT or corporate proxy", "User mistyping a password"],
            queries=[f"Review all authentication events from {source_ip}", "Check whether any failure was followed by success"]))
        last_failure = qualifying[-1]
        successes = [event for event in ip_events if event.event_outcome == "success" and
                     timedelta(0) <= event.timestamp_normalized - last_failure.timestamp_normalized <= window]
        if successes:
            success = successes[0]
            evidence = [*qualifying, success]
            privileged = success.username in {"root", "administrator", "admin"}
            correlation_count = sum(counts[event.event_id] for event in evidence)
            risk = calculate_risk(severity_weight=100, frequency_score=100,
                                  privilege_weight=100 if privileged else 60,
                                  correlation_count=correlation_count, novelty_score=100)
            findings.append(make_finding(events=evidence, finding_type="successful_login_after_failures",
                title="Successful login after repeated failures",
                description=f"Successful login for {success.username or 'unknown user'} from {source_ip} followed {len(qualifying)} failures",
                entity_type="source_ip", entity_value=source_ip, risk=risk, mitre_technique="T1078",
                mitre_tactic="Initial Access",
                false_positives=["Legitimate user recovered the correct password", "Corporate VPN or shared egress IP"],
                queries=["Review post-login process and authorization activity", "Validate the login with the account owner"]))
    return findings


SUSPICIOUS_POWERSHELL = re.compile(r"(?:-enc(?:odedcommand)?\b|downloadstring|invoke-expression|\biex\b|executionpolicy\s+bypass|windowstyle\s+hidden|frombase64string)", re.I)
WEB_EXPLOIT = re.compile(r"(?:\.\./|%2e%2e|union(?:%20|\s)+select|<script|%3cscript|\$\{jndi:|/etc/passwd|cmd\.exe|/wp-admin)", re.I)


def detect_extended_findings(events: Iterable[Event], *, threshold: int, window_minutes: int) -> list[Finding]:
    ordered = [event for event in sorted(events, key=timeline_sort_key) if event.timestamp_normalized]
    findings: list[Finding] = []
    window = timedelta(minutes=window_minutes)

    # Password spraying: one origin targets several distinct accounts.
    failures = [e for e in ordered if e.event_action == "login" and e.event_outcome == "failure"]
    for source_ip, group in _group(failures, lambda e: e.source_ip).items():
        if not source_ip:
            continue
        for candidate in group:
            current = [e for e in group if timedelta(0) <= candidate.timestamp_normalized-e.timestamp_normalized <= window]
            users = {e.username for e in current if e.username}
            if len(current) >= threshold and len(users) >= 3:
                risk = calculate_risk(severity_weight=88, frequency_score=100, privilege_weight=30,
                                      correlation_count=len(current)-1, novelty_score=90)
                findings.append(make_finding(events=current, finding_type="password_spraying",
                    title="Password spraying across multiple accounts",
                    description=f"{source_ip} generated {len(current)} failed logins across {len(users)} accounts",
                    entity_type="source_ip", entity_value=source_ip, risk=risk, mitre_technique="T1110.003",
                    mitre_tactic="Credential Access",
                    false_positives=["Identity health check", "Shared proxy", "Authorized password audit"],
                    queries=["List targeted usernames", "Check successful logins from the same source"]))
                break

    # Distributed guessing: several origins target the same account.
    for username, group in _group(failures, lambda e: e.username).items():
        ips = {e.source_ip for e in group if e.source_ip}
        if username and len(group) >= threshold and len(ips) >= 3:
            risk = calculate_risk(severity_weight=85, frequency_score=100, privilege_weight=80 if username.lower() in {"root","admin","administrator"} else 30,
                                  correlation_count=len(group)-1, novelty_score=100)
            findings.append(make_finding(events=group, finding_type="distributed_password_guessing",
                title="Distributed password guessing",
                description=f"Account {username} received {len(group)} failed logins from {len(ips)} source IPs",
                entity_type="username", entity_value=username, risk=risk, mitre_technique="T1110.001",
                mitre_tactic="Credential Access",
                false_positives=["Distributed monitoring infrastructure", "Federated authentication retries"],
                queries=["Review geographic and ASN diversity", "Check for a subsequent successful login"]))

    signature_rules = [
        ("suspicious_powershell", "Suspicious PowerShell execution", "T1059.001", "Execution",
         lambda e: bool(SUSPICIOUS_POWERSHELL.search(e.command_line or e.raw_log or ""))),
        ("web_exploitation", "Potential web exploitation attempt", "T1190", "Initial Access",
         lambda e: bool(WEB_EXPLOIT.search(e.url_path or e.raw_log or ""))),
        ("persistence_change", "Persistence mechanism created", "T1543.003", "Persistence",
         lambda e: e.event_category == "persistence" or e.event_action == "service_install"),
        ("privilege_escalation", "Privilege escalation activity", "T1548", "Privilege Escalation",
         lambda e: e.event_category == "authorization" and e.event_action == "privilege_escalation"),
    ]
    for finding_type, title, technique, tactic, predicate in signature_rules:
        for event in ordered:
            if not predicate(event):
                continue
            risk = calculate_risk(severity_weight=95 if finding_type != "web_exploitation" else 80,
                                  frequency_score=20, privilege_weight=80, correlation_count=0, novelty_score=90)
            entity = event.host or event.source_ip or event.username or event.process_name or event.source_name
            findings.append(make_finding(events=[event], finding_type=finding_type, title=title,
                description=f"Observed {event.event_action} in {event.source_type}; validate surrounding activity before containment",
                entity_type="host" if event.host else "source", entity_value=entity or "unknown", risk=risk,
                mitre_technique=technique, mitre_tactic=tactic,
                false_positives=["Authorized administration or testing", "Application input containing a signature-like string"],
                queries=["Review adjacent events and parent process", "Validate change window and asset owner"]))
    return findings


def _group(events: Iterable[Event], key):
    grouped = defaultdict(list)
    for event in events:
        grouped[key(event)].append(event)
    return grouped


def rebuild_case_analysis(db: Session, case_id, settings: Settings) -> tuple[int, int]:
    events = list(db.scalars(select(Event).where(Event.case_id == case_id)))
    previous_workflow = {
        (item.finding_type, item.entity_type, item.entity_value): {
            "workflow_status": item.workflow_status, "disposition": item.disposition,
            "assigned_to": item.assigned_to, "analyst_notes": item.analyst_notes,
            "workflow_updated_at": item.workflow_updated_at,
        }
        for item in db.scalars(select(Finding).where(Finding.case_id == case_id))
    }
    db.execute(delete(Correlation).where(Correlation.case_id == case_id))
    db.execute(delete(Finding).where(Finding.case_id == case_id))
    correlations = build_correlations(events, settings.correlation_window_minutes)
    findings = detect_auth_findings(events, correlations, threshold=settings.brute_force_threshold,
                                    window_minutes=settings.brute_force_window_minutes)
    findings.extend(detect_extended_findings(events, threshold=settings.brute_force_threshold,
                                             window_minutes=settings.brute_force_window_minutes))
    for finding in findings:
        workflow = previous_workflow.get((finding.finding_type, finding.entity_type, finding.entity_value))
        if workflow:
            for field, value in workflow.items():
                setattr(finding, field, value)
    db.add_all([*correlations, *findings])
    return len(correlations), len(findings)
