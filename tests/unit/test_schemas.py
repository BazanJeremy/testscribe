"""Unit tests for Pydantic schemas — validation boundaries and edge cases."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas import RawReport, EnrichedReport, CVSSLiteScore, ComplianceTag


# ---------------------------------------------------------------------------
# RawReport
# ---------------------------------------------------------------------------

class TestRawReport:
    def test_minimal_valid_report(self):
        r = RawReport(description="Something is broken")
        assert r.description == "Something is broken"
        assert r.sector is None

    def test_whitespace_only_description_rejected(self):
        with pytest.raises(ValidationError):
            RawReport(description="   ")

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            RawReport(description="")

    def test_description_stripped(self):
        r = RawReport(description="  trailing spaces  ")
        assert r.description == "trailing spaces"

    def test_valid_sectors_accepted(self):
        for sector in ("medtech", "fintech", "generic"):
            r = RawReport(description="Bug", sector=sector)
            assert r.sector == sector

    def test_sector_case_insensitive(self):
        r = RawReport(description="Bug", sector="MedTech")
        assert r.sector == "medtech"

    def test_invalid_sector_rejected(self):
        with pytest.raises(ValidationError):
            RawReport(description="Bug", sector="aerospace")

    def test_description_max_length(self):
        with pytest.raises(ValidationError):
            RawReport(description="x" * 5001)

    def test_optional_fields_default_none(self):
        r = RawReport(description="Bug")
        assert r.id is None
        assert r.title is None
        assert r.component is None
        assert r.reporter is None


# ---------------------------------------------------------------------------
# CVSSLiteScore
# ---------------------------------------------------------------------------

class TestCVSSLiteScore:
    def _valid(self, **kwargs) -> CVSSLiteScore:
        defaults = dict(
            functional_impact="partial",
            reproducibility="always",
            user_scope="single",
            regression_type="new",
            score=5.0,
            priority="medium",
            rationale="Test rationale",
        )
        defaults.update(kwargs)
        return CVSSLiteScore(**defaults)

    def test_valid_score(self):
        s = self._valid(score=7.5, priority="high")
        assert s.score == 7.5

    def test_score_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(score=-0.1)

    def test_score_above_ten_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(score=10.1)

    def test_invalid_priority_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(priority="severe")  # type: ignore

    def test_invalid_impact_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(functional_impact="total")  # type: ignore


# ---------------------------------------------------------------------------
# ComplianceTag
# ---------------------------------------------------------------------------

class TestComplianceTag:
    def test_generic_sector(self):
        tag = ComplianceTag(sector="generic")
        assert tag.medtech is None
        assert tag.fintech is None

    def test_invalid_sector_rejected(self):
        with pytest.raises(ValidationError):
            ComplianceTag(sector="healthcare")  # type: ignore
