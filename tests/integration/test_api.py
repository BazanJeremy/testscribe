"""Integration tests — Flask API contract + end-to-end pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from api.app import app as flask_app


@pytest.fixture(scope="module")
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clear_store():
    """Reset in-memory store before each integration test."""
    import api.app as app_module
    app_module._REPORT_STORE.clear()
    app_module._orchestrator = None
    yield
    app_module._REPORT_STORE.clear()
    app_module._orchestrator = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_has_status_ok(self, client):
        data = client.get("/health").get_json()
        assert data["status"] == "ok"

    def test_health_has_timestamp(self, client):
        data = client.get("/health").get_json()
        assert "timestamp" in data


# ---------------------------------------------------------------------------
# POST /api/enrich
# ---------------------------------------------------------------------------

class TestEnrichEndpoint:
    def test_enrich_returns_201(self, client):
        r = client.post("/api/enrich", json={
            "description": "Login button broken on Firefox"
        })
        assert r.status_code == 201

    def test_enrich_response_has_required_fields(self, client):
        r = client.post("/api/enrich", json={
            "description": "Login button broken",
            "sector": "fintech"
        })
        data = r.get_json()
        for field in ("id", "title", "pattern", "severity", "compliance", "enriched_by"):
            assert field in data, f"Missing field: {field}"

    def test_enrich_severity_has_priority(self, client):
        r = client.post("/api/enrich", json={"description": "App crashes on startup"})
        data = r.get_json()
        assert data["severity"]["priority"] in ("low", "medium", "high", "critical")

    def test_enrich_compliance_sector_matches_input(self, client):
        r = client.post("/api/enrich", json={
            "description": "Infusion pump alarm silent",
            "sector": "medtech"
        })
        data = r.get_json()
        assert data["compliance"]["sector"] == "medtech"

    def test_enrich_medtech_has_iec_class(self, client):
        r = client.post("/api/enrich", json={
            "description": "Infusion pump alarm does not sound",
            "sector": "medtech"
        })
        data = r.get_json()
        assert data["compliance"]["medtech"]["iec_62304_class"] in ("A", "B", "C")

    def test_enrich_fintech_has_dora_level(self, client):
        r = client.post("/api/enrich", json={
            "description": "TOTP 2FA code accepted after expiry",
            "sector": "fintech"
        })
        data = r.get_json()
        assert data["compliance"]["fintech"]["dora_risk_level"] in ("low", "medium", "high")

    def test_empty_body_returns_400(self, client):
        r = client.post("/api/enrich", data="not json",
                        content_type="application/json")
        assert r.status_code == 400

    def test_empty_description_returns_422(self, client):
        r = client.post("/api/enrich", json={"description": "   "})
        assert r.status_code == 422

    def test_invalid_sector_returns_422(self, client):
        r = client.post("/api/enrich", json={
            "description": "Bug found", "sector": "aerospace"
        })
        assert r.status_code == 422

    def test_enriched_report_stored_in_list(self, client):
        client.post("/api/enrich", json={"description": "Bug found"})
        r = client.get("/api/reports")
        data = r.get_json()
        assert data["total"] == 1


# ---------------------------------------------------------------------------
# POST /api/enrich/batch
# ---------------------------------------------------------------------------

class TestBatchEnrichEndpoint:
    def test_batch_enrich_two_reports(self, client):
        r = client.post("/api/enrich/batch", json=[
            {"description": "Login broken", "sector": "fintech"},
            {"description": "Alarm silent", "sector": "medtech"},
        ])
        data = r.get_json()
        assert r.status_code == 201
        assert data["enriched"] == 2
        assert len(data["reports"]) == 2

    def test_batch_with_invalid_item_reports_errors(self, client):
        r = client.post("/api/enrich/batch", json=[
            {"description": "Valid report"},
            {"description": ""},
        ])
        data = r.get_json()
        assert data["enriched"] == 1
        assert len(data["errors"]) == 1

    def test_batch_requires_array(self, client):
        r = client.post("/api/enrich/batch", json={"description": "Not a list"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/reports
# ---------------------------------------------------------------------------

class TestReportsEndpoint:
    def test_empty_store_returns_zero(self, client):
        r = client.get("/api/reports")
        assert r.get_json()["total"] == 0

    def test_filter_by_sector(self, client):
        client.post("/api/enrich", json={"description": "Login broken", "sector": "fintech"})
        client.post("/api/enrich", json={"description": "Alarm silent", "sector": "medtech"})
        r = client.get("/api/reports?sector=fintech")
        data = r.get_json()
        assert data["total"] == 1


# ---------------------------------------------------------------------------
# GET /api/trends
# ---------------------------------------------------------------------------

class TestTrendsEndpoint:
    def test_trends_on_empty_store(self, client):
        r = client.get("/api/trends")
        data = r.get_json()
        assert data["total_reports"] == 0

    def test_trends_counts_patterns(self, client):
        client.post("/api/enrich", json={"description": "Login broken"})
        r = client.get("/api/trends")
        data = r.get_json()
        assert data["total_reports"] == 1
        assert len(data["patterns"]) >= 1

    def test_trends_has_priorities_and_sectors(self, client):
        client.post("/api/enrich", json={"description": "Bug report", "sector": "medtech"})
        data = client.get("/api/trends").get_json()
        assert "priorities" in data
        assert "sectors" in data


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_dashboard_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_dashboard_contains_testscribe(self, client):
        r = client.get("/")
        assert b"TestScribe" in r.data

    def test_dashboard_escapes_report_text_before_innerhtml(self, client):
        # The table and the detail modal are built with innerHTML. Free text
        # that comes from a report (title, steps, summary, environment...) was
        # interpolated raw: a title holding markup ran as markup (stored XSS).
        html = client.get("/").get_data(as_text=True)
        assert "function esc(" in html
        raw_interpolations = [
            "${r.title",
            "${r.pattern",
            "${r.summary",
            "<li>${s}</li>",
            "${b.bug_id}",
            "${b.pattern}",
            "${m.traceability_tag}",
            "${f.psd2_article",
            "${r.compliance.fintech.psd2_article}",
            "${sev.rationale",
            "<p>${k}: ${v}</p>",
        ]
        assert [raw for raw in raw_interpolations if raw in html] == []


class TestRunConfig:
    """How ``python src/api/app.py`` binds — the Docker image runs exactly that."""

    def test_defaults_are_local_and_debugger_off(self, monkeypatch):
        from api.app import run_config

        for name in ("FLASK_HOST", "FLASK_PORT", "FLASK_DEBUG"):
            monkeypatch.delenv(name, raising=False)
        assert run_config() == {"host": "127.0.0.1", "port": 5000, "debug": False}

        # A container must listen on all interfaces to be reachable through
        # a published port; the debugger stays opt-in.
        monkeypatch.setenv("FLASK_HOST", "0.0.0.0")
        monkeypatch.setenv("FLASK_PORT", "8080")
        monkeypatch.setenv("FLASK_DEBUG", "1")
        assert run_config() == {"host": "0.0.0.0", "port": 8080, "debug": True}
