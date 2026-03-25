#!/usr/bin/env python3
"""assemble-templates.py — Verify shared CSS tokens are consistent across templates.

Reads _shared-css.txt and checks that every template contains each
non-comment, non-blank line from the shared CSS.  Reports mismatches
but does NOT auto-patch (templates have per-level overrides, so
blind injection would break ordering).

Usage:
    python3 assemble-templates.py [--resources-dir DIR]

Exit codes:
    0  all templates contain the shared CSS lines
    1  one or more templates are missing shared CSS lines
"""

import argparse
import os
import sys

TEMPLATES = [
    "l0-template.html",
    "l1-template.html",
    "l2-template.html",
    "search-template.html",
    "focus-template.html",
]


def main():
    parser = argparse.ArgumentParser(description="Check shared CSS consistency across wiki templates")
    parser.add_argument("--resources-dir", default=os.path.join(os.path.dirname(__file__), "..", "resources"),
                        help="Path to resources/ directory")
    args = parser.parse_args()
    res_dir = os.path.abspath(args.resources_dir)

    shared_path = os.path.join(res_dir, "_shared-css.txt")
    if not os.path.isfile(shared_path):
        print(f"ERROR: {shared_path} not found")
        sys.exit(1)

    with open(shared_path, "r", encoding="utf-8") as f:
        shared_lines = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("/*")
        ]

    errors = 0
    for tpl_name in TEMPLATES:
        tpl_path = os.path.join(res_dir, tpl_name)
        if not os.path.isfile(tpl_path):
            print(f"  SKIP  {tpl_name} (not found)")
            continue
        with open(tpl_path, "r", encoding="utf-8") as f:
            tpl_content = f.read()

        missing = [line for line in shared_lines if line not in tpl_content]
        if missing:
            errors += 1
            print(f"  FAIL  {tpl_name}: {len(missing)} shared CSS lines missing")
            for m in missing[:5]:
                print(f"        - {m[:80]}")
            if len(missing) > 5:
                print(f"        ... and {len(missing) - 5} more")
        else:
            print(f"  OK    {tpl_name}")

    if errors:
        print(f"\n{errors} template(s) have CSS drift. Update them to match _shared-css.txt.")
        sys.exit(1)
    else:
        print("\nAll templates contain shared CSS tokens.")
        sys.exit(0)


if __name__ == "__main__":
    main()
