# ADR-003 — Severity Model: CVSS-Lite for QA Contexts

**Date:** 2026-06  
**Status:** Accepted  
**Deciders:** Jérémy Bazan (Solo)

---

## Context

TestScribe needs a reproducible, defensible severity scoring system for bug reports.
Standard severity labels ("Critical / High / Medium / Low") are subjective and inconsistent
across teams. CVSS v3 is the industry standard for security vulnerabilities but is not
directly applicable to functional QA defects.

## Decision Drivers

- Score must be reproducible: same input → same score, regardless of who runs it
- Must cover both functional defects and security findings
- Must be meaningful to both QA Engineers and compliance officers (IEC 62304, PSD2)
- Must be computable via rule-based logic without an LLM (CI fallback requirement)

## Options Considered

### Option A — Standard CVSS v3
- Well-known, 8 dimensions (Attack Vector, Complexity, Privileges, etc.)
- Designed for security vulnerabilities, not UX or functional regressions
- Over-engineered for most QA defect types

### Option B — Internal 1-5 scale
- Simple, fast, widely used
- Inherently subjective, not auditable, no rationale trail

### Option C — CVSS-Lite (selected)
- 4 QA-adapted dimensions: Functional Impact, Reproducibility, User Scope, Regression Type
- Weighted sum produces 0-10 score with defined thresholds
- Each dimension maps to an auditable label traceable in compliance reports
- Compatible with IEC 62304 severity classification (A/B/C) and PSD2 operational risk levels

## Scoring Matrix

| Dimension        | Weight | Values |
|------------------|--------|--------|
| Functional Impact | 4.0   | none=0.0 / partial=0.5 / full=1.0 |
| Reproducibility  | 2.5    | always=1.0 / sometimes=0.6 / rare=0.3 |
| User Scope       | 2.0    | single=0.2 / group=0.6 / all=1.0 |
| Regression Type  | 1.5    | new=0.8 / known=0.5 / reopened=1.0 |

**Thresholds:** critical ≥ 8.0 · high ≥ 6.5 · medium ≥ 4.0 · low < 4.0

## Consequences

- **Positive:** Auditable, reproducible, defensible in medtech/fintech compliance reviews
- **Positive:** Claude can score and explain; rule-based fallback produces identical schema
- **Positive:** Threshold calibrated so safety-critical defects (alarm silence, data loss) reliably reach "critical"
- **Negative:** Simpler than full CVSS; may need extension for pure security vulnerability workflows
- **Mitigation:** ComplianceTag agent maps severity output to sector-specific risk levels independently
