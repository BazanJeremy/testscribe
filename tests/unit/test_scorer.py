"""Unit tests for SeverityScorer — fallback mode, no API key required."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agents.severity_scorer import (
    SeverityScorer,
    score_rule_based,
    _compute_score,
    _infer_impact,
    _infer_scope,
    _infer_repro,
    _infer_regression,
)


# ---------------------------------------------------------------------------
# Scoring matrix correctness
# ---------------------------------------------------------------------------

class TestComputeScore:
    def test_worst_case_is_critical(self):
        score, priority = _compute_score("full", "always", "all", "reopened")
        assert score >= 8.5
        assert priority == "critical"

    def test_best_case_is_low(self):
        score, priority = _compute_score("none", "rare", "single", "known")
        assert priority == "low"

    def test_score_within_bounds(self):
        score, _ = _compute_score("full", "always", "all", "new")
        assert 0.0 <= score <= 10.0

    def test_score_is_rounded_to_one_decimal(self):
        score, _ = _compute_score("partial", "sometimes", "group", "new")
        assert score == round(score, 1)

    def test_medium_case(self):
        score, priority = _compute_score("partial", "sometimes", "single", "new")
        assert 4.0 <= score <= 8.5

    def test_critical_threshold(self):
        score, priority = _compute_score("full", "always", "group", "new")
        # full=4.0, always=2.5, group=1.2, new=1.2 = 8.9
        assert priority in ("critical", "high")


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------

class TestInferImpact:
    def test_crash_is_full(self):
        assert _infer_impact("The app crashes on startup") == "full"

    def test_security_is_full(self):
        assert _infer_impact("SQL injection possible in the form") == "full"

    def test_wrong_result_is_partial(self):
        assert _infer_impact("Wrong result displayed in the calculator") == "partial"

    def test_alarm_silent_is_full(self):
        assert _infer_impact("Occlusion alarm doesn't sound") == "full"


class TestInferScope:
    def test_all_users_detected(self):
        assert _infer_scope("Affects all users on the platform") == "all"

    def test_all_browsers_detected(self):
        assert _infer_scope("Issue on all browsers") == "all"

    def test_group_scope_detected(self):
        assert _infer_scope("Ward nurses cannot login") == "group"

    def test_single_is_default(self):
        assert _infer_scope("I cannot submit the form") == "single"


class TestInferRepro:
    def test_always_repro(self):
        assert _infer_repro("Reproduced every time, 100% consistent") == "always"

    def test_reproduced_n_times(self):
        assert _infer_repro("Reproduced 3 times in a row") == "always"

    def test_intermittent_is_sometimes(self):
        assert _infer_repro("Intermittent issue, not always") == "sometimes"

    def test_default_is_sometimes(self):
        assert _infer_repro("The button is broken") == "sometimes"


class TestInferRegression:
    def test_regression_keyword(self):
        assert _infer_regression("This is a regression from v2.4") == "reopened"

    def test_new_bug_is_default(self):
        assert _infer_regression("Brand new defect found in testing") == "new"


# ---------------------------------------------------------------------------
# Full scoring output
# ---------------------------------------------------------------------------

class TestScoreRuleBased:
    def test_returns_severity_result(self, firefox_report):
        result = score_rule_based(firefox_report.description, firefox_report.title)
        assert result is not None

    def test_enriched_by_is_rule_based(self, firefox_report):
        result = score_rule_based(firefox_report.description)
        assert result.enriched_by == "rule-based-fallback"

    def test_score_in_range(self, firefox_report):
        result = score_rule_based(firefox_report.description)
        assert 0.0 <= result.score <= 10.0

    def test_priority_is_valid_literal(self, firefox_report):
        result = score_rule_based(firefox_report.description)
        assert result.priority in ("low", "medium", "high", "critical")

    def test_rationale_non_empty(self, firefox_report):
        result = score_rule_based(firefox_report.description)
        assert len(result.rationale) > 0

    def test_alarm_bug_scores_critical(self, medtech_report):
        """RAW-001: silent infusion pump alarm must score critical."""
        result = score_rule_based(medtech_report.description, medtech_report.title)
        assert result.priority == "critical"

    def test_security_bug_scores_high_or_critical(self, security_report):
        """SQL injection must score high or critical."""
        result = score_rule_based(security_report.description, security_report.title)
        assert result.priority in ("high", "critical")


# ---------------------------------------------------------------------------
# SeverityScorer class
# ---------------------------------------------------------------------------

class TestSeverityScorer:
    def test_force_fallback_uses_rule_based(self, scorer, firefox_report):
        result = scorer.score(firefox_report.description, firefox_report.title)
        assert result.enriched_by == "rule-based-fallback"

    def test_all_seed_reports_score_without_error(self, seed_reports, scorer):
        """All 30 seed reports must score without raising."""
        errors = []
        for raw in seed_reports:
            try:
                result = scorer.score(raw["description"], raw.get("title"))
                assert result.priority in ("low", "medium", "high", "critical")
                assert 0.0 <= result.score <= 10.0
            except Exception as e:
                errors.append(f'{raw["id"]}: {e}')
        assert errors == [], f"Scoring errors: {errors}"

    def test_compute_score_from_dims_utility(self):
        score, priority = SeverityScorer.compute_score_from_dims(
            "full", "always", "all", "new"
        )
        assert 0.0 <= score <= 10.0
        assert priority in ("low", "medium", "high", "critical")


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

class TestScorerProperties:
    @given(
        description=st.text(min_size=1, max_size=500).filter(lambda s: s.strip()),
    )
    @settings(max_examples=50)
    def test_any_description_produces_valid_score(self, description):
        result = score_rule_based(description)
        assert 0.0 <= result.score <= 10.0
        assert result.priority in ("low", "medium", "high", "critical")
        assert result.enriched_by == "rule-based-fallback"

    @given(
        impact=st.sampled_from(["none", "partial", "full"]),
        repro=st.sampled_from(["always", "sometimes", "rare"]),
        scope=st.sampled_from(["single", "group", "all"]),
        regression=st.sampled_from(["new", "known", "reopened"]),
    )
    @settings(max_examples=40)
    def test_all_dimension_combinations_valid(self, impact, repro, scope, regression):
        score, priority = _compute_score(impact, repro, scope, regression)  # type: ignore[arg-type]
        assert 0.0 <= score <= 10.0
        assert priority in ("low", "medium", "high", "critical")
