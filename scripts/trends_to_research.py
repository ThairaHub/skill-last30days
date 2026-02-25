#!/usr/bin/env python3
"""Combine top Google Trends by volume and run last30days research on each.

Reads the Logseq trend pages, picks the top N trends by search volume
across all categories, and runs last30days.py for each one.

Usage:
    python3 scripts/trends_to_research.py [--top 3] [--quick] [--dry-run]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

LOGSEQ_DIR = Path("/Volumes/server-ssd/Documents/Logseq/pages")
SCRIPT_DIR = Path(__file__).parent.resolve()
LAST30DAYS = SCRIPT_DIR / "last30days.py"


def parse_volume(vol_str: str) -> int:
    """Parse Portuguese volume string to a comparable integer.

    Examples: '200 mil+' -> 200000, '10 mil+' -> 10000, '500+' -> 500
    """
    vol_str = vol_str.strip().rstrip("+").strip()
    match = re.match(r"([\d.,]+)\s*mil", vol_str, re.IGNORECASE)
    if match:
        num = float(match.group(1).replace(",", "."))
        return int(num * 1000)
    match = re.match(r"([\d.,]+)", vol_str)
    if match:
        return int(float(match.group(1).replace(",", ".")))
    return 0


def parse_logseq_trends(filepath: Path) -> list[dict]:
    """Parse a Google Trends Logseq page and extract trend name, volume, category."""
    content = filepath.read_text(encoding="utf-8", errors="replace")

    # Extract category from page properties
    cat_match = re.search(r"^category::\s*\[\[(.+?)]]", content, re.MULTILINE)
    category = cat_match.group(1) if cat_match else "unknown"

    trends = []
    current_trend = None

    for line in content.split("\n"):
        # Match trend lines: "\t- trend name #tendencia"
        trend_match = re.match(r"\t- (.+?)\s*#tendencia", line)
        if trend_match:
            current_trend = {
                "name": trend_match.group(1).strip(),
                "category": category,
                "volume_raw": "",
                "volume": 0,
                "source_file": filepath.name,
            }
            trends.append(current_trend)
            continue

        # Match volume lines: "\t\t- volume:: 200 mil+"
        vol_match = re.match(r"\t\t- volume::\s*(.+)", line)
        if vol_match and current_trend:
            current_trend["volume_raw"] = vol_match.group(1).strip()
            current_trend["volume"] = parse_volume(current_trend["volume_raw"])

    return trends


def main():
    parser = argparse.ArgumentParser(description="Research top Google Trends via last30days")
    parser.add_argument("--top", type=int, default=3, help="Number of top trends to research (default: 3)")
    parser.add_argument("--quick", action="store_true", help="Use --quick flag for faster research")
    parser.add_argument("--deep", action="store_true", help="Use --deep flag for comprehensive research")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    parser.add_argument("--store", action="store_true", help="Persist findings to SQLite")
    parser.add_argument("--limit", type=int, default=None, help="Cap results per source (passed to last30days.py)")
    args = parser.parse_args()

    # Find all Google Trends Logseq pages
    trend_files = sorted(LOGSEQ_DIR.glob("google-trends___*.md"))
    if not trend_files:
        print("No Google Trends pages found in Logseq. Run grab_google_trends.py first.")
        sys.exit(1)

    # Parse all trends across categories
    all_trends = []
    for f in trend_files:
        trends = parse_logseq_trends(f)
        all_trends.extend(trends)
        print(f"  {f.name}: {len(trends)} trends")

    if not all_trends:
        print("No trends parsed from Logseq pages.")
        sys.exit(1)

    # Pick top 1 per category (by volume), for diversity, deduped by name
    by_category = {}
    for t in all_trends:
        cat = t["category"]
        if cat not in by_category or t["volume"] > by_category[cat]["volume"]:
            by_category[cat] = t
    seen_names = set()
    top = []
    for t in sorted(by_category.values(), key=lambda t: t["volume"], reverse=True):
        name_key = t["name"].lower().strip()
        if name_key not in seen_names:
            seen_names.add(name_key)
            top.append(t)

    print(f"\nTop trend per category (by volume):")
    print("-" * 60)
    for i, t in enumerate(top, 1):
        print(f"  {i}. {t['name']}  ({t['volume_raw']})  [{t['category']}]")
    print()

    if args.dry_run:
        print("Dry run — would execute:")
        for t in top:
            cmd = f"python3 {LAST30DAYS} \"{t['name']}\""
            if args.quick:
                cmd += " --quick"
            if args.deep:
                cmd += " --deep"
            if args.store:
                cmd += " --store"
            if args.limit:
                cmd += f" --limit {args.limit}"
            print(f"  {cmd}")
        return

    # Run last30days.py for each top trend
    for i, t in enumerate(top, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(top)}] Researching: {t['name']}  ({t['volume_raw']}, {t['category']})")
        print(f"{'='*60}\n")

        cmd = [sys.executable, str(LAST30DAYS), t["name"]]
        if args.quick:
            cmd.append("--quick")
        if args.deep:
            cmd.append("--deep")
        if args.store:
            cmd.append("--store")
        if args.limit:
            cmd.extend(["--limit", str(args.limit)])

        result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))

        if result.returncode != 0:
            print(f"\n  WARNING: last30days.py exited with code {result.returncode} for '{t['name']}'")

    print(f"\n{'='*60}")
    print(f"Done. Researched {len(top)} trends.")
    print(f"Results saved to Logseq and {SCRIPT_DIR.parent / 'out'}")


if __name__ == "__main__":
    main()
