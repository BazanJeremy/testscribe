"""Enriched bug report output schema — fully structured, validated output."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CVSSLiteScore(BaseModel):
    """QA-adapted severity scoring inspired by CVSS v3."""

    functional_impact: Literal["none", "partial", "full"]
    reproducibility: Literal["always", "sometimes", "rare"]
    user_scope: Literal["single", "group", "all"]
    regression_type: Literal["new", "known", "reopened"]
    score: float = Field(ge=0.0, le=10.0, description="Computed 0-10 severity score")
    priority: Literal["low", "medium", "high", "critical"]
    rationale: str = Field(max_length=300, description="One-sentence scoring justification")


class MedtechCompliance(BaseModel):
    """IEC 62304 software safety classification tags."""

    iec_62304_class: Literal["A", "B", "C"] = Field(
        description="A=no injury risk, B=non-serious injury, C=serious injury or death"
    )
    soup_impact: bool = Field(description="Does the bug affect a SOUP component?")
    traceability_tag: str = Field(
        description="Requirement or test case ID this maps to, or 'UNTRACED'"
    )
    change_control_required: bool


class FintechCompliance(BaseModel):
    """PSD2 / DORA operational risk tags."""

    psd2_article: str | None = Field(
        default=None,
        description="Relevant PSD2 article (e.g. 'Art.97 - Strong Authentication')",
    )
    dora_risk_level: Literal["low", "medium", "high"]
    aml_flag: bool = Field(description="Potential Anti-Money Laundering relevance")
    incident_reporting_required: bool


class ComplianceTag(BaseModel):
    """Sector-specific compliance classification."""

    sector: Literal["medtech", "fintech", "generic"]
    medtech: MedtechCompliance | None = None
    fintech: FintechCompliance | None = None


class SimilarBug(BaseModel):
    """Reference to a semantically similar historical bug."""

    bug_id: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    pattern: str
    title_snippet: str = Field(max_length=120)


class EnrichedReport(BaseModel):
    """Fully enriched bug report — output of the TestScribe pipeline."""

    id: str
    raw_input: str
    title: str = Field(max_length=200)
    summary: str = Field(max_length=400, description="Professional one-liner in English")

    # Structured reproduction
    reproduction_steps: list[str] = Field(
        min_length=1,
        description="Given/When/Then formatted steps",
    )
    environment: dict[str, str] = Field(
        description="Inferred environment: os, browser, version, locale"
    )
    expected_result: str = Field(max_length=400)
    actual_result: str = Field(max_length=400)

    # Severity
    severity: CVSSLiteScore

    # Pattern classification
    pattern: str = Field(
        description="Pattern label e.g. UI_REGRESSION, AUTH_FLOW, DATA_VALIDATION"
    )
    similar_bugs: list[SimilarBug] = Field(
        default_factory=list,
        description="Semantically similar bugs from vector store",
    )
    duplicate_probability: float = Field(
        ge=0.0,
        le=1.0,
        description="Probability this is a duplicate of an existing report",
    )

    # Compliance
    compliance: ComplianceTag

    # Pipeline metadata
    enriched_by: Literal["claude-sonnet-4-6", "rule-based-fallback"]
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall enrichment confidence",
    )
    enriched_at: datetime = Field(default_factory=_utcnow)
