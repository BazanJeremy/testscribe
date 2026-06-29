"""Unit tests for ComplianceTagger — IEC 62304 (medtech) + PSD2/DORA (fintech)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agents.compliance_tagger import (
    ComplianceTagger,
    ComplianceResult,
    _tag_medtech,
    _tag_fintech,
)


@pytest.fixture
def tagger():
    return ComplianceTagger(force_fallback=True)


# ---------------------------------------------------------------------------
# IEC 62304 — Medtech
# ---------------------------------------------------------------------------

class TestMedtechTagging:
    def test_alarm_bug_is_class_c(self, tagger):
        result = tagger.tag(
            "The infusion pump alarm does not sound on occlusion",
            sector="medtech", pattern="SAFETY_CRITICAL", severity_priority="critical"
        )
        assert result.medtech is not None
        assert result.medtech.iec_62304_class == "C"

    def test_class_c_requires_change_control(self, tagger):
        result = tagger.tag(
            "Infusion pump alarm silent", sector="medtech",
            pattern="SAFETY_CRITICAL", severity_priority="critical"
        )
        assert result.medtech.change_control_required is True

    def test_audit_log_is_class_b(self, tagger):
        result = tagger.tag(
            "Audit log missing entries after crash",
            sector="medtech", pattern="DATA_INTEGRITY", severity_priority="high"
        )
        assert result.medtech.iec_62304_class in ("B", "C")

    def test_administrative_bug_is_class_a(self, tagger):
        result = tagger.tag(
            "Dark mode toggle resets on page reload",
            sector="medtech", pattern="UI_REGRESSION", severity_priority="low"
        )
        assert result.medtech.iec_62304_class == "A"

    def test_class_a_no_change_control(self, tagger):
        result = tagger.tag(
            "Font size too small on report page",
            sector="medtech", pattern="UI_REGRESSION", severity_priority="low"
        )
        assert result.medtech.change_control_required is False

    def test_dicom_scanner_detects_soup(self, tagger):
        result = tagger.tag(
            "DICOM images from Siemens scanner load incorrectly",
            sector="medtech", pattern="INTEGRATION", severity_priority="medium"
        )
        assert result.medtech.soup_impact is True

    def test_internal_code_no_soup(self, tagger):
        result = tagger.tag(
            "The login form does not validate empty password",
            sector="medtech", pattern="AUTH_FLOW", severity_priority="medium"
        )
        assert result.medtech.soup_impact is False

    def test_traceability_tag_not_empty(self, tagger):
        result = tagger.tag(
            "Session timeout not enforced", sector="medtech",
            pattern="AUTH_FLOW", severity_priority="high"
        )
        assert len(result.medtech.traceability_tag) > 0

    def test_tagged_by_rule_based(self, tagger):
        result = tagger.tag("Bug in alarm system", sector="medtech")
        assert result.tagged_by == "rule-based-fallback"

    def test_all_medtech_seeds_classify_without_error(self, tagger, medtech_reports):
        for raw in medtech_reports:
            result = tagger.tag(
                raw["description"], sector="medtech",
                title=raw.get("title"), severity_priority="medium"
            )
            assert result.medtech is not None
            assert result.medtech.iec_62304_class in ("A", "B", "C")


# ---------------------------------------------------------------------------
# PSD2 / DORA — Fintech
# ---------------------------------------------------------------------------

class TestFintechTagging:
    def test_2fa_maps_to_psd2_art97(self, tagger):
        result = tagger.tag(
            "TOTP code accepted after expiry",
            sector="fintech", pattern="AUTH_FLOW",
            severity_priority="high", title="2FA expired code accepted"
        )
        assert result.fintech is not None
        assert result.fintech.psd2_article is not None
        assert "97" in result.fintech.psd2_article

    def test_wire_transfer_maps_to_psd2(self, tagger):
        result = tagger.tag(
            "Negative amount accepted in wire transfer",
            sector="fintech", pattern="DATA_VALIDATION", severity_priority="high"
        )
        assert result.fintech.psd2_article is not None

    def test_notification_not_sent_maps_to_psd2(self, tagger):
        result = tagger.tag(
            "Push notification for large transaction not sent",
            sector="fintech", pattern="COMPLIANCE_REGULATORY", severity_priority="high"
        )
        assert "97" in (result.fintech.psd2_article or "")

    def test_account_freeze_bypass_flags_aml(self, tagger):
        result = tagger.tag(
            "Account freeze does not block outgoing API transfers",
            sector="fintech", pattern="SECURITY", severity_priority="critical"
        )
        assert result.fintech.aml_flag is True

    def test_critical_bug_is_dora_high(self, tagger):
        result = tagger.tag(
            "Payment processing completely broken",
            sector="fintech", pattern="DATA_VALIDATION", severity_priority="critical"
        )
        assert result.fintech.dora_risk_level == "high"

    def test_low_impact_bug_is_dora_low(self, tagger):
        result = tagger.tag(
            "Currency symbol displayed incorrectly in tooltip",
            sector="fintech", pattern="UI_REGRESSION", severity_priority="low"
        )
        assert result.fintech.dora_risk_level == "low"

    def test_critical_requires_incident_reporting(self, tagger):
        result = tagger.tag(
            "Session persists after password change on all devices",
            sector="fintech", pattern="SECURITY", severity_priority="critical"
        )
        assert result.fintech.incident_reporting_required is True

    def test_low_severity_no_incident_reporting(self, tagger):
        result = tagger.tag(
            "Tooltip text is truncated on mobile",
            sector="fintech", pattern="UI_REGRESSION", severity_priority="low"
        )
        assert result.fintech.incident_reporting_required is False

    def test_all_fintech_seeds_classify_without_error(self, tagger, fintech_reports):
        for raw in fintech_reports:
            result = tagger.tag(
                raw["description"], sector="fintech",
                title=raw.get("title"), severity_priority="medium"
            )
            assert result.fintech is not None
            assert result.fintech.dora_risk_level in ("low", "medium", "high")


# ---------------------------------------------------------------------------
# Generic sector
# ---------------------------------------------------------------------------

class TestGenericSector:
    def test_generic_returns_no_compliance_tags(self, tagger):
        result = tagger.tag("Button broken", sector="generic")
        assert result.medtech is None
        assert result.fintech is None
        assert result.sector == "generic"
