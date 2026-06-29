"""Enrichment Orchestrator — coordinates all four agents into a single pipeline.

Input:  RawReport
Output: EnrichedReport

Pipeline:
  1. ReportEnricher  → title, summary, steps, environment, expected/actual
  2. SeverityScorer  → CVSS-lite score, priority, rationale
  3. PatternClassifier → pattern label, similar bugs, duplicate probability
  4. ComplianceTagger → sector-specific compliance tags
  5. Merge            → build validated EnrichedReport Pydantic model
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from schemas import (
    RawReport,
    EnrichedReport,
    CVSSLiteScore,
    ComplianceTag,
    MedtechCompliance,
    FintechCompliance,
    SimilarBug,
)
from agents.report_enricher import ReportEnricher
from agents.severity_scorer import SeverityScorer
from agents.pattern_classifier import PatternClassifier
from agents.compliance_tagger import ComplianceTagger


class Orchestrator:
    """Coordinates the four TestScribe enrichment agents.

    All agents default to rule-based fallback when ANTHROPIC_API_KEY is absent,
    ensuring the pipeline runs in CI without network access.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        force_fallback: bool = False,
        chroma_persist_path: Optional[str | Path] = None,
    ) -> None:
        self._enricher = ReportEnricher(api_key=api_key, force_fallback=force_fallback)
        self._scorer = SeverityScorer(api_key=api_key, force_fallback=force_fallback)
        self._classifier = PatternClassifier(
            persist_path=chroma_persist_path,
            force_fallback=force_fallback,
        )
        self._tagger = ComplianceTagger(api_key=api_key, force_fallback=force_fallback)

    def enrich(self, raw: RawReport) -> EnrichedReport:
        """Run the full enrichment pipeline on a RawReport."""

        # ------------------------------------------------------------------
        # Step 1 — ReportEnricher
        # ------------------------------------------------------------------
        enrichment = self._enricher.enrich(
            raw.description,
            title=raw.title,
            component=raw.component,
        )

        # ------------------------------------------------------------------
        # Step 2 — SeverityScorer
        # ------------------------------------------------------------------
        severity = self._scorer.score(raw.description, title=raw.title)

        # ------------------------------------------------------------------
        # Step 3 — PatternClassifier
        # ------------------------------------------------------------------
        classification = self._classifier.classify(
            raw.description,
            title=raw.title,
            sector=raw.sector,
            n_similar=3,
        )

        # ------------------------------------------------------------------
        # Step 4 — ComplianceTagger
        # ------------------------------------------------------------------
        sector = raw.sector or "generic"
        compliance_result = self._tagger.tag(
            raw.description,
            sector=sector,  # type: ignore[arg-type]
            pattern=classification.pattern,
            severity_priority=severity.priority,
            title=raw.title,
        )

        # ------------------------------------------------------------------
        # Step 5 — Merge into validated EnrichedReport
        # ------------------------------------------------------------------
        report_id = raw.id or f"TS-{uuid.uuid4().hex[:8].upper()}"

        cvss = CVSSLiteScore(
            functional_impact=severity.functional_impact,
            reproducibility=severity.reproducibility,
            user_scope=severity.user_scope,
            regression_type=severity.regression_type,
            score=severity.score,
            priority=severity.priority,
            rationale=severity.rationale,
        )

        compliance = _build_compliance_tag(compliance_result)

        similar_bugs = [
            SimilarBug(
                bug_id=s.bug_id,
                similarity_score=s.similarity_score,
                pattern=s.pattern,
                title_snippet=s.document[:120],
            )
            for s in classification.similar_bugs
        ]

        # Determine which agent drove the enrichment label
        enriched_by = (
            "claude-sonnet-4-6"
            if enrichment.enriched_by == "claude-sonnet-4-6"
            else "rule-based-fallback"
        )

        # Overall confidence: weighted average of enricher + classifier
        confidence = round(
            (enrichment.confidence_score * 0.5 + classification.confidence * 0.5), 3
        )

        return EnrichedReport(
            id=report_id,
            raw_input=raw.description,
            title=enrichment.title,
            summary=enrichment.summary,
            reproduction_steps=enrichment.reproduction_steps,
            environment=enrichment.environment,
            expected_result=enrichment.expected_result,
            actual_result=enrichment.actual_result,
            severity=cvss,
            pattern=classification.pattern,
            similar_bugs=similar_bugs,
            duplicate_probability=classification.duplicate_probability,
            compliance=compliance,
            enriched_by=enriched_by,
            confidence_score=confidence,
            enriched_at=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _build_compliance_tag(result) -> ComplianceTag:  # type: ignore[no-untyped-def]
    """Convert ComplianceResult dataclass → ComplianceTag Pydantic model."""
    from agents.compliance_tagger import ComplianceResult

    medtech = None
    fintech = None

    if result.sector == "medtech" and result.medtech:
        m = result.medtech
        medtech = MedtechCompliance(
            iec_62304_class=m.iec_62304_class,
            soup_impact=m.soup_impact,
            traceability_tag=m.traceability_tag,
            change_control_required=m.change_control_required,
        )

    if result.sector == "fintech" and result.fintech:
        f = result.fintech
        fintech = FintechCompliance(
            psd2_article=f.psd2_article,
            dora_risk_level=f.dora_risk_level,
            aml_flag=f.aml_flag,
            incident_reporting_required=f.incident_reporting_required,
        )

    return ComplianceTag(
        sector=result.sector,
        medtech=medtech,
        fintech=fintech,
    )
