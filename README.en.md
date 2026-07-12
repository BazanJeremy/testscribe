# TestScribe

**AI-powered bug report enricher: *"button doesn't work"* → structured defect report with CVSS-lite severity, IEC 62304 classification, and semantic duplicate detection — in under 100ms.**

[![CI](https://github.com/BazanJeremy/testscribe/actions/workflows/ci.yml/badge.svg)](https://github.com/BazanJeremy/testscribe/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-144%20passing-brightgreen?logo=pytest)](tests/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?logo=python)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

> 🇫🇷 [Version française](README.md)

**AI proposes, the QA decides.** TestScribe is the downstream link of an AI-assisted quality workflow: it pre-qualifies incoming defects — the judgement stays human. Downstream, the enriched reports serve as an evaluation use case for [EvalForge](https://github.com/BazanJeremy/EvalForge) — soft interop, no runtime coupling.

---

## The Problem

Every QA team receives bug reports like these every week:

```
"button doesn't work"
"page crashes"
"search not working sometimes"
```

These reports are **useless without context**. A QA engineer spends 10–30 minutes turning each one into a structured defect ticket. TestScribe automates that enrichment using a four-agent AI pipeline, with deterministic fallback so it runs in CI without an API key.

**Inspired by Andrej Karpathy's Software 2.0 principle**: replacing manual, rule-based work with learned representations — here applied to QA artefacts.

---

## What It Does

```
Raw input:  "The infusion pump alarm doesn't sound when the line is blocked."

Output:
  Title:   Infusion pump alarm silent on IV occlusion
  Pattern: SAFETY_CRITICAL
  Steps:   Given the user has access to alarm-subsystem
           When The occlusion alarm does not sound when IV line is blocked
           Then the observed behaviour differs from expected
  CVSS-lite score: 9.0 / 10  →  CRITICAL
  IEC 62304 Class: C  (change control required, SOUP impact: No)
  Similar bugs: RAW-001 (0.94 similarity)  →  Duplicate probability: 89%
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1 — INGESTION                                            │
│  Raw text · JSON · CSV · Flask POST /api/enrich                 │
└─────────────────┬───────────────────────────────────────────────┘
                  │  RawReport (Pydantic v2 validated)
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Enrichment Orchestrator  (src/core/orchestrator.py)            │
│  routes · normalises · merges all agent outputs                 │
└──────┬─────────────┬──────────────┬──────────────┬─────────────┘
       │             │              │              │
       ▼             ▼              ▼              ▼
┌──────────┐ ┌────────────┐ ┌──────────────┐ ┌───────────────┐
│ Report   │ │ Severity   │ │ Pattern      │ │ Compliance    │
│ Enricher │ │ Scorer     │ │ Classifier   │ │ Tagger        │
│          │ │            │ │              │ │               │
│ steps    │ │ CVSS-lite  │ │ TF-IDF +     │ │ IEC 62304 A/B/C│
│ env      │ │ 0–10 score │ │ ChromaDB RAG │ │ PSD2 / DORA   │
│ summary  │ │ priority   │ │ dup detect   │ │ AML flag      │
└──────────┘ └────────────┘ └──────┬───────┘ └───────────────┘
                                   │
                         ┌─────────▼─────────┐
                         │  ChromaDB          │
                         │  TF-IDF embeddings │
                         │  semantic search   │
                         └───────────────────┘
  ┌── FALLBACK ─────────────────────────────────────────────────┐
  │  All agents: deterministic rule-based fallback               │
  │  CI runs green without ANTHROPIC_API_KEY                     │
  └─────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 3 — OUTPUT                                               │
│  EnrichedReport (Pydantic v2) · Flask API · Dashboard          │
└─────────────────────────────────────────────────────────────────┘
```

---

## The QA's Role — AI Proposes, the QA Decides

Every TestScribe output is a **proposal**, never a decision:

| TestScribe output | Status | The decision that stays human |
|---|---|---|
| CVSS-lite score + priority | pre-ranking | the ticket's final severity |
| Given/When/Then steps | reproduction proposal | actually reproducing the bug |
| Duplicate probability | signal | merging tickets or not |
| IEC 62304 / PSD2-DORA tags | pre-qualification | the regulatory position — never submitted to an audit as-is |

**Full traceability**: every enriched report carries an `enriched_by` field (`claude-sonnet-4-6` or `rule-based-fallback`) and a `confidence_score`. The QA always knows *who* produced *what*, with what confidence. The exact opposite of a black box.

### What TestScribe does NOT do

- It does not decide the final severity.
- It does not close any ticket.
- It does not replace manual bug reproduction.
- It does not issue regulatory compliance opinions.
- It does not generate test cases.

TestScribe removes the writing and pre-qualification time — not the judgement.

---

## AI Skills Demonstrated

| Skill | Where |
|-------|-------|
| **LLM structured output** | All agents: Claude returns validated JSON via Pydantic v2 |
| **RAG (Retrieval-Augmented Generation)** | `PatternClassifier`: TF-IDF embeddings → ChromaDB → semantic neighbour search |
| **Deterministic fallback** | Every agent has a rule-based fallback; CI never needs an API key |
| **Multi-agent orchestration** | `Orchestrator` coordinates 4 specialised agents into a single pipeline |
| **Sector-specific compliance** | `ComplianceTagger`: IEC 62304 (medtech) + PSD2/DORA (fintech) |
| **Property-based testing** | Hypothesis fuzzing on all agents and schemas |

---

## Tech Stack

```
Python 3.12       Pydantic v2      Flask 3.x
Anthropic SDK     ChromaDB 0.5     scikit-learn (TF-IDF)
Pytest            Hypothesis       Allure
GitHub Actions    Docker           sentence-transformers (optional)
```

---

## Bugs caught by the test suite

This project follows the principle: **tests that find real bugs are assets, not noise**.

### S1 — Two bugs caught during initial build

| Bug | Test that caught it | Root cause | Fix |
|-----|---------------------|------------|-----|
| `"not always"` → scored as `always` reproducibility | `test_intermittent_is_sometimes` | `_ALWAYS_REPRO_KEYWORDS` regex matched `always` inside `"not always"` | Added negative lookbehind: `(?<!not )\balways\b` |
| Infusion pump alarm → `high` instead of `critical` | `test_alarm_bug_scores_critical` | Critical threshold too conservative (8.5) | Lowered to 8.0 — aligns with medtech safety expectations |

### S2 — One bug caught during compliance agent build

| Bug | Test that caught it | Root cause | Fix |
|-----|---------------------|------------|-----|
| UI cosmetic bug → IEC 62304 class B + `change_control=True` | `test_class_a_no_change_control` | `_IEC_CLASS_B_RE` matched generic word `report` in "report page" | Tightened regex to `patient.report`, `audit.log`, `medical.image`; class A always sets `change_control=False` |

---

## Project Structure

```
testscribe/
├── src/
│   ├── agents/
│   │   ├── report_enricher.py     # Agent 1: Given/When/Then + env detection
│   │   ├── severity_scorer.py     # Agent 2: CVSS-lite 0–10 scoring
│   │   ├── pattern_classifier.py  # Agent 3: RAG + ChromaDB semantic search
│   │   └── compliance_tagger.py   # Agent 4: IEC 62304 + PSD2/DORA
│   ├── schemas/
│   │   ├── raw_report.py          # Pydantic v2 input validation
│   │   └── enriched_report.py     # Pydantic v2 structured output
│   ├── core/
│   │   ├── orchestrator.py        # Pipeline coordinator
│   │   ├── embedder.py            # TF-IDF / sentence-transformers facade
│   │   └── vector_store.py        # ChromaDB client (external embeddings)
│   ├── api/
│   │   └── app.py                 # Flask REST API + dashboard
│   └── data/
│       ├── seed_reports.json      # 30 realistic bug reports (medtech/fintech/generic)
│       └── pattern_library.json   # 9 pattern definitions + keywords
├── tests/
│   ├── unit/                      # 121 unit tests + property-based (Hypothesis)
│   ├── integration/               # 23 API contract tests
│   └── conftest.py
├── docs/
│   ├── ADR-001-chromadb-vs-faiss.md
│   ├── ADR-002-embeddings-choice.md
│   └── ADR-003-cvss-lite-scoring.md
├── demo.py                        # Standalone demo — no API key required
├── .github/workflows/ci.yml       # CI: lint → unit → integration → Allure
├── docker-compose.yml
└── requirements.txt
```

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/BazanJeremy/testscribe.git
cd testscribe
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt

# Run the demo (no API key needed)
python demo.py
python demo.py --sector medtech --verbose
python demo.py --sector fintech --json-out enriched.json

# Run tests
python -m pytest tests/

# Start the dashboard
python src/api/app.py
# → http://localhost:5000

# With Claude API (optional — agents fall back automatically without it)
$env:ANTHROPIC_API_KEY="sk-ant-..."
python src/api/app.py
```

### Docker

```bash
docker-compose up
# → http://localhost:5000
```

---

## API Reference

### `POST /api/enrich`

```json
{
  "description": "The login button does nothing on Firefox",
  "title": "Login button non-responsive",
  "component": "authentication",
  "sector": "fintech"
}
```

**Response 201:**

```json
{
  "id": "TS-A1B2C3D4",
  "title": "Login button non-responsive on Firefox",
  "pattern": "AUTH_FLOW",
  "severity": { "score": 5.1, "priority": "medium", "functional_impact": "partial" },
  "compliance": { "sector": "fintech", "fintech": { "psd2_article": "Art.97 — Session Security", "dora_risk_level": "medium" } },
  "reproduction_steps": ["Given the user navigates to authentication", "When Login button does nothing on Firefox", "Then the observed behaviour differs from expected"],
  "similar_bugs": [{ "bug_id": "RAW-020", "similarity_score": 0.72, "pattern": "AUTH_FLOW" }],
  "duplicate_probability": 0.42,
  "enriched_by": "rule-based-fallback",
  "confidence_score": 0.57
}
```

### `POST /api/enrich/batch`

Send an array of report objects. Partial success — each item enriched independently.

### `GET /api/reports?sector=medtech&priority=critical&pattern=SAFETY_CRITICAL`

### `GET /api/trends`

Returns pattern/priority/sector distribution across all enriched reports.

---

## Supported Patterns

| Pattern | Description |
|---------|-------------|
| `SAFETY_CRITICAL` | Patient safety, alarm failures, device malfunction (medtech) |
| `SECURITY` | Injection, bypass, privilege escalation |
| `AUTH_FLOW` | Login, session, 2FA, token, password |
| `DATA_VALIDATION` | Input validation, boundary conditions, IBAN, format |
| `DATA_INTEGRITY` | Data loss, duplication, sync failures |
| `COMPLIANCE_REGULATORY` | Audit, e-signature, PSD2 notification, reporting |
| `PERFORMANCE` | Timeouts, freezes, crashes under load |
| `INTEGRATION` | Third-party API, DICOM, HL7, feed failures |
| `UI_REGRESSION` | Layout, rendering, responsive design |

---

## Architectural Decisions

- **[ADR-001](docs/ADR-001-chromadb-vs-faiss.md)** — ChromaDB over FAISS: simpler API, persistent storage, filter-by-metadata for sector isolation
- **[ADR-002](docs/ADR-002-embeddings-choice.md)** — TF-IDF default with sentence-transformers upgrade path: CI-safe without network, neural available in production
- **[ADR-003](docs/ADR-003-cvss-lite-scoring.md)** — CVSS-lite adapted for QA: 4 dimensions (functional_impact, reproducibility, user_scope, regression_type) calibrated against medtech safety expectations

---

## Sector Adaptations

### Medtech (IEC 62304)

- Class C: alarm failures, dosage errors, vital signs, infusion pumps → change control required
- Class B: authentication, audit logs, e-signatures, DICOM → change control required
- Class A: UI/cosmetic, administrative → no change control
- SOUP (Software of Unknown Provenance) detection: DICOM viewers, HL7, third-party scanners

### Fintech (PSD2 / DORA)

- PSD2 article mapping: Art.97 (SCA, session), Art.36 (payments), Art.80 (IBAN), Art.88 (fraud)
- DORA operational risk level: high for payment/session failures, medium for data accuracy
- AML flag: account freeze bypass, large transaction notification failures

---

## Known Limitations

- Fallback heuristics are calibrated on 30 seed reports — not an industrial corpus.
- TF-IDF captures lexical similarity, not fine-grained semantics. Deliberate trade-off ([ADR-002](docs/ADR-002-embeddings-choice.md)): zero network dependency in CI, deterministic results; the sentence-transformers upgrade path is documented.
- Compliance tags are a qualification aid, not a regulatory opinion.
- Fallback mode produces poorer output than LLM mode (keyword rules, no rephrasing).
- Corpus, patterns and outputs are English-only.

---

## Related projects

These tools share the same principles: **deterministic first, AI where it earns its place — the QA stays the arbiter.** All run locally, no API keys required.

| Project | Focus |
|---|---|
| [EvalForge](https://github.com/BazanJeremy/EvalForge) | LLM evaluation & judge calibration |
| [ReleaseGuard](https://github.com/BazanJeremy/ReleaseGuard) | Explainable GO/NO-GO release gate |
| [FlakySense](https://github.com/BazanJeremy/flakysense) | Statistical flaky-test diagnosis |
| [Anomaly Sentinel](https://github.com/BazanJeremy/anomaly-sentinel) | Testing AI anomaly-detection systems (medtech · fintech) |
| [TestScribe](https://github.com/BazanJeremy/testscribe) **← this repo** | AI-assisted bug report enrichment |
| [SkyGuard](https://github.com/BazanJeremy/skyguard) | Security quality gate for critical avionics systems |

## Author

**Jérémy Bazan** — QA Engineer · AI Test Engineering  
ISTQB Foundation v4 · MCP in production  
[LinkedIn](https://www.linkedin.com/in/jeremy-bazan/) · [GitHub](https://github.com/BazanJeremy)  
Lyon, France → Switzerland (Suisse romande) / Full Remote
