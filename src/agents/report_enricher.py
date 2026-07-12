"""ReportEnricher — transforms a raw bug report into a structured description.

Uses claude-sonnet-4-6 when ANTHROPIC_API_KEY is set, falls back to
a deterministic Jinja2 rule-based enricher so CI always passes.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

try:
    import anthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Output dataclass (passed to orchestrator, not final schema)
# ---------------------------------------------------------------------------


@dataclass
class EnrichmentResult:
    title: str
    summary: str
    reproduction_steps: list[str]
    environment: dict[str, str]
    expected_result: str
    actual_result: str
    enriched_by: str
    confidence_score: float


# ---------------------------------------------------------------------------
# Fallback — deterministic rule-based enricher
# ---------------------------------------------------------------------------

_ENV_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"firefox", re.IGNORECASE), "browser", "Firefox"),
    (re.compile(r"chrome", re.IGNORECASE), "browser", "Chrome"),
    (re.compile(r"safari", re.IGNORECASE), "browser", "Safari"),
    (re.compile(r"edge", re.IGNORECASE), "browser", "Edge"),
    (re.compile(r"android", re.IGNORECASE), "os", "Android"),
    (re.compile(r"iphone|ios", re.IGNORECASE), "os", "iOS"),
    (re.compile(r"windows\s*11", re.IGNORECASE), "os", "Windows 11"),
    (re.compile(r"windows\s*10", re.IGNORECASE), "os", "Windows 10"),
    (re.compile(r"windows", re.IGNORECASE), "os", "Windows"),
    (re.compile(r"macos|mac os", re.IGNORECASE), "os", "macOS"),
    (re.compile(r"linux|ubuntu", re.IGNORECASE), "os", "Linux"),
    (re.compile(r"mobile|phone|smartphone", re.IGNORECASE), "platform", "Mobile"),
    (re.compile(r"staging", re.IGNORECASE), "environment", "Staging"),
    (re.compile(r"production|prod\b", re.IGNORECASE), "environment", "Production"),
]

_VERSION_RE = re.compile(
    r"v?(\d+\.\d+(?:\.\d+)?)|version\s+(\d+\.\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

_CRASH_RE = re.compile(r"crash|freeze|hang|timeout|502|500|error", re.IGNORECASE)
_EXPECTED_KEYWORDS = re.compile(
    r"should|expect|correct|normal|proper|intended", re.IGNORECASE
)


def _extract_environment(text: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for pattern, key, value in _ENV_PATTERNS:
        if pattern.search(text) and key not in env:
            env[key] = value
    version_match = _VERSION_RE.search(text)
    if version_match:
        env["version"] = version_match.group(1) or version_match.group(2)
    if not env:
        env["os"] = "unspecified"
    return env


def _build_steps(title: str, description: str, component: str | None) -> list[str]:
    comp_label = component.replace("-", " ") if component else "the feature"
    # Extract numbered steps if present
    numbered = re.findall(r"\d+[.)]\s+(.+)", description)
    if len(numbered) >= 2:
        return [
            f"Given the user has access to {comp_label}",
            *[f"When {s.rstrip('.')}" for s in numbered[:3]],
            "Then the issue described above is observed",
        ]
    sentences = [s.strip() for s in re.split(r"[.!?]+", description) if s.strip()]
    action = sentences[0] if sentences else "the user performs the action"
    return [
        f"Given the user navigates to {comp_label}",
        f"When {action[:120]}",
        "Then the observed behaviour differs from expected",
    ]


def _extract_actual(description: str) -> str:
    sentences = [s.strip() for s in re.split(r"[.!?]+", description) if s.strip()]
    for s in reversed(sentences):
        if len(s) > 20 and not _EXPECTED_KEYWORDS.search(s):
            return s[:300]
    return sentences[-1][:300] if sentences else description[:300]


def _extract_expected(title: str, description: str) -> str:
    for s in re.split(r"[.!?]+", description):
        if _EXPECTED_KEYWORDS.search(s) and len(s.strip()) > 15:
            return s.strip()[:300]
    verb = "function correctly"
    if _CRASH_RE.search(title):
        verb = "remain stable and responsive"
    return f"The {title.lower()} should {verb}."


def _generate_title(raw_title: str | None, description: str) -> str:
    if raw_title and len(raw_title) > 10:
        return raw_title[:200]
    first = re.split(r"[.!?]+", description)[0].strip()
    return first[:100] if first else "Untitled bug report"


def enrich_rule_based(
    description: str,
    title: str | None = None,
    component: str | None = None,
) -> EnrichmentResult:
    """Deterministic fallback enricher — no API key required."""
    gen_title = _generate_title(title, description)
    first_sentence = re.split(r"[.!?]+", description)[0].strip()
    summary = f"{first_sentence[:200]}." if first_sentence else description[:200]

    return EnrichmentResult(
        title=gen_title,
        summary=summary,
        reproduction_steps=_build_steps(gen_title, description, component),
        environment=_extract_environment(description),
        expected_result=_extract_expected(gen_title, description),
        actual_result=_extract_actual(description),
        enriched_by="rule-based-fallback",
        confidence_score=0.55,
    )


# ---------------------------------------------------------------------------
# Claude agent
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a senior QA engineer. Given a raw bug report, produce a
structured enrichment as valid JSON with exactly these keys:
- title: str (concise, max 120 chars)
- summary: str (professional one-liner, max 300 chars)
- reproduction_steps: list[str] (3-5 steps in Given/When/Then format)
- environment: dict[str,str] (inferred os, browser, version, environment)
- expected_result: str (what should happen, max 300 chars)
- actual_result: str (what actually happened, max 300 chars)
- confidence_score: float (0.0-1.0, your confidence in the enrichment)

Return ONLY the JSON object. No markdown, no explanation."""


def enrich_with_claude(
    description: str,
    title: str | None = None,
    component: str | None = None,
    api_key: str | None = None,
) -> EnrichmentResult:
    """Enrich using claude-sonnet-4-6. Raises on API failure."""
    if not _ANTHROPIC_AVAILABLE:
        raise RuntimeError("anthropic package not installed")

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=key)
    context = f"Title: {title}\n" if title else ""
    context += f"Component: {component}\n" if component else ""
    context += f"Description: {description}"

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )

    raw_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            raw_text += block.text

    # Strip possible markdown fences
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
    data = json.loads(clean)

    return EnrichmentResult(
        title=str(data.get("title", title or ""))[:200],
        summary=str(data.get("summary", ""))[:400],
        reproduction_steps=list(data.get("reproduction_steps", [])),
        environment=dict(data.get("environment", {})),
        expected_result=str(data.get("expected_result", ""))[:400],
        actual_result=str(data.get("actual_result", ""))[:400],
        enriched_by="claude-sonnet-4-6",
        confidence_score=float(data.get("confidence_score", 0.8)),
    )


# ---------------------------------------------------------------------------
# Public interface — auto-selects backend
# ---------------------------------------------------------------------------


class ReportEnricher:
    """Auto-selects Claude or rule-based fallback based on API key availability."""

    def __init__(self, api_key: str | None = None, force_fallback: bool = False):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._force_fallback = force_fallback

    def enrich(
        self,
        description: str,
        title: str | None = None,
        component: str | None = None,
    ) -> EnrichmentResult:
        if self._force_fallback or not self._api_key:
            return enrich_rule_based(description, title, component)
        try:
            return enrich_with_claude(description, title, component, self._api_key)
        except Exception:
            return enrich_rule_based(description, title, component)
