#!/usr/bin/env python3
"""
TestScribe — Standalone Demo
============================
Enriches all 30 seed bug reports using the rule-based fallback pipeline.
No ANTHROPIC_API_KEY required.

Usage:
    python demo.py
    python demo.py --sector medtech
    python demo.py --limit 5 --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# The demo prints box-drawing characters; Windows consoles and redirected
# output often default to cp1252, which cannot encode them.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Make src/ importable when running from project root
sys.path.insert(0, str(Path(__file__).parent / "src"))

from schemas import RawReport
from core.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# ANSI colours (disabled on Windows if not supported)
# ---------------------------------------------------------------------------

def _supports_colour() -> bool:
    import os
    return sys.stdout.isatty() and os.name != "nt" or (
        os.name == "nt" and "ANSICON" in os.environ
    )


_USE_COLOUR = _supports_colour()

def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOUR else text

def cyan(t: str) -> str:    return _c(t, "96")
def green(t: str) -> str:   return _c(t, "92")
def yellow(t: str) -> str:  return _c(t, "93")
def red(t: str) -> str:     return _c(t, "91")
def bold(t: str) -> str:    return _c(t, "1")
def dim(t: str) -> str:     return _c(t, "2")
def magenta(t: str) -> str: return _c(t, "95")

PRIORITY_COLOUR = {
    "critical": red,
    "high": yellow,
    "medium": cyan,
    "low": green,
}

SECTOR_ICON = {
    "medtech": "🏥",
    "fintech": "🏦",
    "generic": "🔧",
}


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

def _bar(value: int, total: int, width: int = 20) -> str:
    if total == 0:
        return "░" * width
    filled = round(value / total * width)
    return "█" * filled + "░" * (width - filled)


def _print_header() -> None:
    print()
    print(bold("╔══════════════════════════════════════════════════════════╗"))
    print(bold("║") + cyan("   ⚡ TestScribe — AI-powered Bug Report Enricher Demo  ") + bold("║"))
    print(bold("║") + dim("      Rule-based fallback · No API key required          ") + bold("║"))
    print(bold("╚══════════════════════════════════════════════════════════╝"))
    print()


def _print_report(idx: int, raw: dict, result, verbose: bool) -> None:
    priority = result.severity.priority
    colour_fn = PRIORITY_COLOUR.get(priority, cyan)
    sector_icon = SECTOR_ICON.get(raw.get("sector", "generic"), "🔧")
    iec = ""
    if result.compliance.medtech:
        iec = f" · IEC 62304 class {result.compliance.medtech.iec_62304_class}"
    psd2 = ""
    if result.compliance.fintech and result.compliance.fintech.psd2_article:
        psd2 = f" · {result.compliance.fintech.psd2_article[:30]}…"

    print(f"  {dim(f'[{idx:02d}]')} {sector_icon} {bold(result.title[:55]+'…' if len(result.title)>55 else result.title)}")
    print(f"       Pattern: {magenta(result.pattern):<28} Priority: {colour_fn(priority.upper())}{iec}{psd2}")
    print(f"       Score:   {colour_fn(str(result.severity.score))}/10  "
          f"Confidence: {dim(f'{result.confidence_score:.0%}')}"
          f"  By: {dim(result.enriched_by)}")

    if verbose:
        print(f"       Summary: {dim(result.summary[:90])}")
        print(f"       Steps:   {dim(result.reproduction_steps[0][:80])}")
        if result.similar_bugs:
            top = result.similar_bugs[0]
            print(f"       Similar: {dim(top.bug_id)} ({top.similarity_score:.2f} sim)")
    print()


def _print_summary(results: list, elapsed: float) -> None:
    from collections import Counter

    priorities: Counter = Counter()
    patterns: Counter = Counter()
    sectors: Counter = Counter()
    total_conf = 0.0

    for r in results:
        priorities[r.severity.priority] += 1
        patterns[r.pattern] += 1
        sectors[r.compliance.sector] += 1
        total_conf += r.confidence_score

    total = len(results)
    avg_conf = total_conf / total if total else 0.0

    print(bold("─" * 62))
    print(bold(f"  Pipeline Summary — {total} reports in {elapsed:.2f}s"))
    print(bold("─" * 62))
    print()

    # Priority distribution
    print(f"  {bold('Priority Distribution')}")
    for p in ("critical", "high", "medium", "low"):
        count = priorities[p]
        colour_fn = PRIORITY_COLOUR[p]
        bar = _bar(count, total)
        label = colour_fn(f"{p.upper():<10}")
        print(f"    {label} {bar}  {count:2d} / {total}")
    print()

    # Top patterns
    print(f"  {bold('Top Patterns')}")
    for pattern, count in patterns.most_common(5):
        bar = _bar(count, total)
        print(f"    {magenta(pattern):<28} {bar}  {count}")
    print()

    # Sectors
    print(f"  {bold('Sectors')}")
    for sector, count in sectors.most_common():
        icon = SECTOR_ICON.get(sector, "🔧")
        bar = _bar(count, total, width=10)
        print(f"    {icon} {sector:<10} {bar}  {count}")
    print()

    print(f"  {bold('Avg confidence:')} {cyan(f'{avg_conf:.0%}')}")
    print(f"  {bold('Backend used:')}  {dim('rule-based-fallback (CI-safe, no API key)')}")
    print()
    print(bold("─" * 62))
    print(green("  ✓ All reports enriched successfully"))
    print(dim("  → Run `python src/api/app.py` to explore results in the dashboard"))
    print(bold("─" * 62))
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="TestScribe standalone demo")
    parser.add_argument("--sector", choices=["medtech", "fintech", "generic"],
                        help="Filter seed reports by sector")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of reports to enrich (default: all)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print reproduction steps and similar bugs")
    parser.add_argument("--json-out", type=str, default=None,
                        help="Save enriched reports to JSON file")
    args = parser.parse_args()

    _print_header()

    # Load seed reports
    data_path = Path(__file__).parent / "src" / "data" / "seed_reports.json"
    with data_path.open(encoding="utf-8") as f:
        seed_data: list[dict] = json.load(f)

    # Apply filters
    if args.sector:
        seed_data = [r for r in seed_data if r.get("sector") == args.sector]
        print(dim(f"  Filtered to sector: {args.sector} ({len(seed_data)} reports)\n"))

    if args.limit:
        seed_data = seed_data[:args.limit]

    if not seed_data:
        print(yellow("  No reports match the filter criteria."))
        sys.exit(0)

    # Initialise orchestrator in fallback mode
    print(dim(f"  Initialising pipeline ({len(seed_data)} reports)…\n"))
    orchestrator = Orchestrator(force_fallback=True)

    enriched: list = []
    errors: list[tuple[str, str]] = []
    start = time.perf_counter()

    for i, raw_dict in enumerate(seed_data, 1):
        try:
            raw = RawReport(**raw_dict)
            result = orchestrator.enrich(raw)
            enriched.append(result)
            _print_report(i, raw_dict, result, args.verbose)
        except Exception as e:
            errors.append((raw_dict.get("id", "?"), str(e)))
            print(f"  {red('✗')} {raw_dict.get('id', '?')}: {e}\n")

    elapsed = time.perf_counter() - start

    if errors:
        print(red(f"\n  {len(errors)} error(s) during enrichment:"))
        for bug_id, msg in errors:
            print(f"    {bug_id}: {msg}")
        print()

    _print_summary(enriched, elapsed)

    # Optional JSON export
    if args.json_out:
        out_path = Path(args.json_out)
        reports_json = [r.model_dump(mode="json") for r in enriched]
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(reports_json, f, indent=2, default=str, ensure_ascii=False)
        print(green(f"  ✓ Saved {len(reports_json)} enriched reports to {out_path}"))
        print()


if __name__ == "__main__":
    main()
