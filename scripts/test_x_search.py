#!/usr/bin/env python3
"""Test script to inspect raw X search results and check for hallucination.

Usage:
    python3 scripts/test_x_search.py <topic> [--source bird|xai|ollama]
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).parent))

from lib import env, bird_x, xai_x, models, normalize

def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "microsaas"

    # Parse --source flag
    forced_source = None
    for arg in sys.argv[2:]:
        if arg.startswith("--source="):
            forced_source = arg.split("=", 1)[1]
        elif arg == "--source" and sys.argv.index(arg) + 1 < len(sys.argv):
            forced_source = sys.argv[sys.argv.index(arg) + 1]

    config = env.get_config()
    x_status = env.get_x_source_status(config)

    # Determine source: forced > bird > xai > ollama
    if forced_source:
        source = forced_source
    elif x_status["source"]:
        source = x_status["source"]
    elif env._parse_bool(config.get("USE_OLLAMA_X")):
        source = "ollama"
    else:
        source = None

    from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    to_date = datetime.now().strftime("%Y-%m-%d")

    print(f"Topic:       {topic}")
    print(f"Date range:  {from_date} → {to_date}")
    print(f"X source:    {source}")
    print(f"Bird status: installed={x_status['bird_installed']}, "
          f"auth={x_status['bird_authenticated']}, user={x_status['bird_username']}")
    print(f"xAI avail:   {x_status['xai_available']}")
    print(f"Ollama X:    {env._parse_bool(config.get('USE_OLLAMA_X'))}")
    print("-" * 60)

    # Run search
    raw_items = []
    raw_response = None

    if source == "bird":
        print("Searching via Bird (real API)...")
        raw_response = bird_x.search_x(topic, from_date, to_date, depth="default", max_items_cap=10)
        raw_items = bird_x.parse_bird_response(raw_response or {})
    elif source == "xai":
        print("Searching via xAI (Grok)...")
        selected = models.get_models(config)
        raw_response = xai_x.search_x(
            config["XAI_API_KEY"], selected["xai"],
            topic, from_date, to_date, depth="default", max_items_cap=10,
        )
        raw_items = xai_x.parse_x_response(raw_response or {})
    elif source == "ollama":
        print("Searching via Ollama...")
        from lib import ollama_x
        raw_response = ollama_x.search_x(
            config.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            config.get("OLLAMA_X_MODEL", "gemma3:4b"),
            topic, from_date, to_date, depth="default", max_items_cap=10,
        )
        raw_items = ollama_x.parse_x_response(raw_response or {})
    else:
        print("ERROR: No X source available (no Bird auth, no XAI_API_KEY)")
        sys.exit(1)

    print(f"\nRaw items returned: {len(raw_items)}")
    print("=" * 60)

    # Show each item
    for item in raw_items:
        url = item.get("url", "")
        status_match = re.search(r'/status/(\d+)', url)
        status_id = status_match.group(1) if status_match else "???"

        eng = item.get("engagement") or {}
        likes = eng.get("likes", "?")
        rts = eng.get("reposts", "?")

        print(f"\n{item.get('id', '?')} @{item.get('author_handle', '???')}")
        print(f"  URL:    {url}")
        print(f"  ID:     {status_id}")
        print(f"  Date:   {item.get('date', '???')}")
        print(f"  Eng:    {likes} likes, {rts} rt")
        print(f"  Text:   {str(item.get('text', ''))[:120]}...")

    # Run hallucination detection
    print("\n" + "=" * 60)
    print("HALLUCINATION CHECK")
    print("=" * 60)

    normalized = normalize.normalize_x_items(raw_items, from_date, to_date)
    is_hallucinated = normalize.detect_x_hallucination(normalized)

    if is_hallucinated:
        print(">>> HALLUCINATION DETECTED — these results are likely fabricated")
    else:
        print(">>> Passed — no hallucination signals detected")

    # Show raw status IDs for manual inspection
    ids = []
    for item in raw_items:
        m = re.search(r'/status/(\d+)', item.get("url", ""))
        if m:
            ids.append(int(m.group(1)))
    if ids:
        sorted_ids = sorted(ids)
        print(f"\nStatus IDs (sorted): {sorted_ids}")
        diffs = [sorted_ids[i] - sorted_ids[i-1] for i in range(1, len(sorted_ids))]
        print(f"ID diffs:            {diffs}")

    # Dump raw response for debugging
    print("\n" + "=" * 60)
    print("RAW RESPONSE (first 2000 chars)")
    print("=" * 60)
    print(json.dumps(raw_response, indent=2, default=str)[:2000])


if __name__ == "__main__":
    main()
