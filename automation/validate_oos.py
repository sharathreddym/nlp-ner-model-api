"""
validate_oos.py — guardrail for a regenerated outOfScopeData.json.

Fails loudly (returns list of problems) if the file is unusable, so a bad
Snowflake refresh can NEVER be committed/deployed. Catches the classes of
failure we actually hit:
  - JSON won't parse / 32 KB truncation
  - missing required keys
  - wildly different counts (e.g. an empty / half-loaded source pull)

Usage (standalone):
    python validate_oos.py new_outOfScopeData.json --baseline dependencies/outOfScopeData.json
Exit code 0 = OK, 1 = problems (printed to stderr).
"""
from __future__ import annotations
import json
import os
import sys

# The exact 10 keys the runtime (post_processing / ner_helper) depends on.
REQUIRED_KEYS = [
    "grades", "gradesExternal", "gradesInScope", "gradesInScopeExternal",
    "brands", "brands_internal", "brands_commerical", "brands_not_in_scope",
    "polymers", "fillers",
]

# Guardrail thresholds — tune to your data. These caught the real bugs.
MIN_BYTES = 500_000          # real file is ~725 KB; 32 KB-truncation is far below this
MAX_COUNT_SWING = 0.25       # >25% change vs baseline in a grade list = suspicious


def validate(path: str, baseline_path: str | None = None) -> list[str]:
    problems: list[str] = []

    # 1) file exists and is a sane size (catches truncation / empty)
    if not os.path.exists(path):
        return [f"file not found: {path}"]
    size = os.path.getsize(path)
    if size < MIN_BYTES:
        problems.append(f"file too small ({size:,} B < {MIN_BYTES:,} B) — likely truncated/empty")

    # 2) parses as JSON (catches control-char / doubled-quote corruption)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return problems + [f"JSON did not parse: {e}"]

    # 3) all required keys present, each a list
    for k in REQUIRED_KEYS:
        if k not in data:
            problems.append(f"missing required key: {k}")
        elif not isinstance(data[k], list):
            problems.append(f"key {k} is not a list (got {type(data[k]).__name__})")

    # 4) in-scope lists must be non-empty (an empty SPT pull hides everything)
    for k in ("gradesInScope", "gradesInScopeExternal"):
        if isinstance(data.get(k), list) and len(data[k]) == 0:
            problems.append(f"{k} is empty — SPT/in-scope source likely failed to load")

    # 5) sanity: counts didn't swing wildly vs the currently-committed file
    if baseline_path and os.path.exists(baseline_path):
        try:
            with open(baseline_path, encoding="utf-8") as f:
                base = json.load(f)
            for k in ("grades", "gradesExternal", "gradesInScope", "gradesInScopeExternal"):
                b, n = len(base.get(k, [])), len(data.get(k, []))
                if b and abs(n - b) / b > MAX_COUNT_SWING:
                    problems.append(
                        f"{k} count swung {b:,} -> {n:,} "
                        f"(> {int(MAX_COUNT_SWING*100)}%) — verify the source pull"
                    )
        except Exception as e:
            problems.append(f"could not compare to baseline: {e}")

    return problems


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--baseline", default=None)
    args = ap.parse_args()
    problems = validate(args.path, args.baseline)
    if problems:
        print("VALIDATION FAILED:", file=sys.stderr)
        for p in problems:
            print("  -", p, file=sys.stderr)
        return 1
    print("validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
