"""SeverityScorer — computes a CVSS-lite QA severity score for a bug report.

Uses claude-sonnet-4-6 when available, deterministic keyword-based fallback otherwise.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Literal, Optional

try:
    import anthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

FunctionalImpact = Literal["none", "partial", "full"]
Reproducibility = Literal["always", "sometimes", "rare"]
UserScope = Literal["single", "group", "all"]
RegressionType = Literal["new", "known", "reopened"]
Priority = Literal["low", "medium", "high", "critical"]


@dataclass
class SeverityResult:
    functional_impact: FunctionalImpact
    reproducibility: Reproducibility
    user_scope: UserScope
    regression_type: RegressionType
    score: float
    priority: Priority
    rationale: str
    enriched_by: str


# ---------------------------------------------------------------------------
# Scoring matrix — maps dimension values to numeric weights
# ---------------------------------------------------------------------------

_IMPACT_WEIGHTS: dict[str, float] = {"none": 0.0, "partial": 0.5, "full": 1.0}
_REPRO_WEIGHTS: dict[str, float] = {"always": 1.0, "sometimes": 0.6, "rare": 0.3}
_SCOPE_WEIGHTS: dict[str, float] = {"single": 0.2, "group": 0.6, "all": 1.0}
_REGRESSION_WEIGHTS: dict[str, float] = {"new": 0.8, "known": 0.5, "reopened": 1.0}


def _compute_score(
    impact: FunctionalImpact,
    repro: Reproducibility,
    scope: UserScope,
    regression: RegressionType,
) -> tuple[float, Priority]:
    raw = (
        _IMPACT_WEIGHTS[impact] * 4.0
        + _REPRO_WEIGHTS[repro] * 2.5
        + _SCOPE_WEIGHTS[scope] * 2.0
        + _REGRESSION_WEIGHTS[regression] * 1.5
    )
    score = round(min(raw, 10.0), 1)
    if score >= 8.0:
        priority: Priority = "critical"
    elif score >= 6.5:
        priority = "high"
    elif score >= 4.0:
        priority = "medium"
    else:
        priority = "low"
    return score, priority


# ---------------------------------------------------------------------------
# Heuristic keyword sets for fallback
# ---------------------------------------------------------------------------

_CRITICAL_KEYWORDS = re.compile(
    r"crash|data.loss|corrupt|security|inject|bypass|not.sent|missing.entr|frozen|"
    r"alarm.doesn|occlusion|session.not|freeze|502|500|overwrite|duplicate.*medication",
    re.IGNORECASE,
)
_HIGH_KEYWORDS = re.compile(
    r"wrong.result|incorrect|invalid|fail|blocked|does.not|no.error|not.working|"
    r"negative.value|expired|persist|not.trigger|not.enforced|skips",
    re.IGNORECASE,
)
_ALL_SCOPE_KEYWORDS = re.compile(
    r"all.user|all.account|all.browser|everyone|all.patient|entire",
    re.IGNORECASE,
)
_GROUP_SCOPE_KEYWORDS = re.compile(
    r"all.firefox|affect.account|large.file|over.5.year|ward|nurse|doctor",
    re.IGNORECASE,
)
_ALWAYS_REPRO_KEYWORDS = re.compile(
    r"(?<!not )\balways\b|every.time|reproduced \d|100%|consistently|each.time",
    re.IGNORECASE,
)
_RARE_REPRO_KEYWORDS = re.compile(
    r"sometimes|intermittent|occasionally|random|not.always|rare|flaky",
    re.IGNORECASE,
)
_REOPEN_KEYWORDS = re.compile(r"regression|reopen|again|broke.again", re.IGNORECASE)
_KNOWN_KEYWORDS = re.compile(r"known.issue|already.reported|workaround.exist", re.IGNORECASE)


def _infer_impact(text: str) -> FunctionalImpact:
    if _CRITICAL_KEYWORDS.search(text):
        return "full"
    if _HIGH_KEYWORDS.search(text):
        return "partial"
    return "partial"  # Safe default — don't underestimate


def _infer_scope(text: str) -> UserScope:
    if _ALL_SCOPE_KEYWORDS.search(text):
        return "all"
    if _GROUP_SCOPE_KEYWORDS.search(text):
        return "group"
    return "single"


def _infer_repro(text: str) -> Reproducibility:
    if _ALWAYS_REPRO_KEYWORDS.search(text):
        return "always"
    if _RARE_REPRO_KEYWORDS.search(text):
        return "sometimes"
    return "sometimes"  # Assume reproducible by default


def _infer_regression(text: str) -> RegressionType:
    if _REOPEN_KEYWORDS.search(text):
        return "reopened"
    if _KNOWN_KEYWORDS.search(text):
        return "known"
    return "new"


def score_rule_based(
    description: str,
    title: Optional[str] = None,
) -> SeverityResult:
    """Deterministic CVSS-lite scoring — no API key required."""
    combined = f"{title or ''} {description}"
    impact = _infer_impact(combined)
    scope = _infer_scope(combined)
    repro = _infer_repro(combined)
    regression = _infer_regression(combined)
    score, priority = _compute_score(impact, repro, scope, regression)

    return SeverityResult(
        functional_impact=impact,
        reproducibility=repro,
        user_scope=scope,
        regression_type=regression,
        score=score,
        priority=priority,
        rationale=f"Rule-based: impact={impact}, repro={repro}, scope={scope}, regression={regression}.",
        enriched_by="rule-based-fallback",
    )


# ---------------------------------------------------------------------------
# Claude agent
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a senior QA engineer specialised in severity assessment.
Given a bug report, return a CVSS-lite severity score as valid JSON with these keys:
- functional_impact: "none" | "partial" | "full"
- reproducibility: "always" | "sometimes" | "rare"
- user_scope: "single" | "group" | "all"
- regression_type: "new" | "known" | "reopened"
- rationale: str (one sentence justifying the scoring, max 200 chars)

Return ONLY the JSON object. No markdown, no explanation."""


def score_with_claude(
    description: str,
    title: Optional[str] = None,
    api_key: Optional[str] = None,
) -> SeverityResult:
    """Score using claude-sonnet-4-6. Raises on API failure."""
    if not _ANTHROPIC_AVAILABLE:
        raise RuntimeError("anthropic package not installed")

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=key)
    context = f"Title: {title}\nDescription: {description}" if title else description

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )

    raw_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            raw_text += block.text

    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
    data = json.loads(clean)

    impact: FunctionalImpact = data.get("functional_impact", "partial")
    repro: Reproducibility = data.get("reproducibility", "sometimes")
    scope: UserScope = data.get("user_scope", "single")
    regression: RegressionType = data.get("regression_type", "new")
    score, priority = _compute_score(impact, repro, scope, regression)

    return SeverityResult(
        functional_impact=impact,
        reproducibility=repro,
        user_scope=scope,
        regression_type=regression,
        score=score,
        priority=priority,
        rationale=str(data.get("rationale", ""))[:300],
        enriched_by="claude-sonnet-4-6",
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


class SeverityScorer:
    """Auto-selects Claude or rule-based fallback."""

    def __init__(self, api_key: Optional[str] = None, force_fallback: bool = False):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._force_fallback = force_fallback

    def score(
        self,
        description: str,
        title: Optional[str] = None,
    ) -> SeverityResult:
        if self._force_fallback or not self._api_key:
            return score_rule_based(description, title)
        try:
            return score_with_claude(description, title, self._api_key)
        except Exception:
            return score_rule_based(description, title)

    @staticmethod
    def compute_score_from_dims(
        impact: FunctionalImpact,
        repro: Reproducibility,
        scope: UserScope,
        regression: RegressionType,
    ) -> tuple[float, Priority]:
        """Utility — compute score from already-known dimensions."""
        return _compute_score(impact, repro, scope, regression)
