"""Unit tests for ReportEnricher — fallback mode, no API key required."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agents.report_enricher import (
    ReportEnricher,
    _build_steps,
    _extract_environment,
    _generate_title,
    enrich_rule_based,
)

# ---------------------------------------------------------------------------
# Environment extraction
# ---------------------------------------------------------------------------

class TestExtractEnvironment:
    def test_detects_firefox(self):
        env = _extract_environment("Tested on Firefox 126")
        assert env.get("browser") == "Firefox"

    def test_detects_chrome(self):
        env = _extract_environment("Reproduced on Chrome 124 on Windows 11")
        assert env.get("browser") == "Chrome"

    def test_detects_windows_11(self):
        env = _extract_environment("Windows 11 machine")
        assert env.get("os") == "Windows 11"

    def test_detects_ios(self):
        env = _extract_environment("iPhone SE running iOS 17")
        assert env.get("os") == "iOS"

    def test_detects_staging(self):
        env = _extract_environment("Tested on staging environment")
        assert env.get("environment") == "Staging"

    def test_detects_version_number(self):
        env = _extract_environment("App version 3.4.1 on Android")
        assert env.get("version") == "3.4.1"

    def test_falls_back_to_unspecified(self):
        env = _extract_environment("The button does not work")
        assert "os" in env
        assert env["os"] == "unspecified"

    def test_no_duplicate_keys(self):
        env = _extract_environment("Chrome on Windows 11 Chrome version 124")
        assert len([k for k in env if k == "browser"]) == 1


# ---------------------------------------------------------------------------
# Step generation
# ---------------------------------------------------------------------------

class TestBuildSteps:
    def test_returns_at_least_three_steps(self):
        steps = _build_steps("Login broken", "The login page shows an error.", "auth")
        assert len(steps) >= 3

    def test_first_step_is_given(self):
        steps = _build_steps("Crash", "App crashes on open.", "dashboard")
        assert steps[0].lower().startswith("given")

    def test_last_step_is_then_like(self):
        steps = _build_steps("Error", "Error on submit.", "form")
        assert steps[-1].lower().startswith("then")

    def test_numbered_description_extracts_steps(self):
        desc = "1. Navigate to login. 2. Enter credentials. 3. Click submit."
        steps = _build_steps("Login", desc, "auth")
        assert len(steps) >= 3

    def test_component_appears_in_given(self):
        steps = _build_steps("Bug", "Something is wrong.", "payment-processing")
        assert "payment processing" in steps[0].lower()


# ---------------------------------------------------------------------------
# Title generation
# ---------------------------------------------------------------------------

class TestGenerateTitle:
    def test_uses_provided_title_when_long_enough(self):
        title = _generate_title("Login button broken on Firefox", "desc")
        assert "Login" in title

    def test_falls_back_to_description_when_title_short(self):
        title = _generate_title("Bug", "The payment form crashes on submit.")
        assert len(title) > 5

    def test_none_title_uses_description(self):
        title = _generate_title(None, "Search results are wrong.")
        assert "Search" in title

    def test_title_max_200_chars(self):
        long_title = "A" * 300
        title = _generate_title(long_title, "desc")
        assert len(title) <= 200


# ---------------------------------------------------------------------------
# Rule-based enricher full output
# ---------------------------------------------------------------------------

class TestEnrichRuleBased:
    def test_returns_enrichment_result(self, firefox_report):
        result = enrich_rule_based(
            firefox_report.description,
            firefox_report.title,
            firefox_report.component,
        )
        assert result is not None

    def test_enriched_by_is_rule_based(self, firefox_report):
        result = enrich_rule_based(firefox_report.description, firefox_report.title)
        assert result.enriched_by == "rule-based-fallback"

    def test_title_is_non_empty(self, firefox_report):
        result = enrich_rule_based(firefox_report.description, firefox_report.title)
        assert len(result.title) > 0

    def test_summary_is_non_empty(self, firefox_report):
        result = enrich_rule_based(firefox_report.description)
        assert len(result.summary) > 0

    def test_reproduction_steps_non_empty(self, firefox_report):
        result = enrich_rule_based(firefox_report.description, firefox_report.title)
        assert len(result.reproduction_steps) >= 1

    def test_environment_is_dict(self, firefox_report):
        result = enrich_rule_based(firefox_report.description)
        assert isinstance(result.environment, dict)

    def test_firefox_detected_in_env(self, firefox_report):
        result = enrich_rule_based(firefox_report.description)
        assert result.environment.get("browser") == "Firefox"

    def test_confidence_score_valid_range(self, firefox_report):
        result = enrich_rule_based(firefox_report.description)
        assert 0.0 <= result.confidence_score <= 1.0

    def test_expected_result_non_empty(self, firefox_report):
        result = enrich_rule_based(firefox_report.description, firefox_report.title)
        assert len(result.expected_result) > 0

    def test_actual_result_non_empty(self, firefox_report):
        result = enrich_rule_based(firefox_report.description)
        assert len(result.actual_result) > 0


# ---------------------------------------------------------------------------
# ReportEnricher class (forced fallback)
# ---------------------------------------------------------------------------

class TestReportEnricher:
    def test_force_fallback_uses_rule_based(self, enricher, firefox_report):
        result = enricher.enrich(
            firefox_report.description,
            firefox_report.title,
            firefox_report.component,
        )
        assert result.enriched_by == "rule-based-fallback"

    def test_no_api_key_uses_rule_based(self, firefox_report):
        enricher = ReportEnricher(api_key=None, force_fallback=False)
        result = enricher.enrich(firefox_report.description)
        assert result.enriched_by == "rule-based-fallback"

    def test_minimal_description_no_crash(self, minimal_report):
        enricher = ReportEnricher(force_fallback=True)
        result = enricher.enrich(minimal_report.description)
        assert result is not None
        assert result.enriched_by == "rule-based-fallback"

    def test_all_seed_reports_enrich_without_error(self, seed_reports, enricher):
        """All 30 seed reports must enrich successfully with fallback."""
        errors = []
        for raw in seed_reports:
            try:
                result = enricher.enrich(
                    raw["description"],
                    raw.get("title"),
                    raw.get("component"),
                )
                assert result.enriched_by == "rule-based-fallback"
            except Exception as e:
                errors.append(f'{raw["id"]}: {e}')
        assert errors == [], f"Enrichment errors: {errors}"


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

class TestEnricherProperties:
    @given(
        description=st.text(min_size=1, max_size=500).filter(lambda s: s.strip()),
    )
    @settings(max_examples=50)
    def test_any_description_produces_valid_result(self, description):
        result = enrich_rule_based(description)
        assert result.title is not None
        assert result.enriched_by == "rule-based-fallback"
        assert isinstance(result.reproduction_steps, list)
        assert len(result.reproduction_steps) >= 1
        assert 0.0 <= result.confidence_score <= 1.0

    @given(
        title=st.one_of(st.none(), st.text(min_size=0, max_size=200)),
        description=st.text(min_size=1, max_size=1000).filter(lambda s: s.strip()),
    )
    @settings(max_examples=30)
    def test_title_always_within_length(self, title, description):
        result = enrich_rule_based(description, title)
        assert len(result.title) <= 200
