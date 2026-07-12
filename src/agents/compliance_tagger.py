"""ComplianceTagger — sector-specific regulatory classification.

Maps enriched bug reports to compliance frameworks:
- Medtech: IEC 62304 software safety class (A/B/C), SOUP impact
- Fintech: PSD2 article, DORA operational risk, AML flag

Uses Claude when available, deterministic keyword rules as fallback.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Literal

try:
    import anthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

Sector = Literal["medtech", "fintech", "generic"]


@dataclass
class MedtechTag:
    iec_62304_class: Literal["A", "B", "C"]
    soup_impact: bool
    traceability_tag: str
    change_control_required: bool
    rationale: str


@dataclass
class FintechTag:
    psd2_article: str | None
    dora_risk_level: Literal["low", "medium", "high"]
    aml_flag: bool
    incident_reporting_required: bool
    rationale: str


@dataclass
class ComplianceResult:
    sector: Sector
    medtech: MedtechTag | None = None
    fintech: FintechTag | None = None
    tagged_by: str = "rule-based-fallback"


# ---------------------------------------------------------------------------
# IEC 62304 — Medtech rules
# ---------------------------------------------------------------------------

# Class C: software failure could cause death or serious injury
_IEC_CLASS_C_RE = re.compile(
    r"alarm|death|fatal|patient.safet|occlusion|infusion.pump|vital.sign|"
    r"dosage|drug.deliver|ventilat|defibrillat|radiation|implant",
    re.IGNORECASE,
)
# Class B: non-serious injury
_IEC_CLASS_B_RE = re.compile(
    r"discharge|e.sign|audit.log|session.timeout|authentication|medication.record|"
    r"reconcili|dicom|medical.image|clinical.diagnosis|patient.report|traceabilit",
    re.IGNORECASE,
)

_SOUP_RE = re.compile(
    r"third.party|external.librar|open.source|vendor|SOUP|framework|"
    r"dicom|hl7|fhir|siemens|philips|scanner",
    re.IGNORECASE,
)

_CHANGE_CONTROL_RE = re.compile(
    r"class [BC]|safety|alarm|dose|infusion|critical|certif|validat",
    re.IGNORECASE,
)


def _tag_medtech(text: str, pattern: str = "", severity_priority: str = "medium") -> MedtechTag:
    combined = f"{text} {pattern}"

    if _IEC_CLASS_C_RE.search(combined) or severity_priority == "critical":
        iec_class: Literal["A", "B", "C"] = "C"
        rationale = "Software failure could directly contribute to serious injury or death."
    elif _IEC_CLASS_B_RE.search(combined) or severity_priority == "high":
        iec_class = "B"
        rationale = "Software failure could contribute to non-serious injury or clinical error."
    else:
        iec_class = "A"
        rationale = "No injury risk identified; defect affects administrative functionality only."

    soup = bool(_SOUP_RE.search(combined))
    # Class A: no change control regardless of other signals;
    # Class B or C always requires change control
    change_ctrl = iec_class != "A"

    # Derive traceability tag from pattern
    pattern_map = {
        "SAFETY_CRITICAL": "SRS-SAF",
        "AUTH_FLOW": "SRS-SEC",
        "DATA_INTEGRITY": "SRS-INT",
        "COMPLIANCE_REGULATORY": "SRS-REG",
        "DATA_VALIDATION": "SRS-VAL",
        "PERFORMANCE": "SRS-PERF",
        "INTEGRATION": "SRS-INT",
    }
    trace_prefix = pattern_map.get(pattern.upper(), "SRS-GEN")
    trace_tag = f"{trace_prefix}-UNTRACED"

    return MedtechTag(
        iec_62304_class=iec_class,
        soup_impact=soup,
        traceability_tag=trace_tag,
        change_control_required=change_ctrl,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# PSD2 / DORA — Fintech rules
# ---------------------------------------------------------------------------

_PSD2_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"2fa|otp|totp|strong.auth|multi.factor|mfa", re.IGNORECASE),
     "Art.97 — Strong Customer Authentication (SCA)"),
    (re.compile(r"transaction.notif|push.notif|alert.*transfer|payment.*notif", re.IGNORECASE),
     "Art.97 — Transaction Monitoring & Notification"),
    (re.compile(r"wire.transfer|payment.process|fund.transfer|outgoing.transfer", re.IGNORECASE),
     "Art.36 — Access to Payment Systems"),
    (re.compile(r"iban|beneficiar|payee.validat", re.IGNORECASE),
     "Art.80 — Payee Verification Requirements"),
    (re.compile(r"session.*persist|password.*change.*session|token.*invalidat", re.IGNORECASE),
     "Art.97 — Session Security"),
    (re.compile(r"account.freeze|compliance.dashboard|aml|anti.money", re.IGNORECASE),
     "Art.88 — Fraud Prevention"),
]

_DORA_HIGH_RE = re.compile(
    r"payment.process|wire.transfer|session.persist|account.freeze|"
    r"2fa.*expir|expired.*token|notif.*not.sent|compliance.engine",
    re.IGNORECASE,
)
_DORA_MEDIUM_RE = re.compile(
    r"iban|beneficiar|pagination|pdf.statement|currency.rate|loan.calculat|"
    r"transaction.history|exchange.rate",
    re.IGNORECASE,
)

_AML_RE = re.compile(
    r"account.freeze|aml|anti.money|suspicious|large.transaction|"
    r"compliance.dashboard|api.*freeze|freeze.*api",
    re.IGNORECASE,
)

_INCIDENT_REPORTING_RE = re.compile(
    r"payment.process|wire.transfer|session.persist|account.freeze|"
    r"2fa|strong.auth|notif.*not.sent",
    re.IGNORECASE,
)


def _tag_fintech(text: str, pattern: str = "", severity_priority: str = "medium") -> FintechTag:
    combined = f"{text} {pattern}"

    psd2_article: str | None = None
    for psd2_re, article in _PSD2_RULES:
        if psd2_re.search(combined):
            psd2_article = article
            break

    if _DORA_HIGH_RE.search(combined) or severity_priority in ("critical", "high"):
        dora_level: Literal["low", "medium", "high"] = "high"
        rationale = "High operational risk: defect affects core payment or security controls."
    elif _DORA_MEDIUM_RE.search(combined) or severity_priority == "medium":
        dora_level = "medium"
        rationale = "Medium operational risk: defect affects financial data accuracy or access."
    else:
        dora_level = "low"
        rationale = "Low operational risk: defect affects UI or non-critical reporting."

    aml = bool(_AML_RE.search(combined))
    incident = bool(_INCIDENT_REPORTING_RE.search(combined)) or severity_priority in ("critical", "high")

    return FintechTag(
        psd2_article=psd2_article,
        dora_risk_level=dora_level,
        aml_flag=aml,
        incident_reporting_required=incident,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Claude agent
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_MEDTECH = """You are a medical device software compliance specialist (IEC 62304).
Analyse this bug report and return JSON with these keys:
- iec_62304_class: "A" | "B" | "C" (A=no injury, B=non-serious injury, C=serious injury/death)
- soup_impact: bool (does this affect a Software Of Unknown Provenance component?)
- traceability_tag: str (requirement ID or "SRS-GEN-UNTRACED")
- change_control_required: bool
- rationale: str (one sentence, max 200 chars)

Return ONLY the JSON object."""

_SYSTEM_PROMPT_FINTECH = """You are a PSD2/DORA compliance specialist.
Analyse this bug report and return JSON with these keys:
- psd2_article: str | null (most relevant PSD2 article, e.g. "Art.97 — Strong Customer Authentication")
- dora_risk_level: "low" | "medium" | "high"
- aml_flag: bool (potential Anti-Money Laundering relevance)
- incident_reporting_required: bool
- rationale: str (one sentence, max 200 chars)

Return ONLY the JSON object."""


def _claude_tag(system: str, text: str, api_key: str) -> dict:
    if not _ANTHROPIC_AVAILABLE:
        raise RuntimeError("anthropic package not installed")
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": text}],
    )
    raw = "".join(b.text for b in msg.content if hasattr(b, "text"))
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    return json.loads(clean)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class ComplianceTagger:
    """Auto-selects Claude or rule-based compliance tagging."""

    def __init__(self, api_key: str | None = None, force_fallback: bool = False):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._force_fallback = force_fallback

    def tag(
        self,
        description: str,
        sector: Sector,
        pattern: str = "",
        severity_priority: str = "medium",
        title: str | None = None,
    ) -> ComplianceResult:
        combined = f"{title or ''} {description}"

        if sector == "generic":
            return ComplianceResult(sector="generic", tagged_by="rule-based-fallback")

        if self._force_fallback or not self._api_key:
            return self._rule_based(combined, sector, pattern, severity_priority)

        try:
            return self._claude_tag_dispatch(combined, sector, pattern, severity_priority)
        except Exception:
            return self._rule_based(combined, sector, pattern, severity_priority)

    def _rule_based(
        self, text: str, sector: Sector, pattern: str, severity_priority: str
    ) -> ComplianceResult:
        if sector == "medtech":
            return ComplianceResult(
                sector="medtech",
                medtech=_tag_medtech(text, pattern, severity_priority),
                tagged_by="rule-based-fallback",
            )
        return ComplianceResult(
            sector="fintech",
            fintech=_tag_fintech(text, pattern, severity_priority),
            tagged_by="rule-based-fallback",
        )

    def _claude_tag_dispatch(
        self, text: str, sector: Sector, pattern: str, severity_priority: str
    ) -> ComplianceResult:
        assert self._api_key
        if sector == "medtech":
            data = _claude_tag(_SYSTEM_PROMPT_MEDTECH, text, self._api_key)
            mt = MedtechTag(
                iec_62304_class=data.get("iec_62304_class", "A"),
                soup_impact=bool(data.get("soup_impact", False)),
                traceability_tag=str(data.get("traceability_tag", "SRS-GEN-UNTRACED")),
                change_control_required=bool(data.get("change_control_required", False)),
                rationale=str(data.get("rationale", ""))[:300],
            )
            return ComplianceResult(sector="medtech", medtech=mt, tagged_by="claude-sonnet-4-6")

        data = _claude_tag(_SYSTEM_PROMPT_FINTECH, text, self._api_key)
        ft = FintechTag(
            psd2_article=data.get("psd2_article"),
            dora_risk_level=data.get("dora_risk_level", "low"),
            aml_flag=bool(data.get("aml_flag", False)),
            incident_reporting_required=bool(data.get("incident_reporting_required", False)),
            rationale=str(data.get("rationale", ""))[:300],
        )
        return ComplianceResult(sector="fintech", fintech=ft, tagged_by="claude-sonnet-4-6")
