"""Shared fixtures for TestScribe test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents import ReportEnricher, SeverityScorer
from schemas import RawReport

DATA_PATH = Path(__file__).parent.parent / "src" / "data" / "seed_reports.json"


@pytest.fixture(scope="session")
def seed_reports() -> list[dict]:
    """All 30 seed raw reports as dicts."""
    with DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def seed_raw_reports(seed_reports) -> list[RawReport]:
    """All 30 seed reports parsed as RawReport models."""
    return [RawReport(**r) for r in seed_reports]


@pytest.fixture(scope="session")
def medtech_reports(seed_reports) -> list[dict]:
    return [r for r in seed_reports if r["sector"] == "medtech"]


@pytest.fixture(scope="session")
def fintech_reports(seed_reports) -> list[dict]:
    return [r for r in seed_reports if r["sector"] == "fintech"]


@pytest.fixture(scope="session")
def generic_reports(seed_reports) -> list[dict]:
    return [r for r in seed_reports if r["sector"] == "generic"]


@pytest.fixture
def enricher() -> ReportEnricher:
    """Enricher in forced fallback mode — no API key needed."""
    return ReportEnricher(force_fallback=True)


@pytest.fixture
def scorer() -> SeverityScorer:
    """Scorer in forced fallback mode — no API key needed."""
    return SeverityScorer(force_fallback=True)


# ---------------------------------------------------------------------------
# Representative single-report fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_report() -> RawReport:
    return RawReport(description="Button doesn't work")


@pytest.fixture
def firefox_report() -> RawReport:
    return RawReport(
        id="TEST-FF-001",
        title="Login button non-responsive on Firefox",
        description=(
            "The login button on the authentication page does nothing when clicked on Firefox 126. "
            "The issue is reproduced every time. Chrome and Safari work fine."
        ),
        component="authentication",
        sector="fintech",
    )


@pytest.fixture
def crash_report() -> RawReport:
    return RawReport(
        id="TEST-CRASH-001",
        title="Dashboard crashes on open",
        description=(
            "The main dashboard crashes immediately upon loading. "
            "A JavaScript error appears in the console: TypeError: Cannot read properties of undefined. "
            "Affects all users on Windows 11 running Chrome 124."
        ),
        component="dashboard",
        sector="generic",
    )


@pytest.fixture
def medtech_report() -> RawReport:
    return RawReport(
        id="TEST-MED-001",
        title="Infusion pump alarm silent on occlusion",
        description=(
            "The occlusion alarm on the infusion pump display does not sound when the IV line is blocked. "
            "Tested with a clamp on the line; alarm LED remained green with no audio alert. "
            "Reproduced consistently in 5 of 5 trials."
        ),
        component="alarm-subsystem",
        sector="medtech",
    )


@pytest.fixture
def security_report() -> RawReport:
    return RawReport(
        id="TEST-SEC-001",
        title="Patient ID field accepts SQL injection",
        description=(
            "The patient ID input field accepts SQL injection strings like ' OR 1=1 -- "
            "without any validation error. Should only allow alphanumeric characters and dashes."
        ),
        component="patient-registration",
        sector="medtech",
    )
