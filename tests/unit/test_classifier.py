"""Unit tests for PatternClassifier — RAG + keyword fallback."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agents.pattern_classifier import (
    PatternClassifier,
    ClassificationResult,
    _classify_keyword,
    _load_pattern_library,
)


@pytest.fixture(scope="module")
def patterns():
    return _load_pattern_library()


@pytest.fixture(scope="module")
def classifier():
    """Classifier in RAG mode — seeded with 30 seed reports."""
    return PatternClassifier()


@pytest.fixture
def fallback_classifier():
    return PatternClassifier(force_fallback=True)


# ---------------------------------------------------------------------------
# Keyword classifier
# ---------------------------------------------------------------------------

class TestKeywordClassifier:
    def test_auth_keywords_detected(self, patterns):
        result = _classify_keyword("login button broken on Firefox", patterns)
        assert result == "AUTH_FLOW"

    def test_safety_critical_detected(self, patterns):
        result = _classify_keyword("infusion pump alarm does not sound on occlusion", patterns)
        assert result == "SAFETY_CRITICAL"

    def test_data_validation_detected(self, patterns):
        result = _classify_keyword("negative amount accepted in wire transfer field", patterns)
        assert result == "DATA_VALIDATION"

    def test_security_detected(self, patterns):
        result = _classify_keyword("SQL injection accepted in patient ID field", patterns)
        assert result == "SECURITY"

    def test_performance_detected(self, patterns):
        result = _classify_keyword("graph freezes after 30 minutes of use", patterns)
        assert result == "PERFORMANCE"

    def test_unknown_falls_back_to_ui_regression(self, patterns):
        result = _classify_keyword("something weird happened", patterns)
        assert result == "UI_REGRESSION"

    def test_safety_beats_data_validation_in_priority(self, patterns):
        # "alarm" should win over weaker data-related terms
        result = _classify_keyword("alarm dosage infusion pump occlusion data", patterns)
        assert result == "SAFETY_CRITICAL"


# ---------------------------------------------------------------------------
# RAG classifier
# ---------------------------------------------------------------------------

class TestRAGClassifier:
    def test_store_seeded_with_30_reports(self, classifier):
        assert classifier._store.count() == 30

    def test_classify_returns_result(self, classifier):
        result = classifier.classify("button does not work", title="Checkout broken")
        assert isinstance(result, ClassificationResult)

    def test_infusion_pump_classified_as_safety_critical(self, classifier):
        result = classifier.classify(
            "The infusion pump alarm does not sound when IV line is blocked",
            title="Infusion pump alarm failure",
            sector="medtech",
        )
        assert result.pattern == "SAFETY_CRITICAL"

    def test_2fa_classified_as_auth(self, classifier):
        result = classifier.classify(
            "TOTP code accepted 4 minutes after generation",
            title="2FA expired code accepted",
            sector="fintech",
        )
        assert result.pattern == "AUTH_FLOW"

    def test_similar_bugs_returned(self, classifier):
        result = classifier.classify(
            "The infusion pump alarm does not sound when IV line is blocked",
            sector="medtech",
        )
        assert len(result.similar_bugs) > 0

    def test_similar_bug_is_raw_001(self, classifier):
        """RAW-001 is the infusion pump alarm seed report — must be top similar."""
        result = classifier.classify(
            "infusion pump alarm silent occlusion",
            sector="medtech",
            n_similar=1,
        )
        assert result.similar_bugs[0].bug_id == "RAW-001"

    def test_duplicate_probability_range(self, classifier):
        result = classifier.classify("button broken", title="UI bug")
        assert 0.0 <= result.duplicate_probability <= 1.0

    def test_exact_seed_report_high_duplicate_prob(self, classifier):
        """Submitting a known seed report should yield high duplicate probability."""
        result = classifier.classify(
            "The occlusion alarm on the infusion pump display doesn't sound when the IV line is blocked.",
            title="Infusion pump alarm doesn't trigger",
            sector="medtech",
        )
        # Should be a duplicate of RAW-001
        assert result.duplicate_probability > 0.5

    def test_confidence_in_range(self, classifier):
        result = classifier.classify("session timeout not enforced", sector="medtech")
        assert 0.0 <= result.confidence <= 1.0

    def test_add_report_increases_store(self, classifier):
        initial = classifier._store.count()
        classifier.add_report("NEW-001", "New unique bug about XYZ", "UI_REGRESSION")
        assert classifier._store.count() == initial + 1


# ---------------------------------------------------------------------------
# Fallback mode
# ---------------------------------------------------------------------------

class TestFallbackClassifier:
    def test_fallback_returns_result(self, fallback_classifier):
        result = fallback_classifier.classify("login fails on mobile", title="Login bug")
        assert result.classified_by == "rule-based-fallback"

    def test_fallback_pattern_valid(self, fallback_classifier, seed_reports):
        valid_patterns = {
            "AUTH_FLOW", "DATA_VALIDATION", "UI_REGRESSION", "DATA_INTEGRITY",
            "PERFORMANCE", "SAFETY_CRITICAL", "COMPLIANCE_REGULATORY", "SECURITY", "INTEGRATION"
        }
        for raw in seed_reports:
            result = fallback_classifier.classify(raw["description"], title=raw.get("title"))
            assert result.pattern in valid_patterns, f"{raw['id']}: {result.pattern}"


# ---------------------------------------------------------------------------
# Property-based
# ---------------------------------------------------------------------------

class TestClassifierProperties:
    _VALID_PATTERNS = {
        "AUTH_FLOW", "DATA_VALIDATION", "UI_REGRESSION", "DATA_INTEGRITY",
        "PERFORMANCE", "SAFETY_CRITICAL", "COMPLIANCE_REGULATORY", "SECURITY", "INTEGRATION"
    }

    @given(text=st.text(min_size=1, max_size=300).filter(lambda s: s.strip()))
    @settings(max_examples=40)
    def test_keyword_always_returns_valid_pattern(self, text):
        patterns = _load_pattern_library()
        result = _classify_keyword(text, patterns)
        assert result in self._VALID_PATTERNS
