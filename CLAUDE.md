# CLAUDE.md — TestScribe

> AI bug report enricher — multi-agent pipeline turning raw bug reports into enriched, scored, classified, compliance-tagged reports.
> Portfolio project P3 of a 6-project AI Test Engineering portfolio.

## Project State — READ FIRST

- **Status: ✅ COMPLETE and validated in real conditions.**
  - 144/144 tests passing, demo scenario 30/30, Flask dashboard operational.
  - Validated on Windows / Python 3.14. `docker-compose.yml` and CI workflow ready.
- **Maintenance mode.** Default posture: do NOT refactor, restructure, or "improve" unless explicitly asked.
- If a change is requested: **smallest targeted fix**, no broad rewrites.

## Architecture (fixed — do not redesign)

Four agents, each with a **deterministic rule-based fallback** (runs in CI without API keys):

1. **ReportEnricher** — normalizes and enriches raw bug reports.
2. **SeverityScorer** — severity scoring. ⚠️ Critical threshold is **8.0** (was 8.5 — corrected after a test caught misclassification; do not revert).
3. **PatternClassifier** — RAG over ChromaDB with **TF-IDF embeddings** (deliberately chosen over neural embeddings: zero API cost, deterministic, CI-friendly).
4. **ComplianceTagger** — tags reports against **IEC 62304** (medical) and **PSD2** (fintech).

Stack: Python 3.14, Pydantic v2, Flask dashboard, ChromaDB, pytest.

## Known Fixed Bugs — Portfolio Evidence (do not "clean up")

These three bugs were **caught by the test suite**, are documented as evidence of the QA process, and their history must be preserved:

1. Regex lookbehind bug on `ALWAYS_REPRO` pattern.
2. Critical severity threshold corrected 8.5 → 8.0.
3. `IEC_CLASS_B_RE` too generic — cosmetic UI bugs misclassified as IEC 62304 Class B.

Any documentation touching these must keep the narrative: *test caught it → analyzed → fixed → regression-tested*.

## Environment

- OS: Windows 11, shell: PowerShell
- Python 3.14, virtualenv in `.venv`
- Run tests with: `python -m pytest` — **NEVER** bare `pytest`
- Flask dashboard runs locally; ChromaDB persists locally — never scan the Chroma persistence directory (token waste)
- CI: GitHub Actions (free tier, repo private under `BazanJeremy`)

## Architecture Principles (non-negotiable, portfolio-wide)

1. Deterministic fallback on every AI agent — suite green with zero API keys.
2. Pydantic v2 everywhere.
3. ADRs in `docs/adr/`, superseded not edited.
4. Bugs found by tests = portfolio evidence, documented before fixed.

## Conventions

- Codebase, comments, README, ADRs: **professional English**. Conversation: French.
- Small atomic commits, imperative English messages.
- Free/open-source only.
- Report exact errors, fix precisely — the user runs locally and pastes real output.

## What NOT to Do

- No new dependencies, no README regeneration (final, senior-reviewed).
- Do not replace TF-IDF with neural embeddings — the choice is an ADR-backed decision.
- Do not scan `.venv/`, ChromaDB storage, or demo output folders.
