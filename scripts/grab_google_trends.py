#!/usr/bin/env python3
"""Download trending topics from Google Trends and save as Logseq pages.

Grabs multiple categories for a given country using Playwright,
parses the CSVs, and writes Logseq-native outliner .md files.

Usage:
    python3 scripts/grab_google_trends.py [--geo BR] [--headed]
"""

import argparse
import csv
import io
import re
import tempfile
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

CATEGORIES = {
    "4": "Entretenimento",
    "10": "Legislacao_e_governo",
    "3": "Financas",
    "14": "Politica",
}

LOGSEQ_DIR = Path("/Volumes/server-ssd/Documents/Logseq/pages")


def _sanitize_logseq_filename(name: str) -> str:
    sanitized = re.sub(r'[/:*?"<>|\\]', '-', name)
    sanitized = re.sub(r'-{2,}', '-', sanitized).strip('- ')
    return sanitized or 'untitled'


def parse_csv(csv_path: Path) -> list[dict]:
    """Parse a Google Trends CSV into a list of trend dicts."""
    content = csv_path.read_text(encoding="utf-8", errors="replace")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return []

    header = rows[0]
    items = []
    for row in rows[1:]:
        if len(row) < 2:
            continue
        item = {}
        for i, col in enumerate(header):
            if i < len(row):
                item[col] = row[i]
        items.append(item)
    return items


def render_logseq_trends(geo: str, cat_id: str, cat_name: str, items: list[dict]) -> str:
    """Render trend items as a Logseq-native outliner page."""
    lines = []
    today = datetime.now().strftime("%Y-%m-%d")

    # Page-level properties
    lines.append(f"type:: [[google-trends]]")
    lines.append(f"category:: [[{cat_name}]]")
    lines.append(f"category-id:: {cat_id}")
    lines.append(f"geo:: {geo}")
    lines.append(f"date:: [[{today}]]")
    lines.append(f"trends-count:: {len(items)}")
    lines.append("")

    # Root block
    lines.append(f"- Google Trends: {cat_name} ({geo}) #google-trends")

    if not items:
        lines.append(f"\t- Nenhuma tendência encontrada para esta categoria")
        lines.append("")
        return "\n".join(lines)

    for item in items:
        trend_name = item.get("Tendências", item.get("Trending", "???"))
        volume = item.get("Volume de pesquisa", item.get("Search Volume", ""))
        started = item.get("Iniciado", item.get("Started", ""))
        ended = item.get("Finalizada", item.get("Ended", ""))
        breakdown = item.get("Detalhamento da tendência", item.get("Trend Breakdown", ""))
        explore_url = item.get('Acesse a página "Explorar"', item.get("Explore Link", ""))

        lines.append(f"\t- {trend_name} #tendencia")
        lines.append(f"\t\t- volume:: {volume}")
        if started:
            lines.append(f"\t\t- inicio:: {started}")
        if ended:
            lines.append(f"\t\t- fim:: {ended}")
        if explore_url:
            lines.append(f"\t\t- explore:: {explore_url}")
        if breakdown:
            # Show top related queries (first 10)
            related = [q.strip() for q in breakdown.split(",") if q.strip()]
            if related:
                lines.append(f"\t\t- Termos relacionados")
                for term in related[:10]:
                    lines.append(f"\t\t\t- {term}")
                if len(related) > 10:
                    lines.append(f"\t\t\t- ... e mais {len(related) - 10} termos")

    lines.append("")
    return "\n".join(lines)


def download_category(page, geo, cat_id, cat_name, tmp_dir):
    """Download CSV for a single category. Returns path to temp CSV or None."""
    url = f"https://trends.google.com/trending?geo={geo}&category={cat_id}"
    tmp_csv = Path(tmp_dir) / f"trends_{geo}_cat{cat_id}.csv"

    print(f"\n{'='*60}")
    print(f"Category {cat_id}: {cat_name}")
    print(f"URL:      {url}")

    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    # Wait for the export button to appear (page may still be loading data)
    page.locator('button:has-text("Exportar"), button:has-text("Export")').first.wait_for(
        state="visible", timeout=15000
    )
    page.wait_for_timeout(1000)

    # Find the toolbar export button
    export_btn = None
    for selector in [
        'button.wkLVUc-LgbsSe:has-text("Exportar")',
        'button.wkLVUc-LgbsSe:has-text("Export")',
        'button[aria-label="Exportar"]',
        'button[aria-label="Export"]',
    ]:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=1000):
                export_btn = btn
                print(f"  Found button: {selector}")
                break
        except Exception:
            continue

    if not export_btn:
        print(f"  ERROR: Could not find export button")
        buttons = page.locator("button").all()
        for i, btn in enumerate(buttons[:20]):
            try:
                text = btn.inner_text(timeout=1000).strip().replace('\n', ' ')
                label = btn.get_attribute("aria-label") or ""
                print(f"    [{i}] text={text[:50]!r}  aria-label={label!r}")
            except Exception:
                pass
        return None

    # Step 1: Click "Exportar" to open dropdown
    print("  Clicking Exportar...")
    export_btn.click()
    page.wait_for_timeout(1000)

    # Step 2: Arrow down + Enter to select "Fazer download como CSV"
    print("  Selecting CSV via keyboard (ArrowDown + Enter)...")
    try:
        with page.expect_download(timeout=15000) as download_info:
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(300)
            page.keyboard.press("Enter")
        download = download_info.value
        download.save_as(str(tmp_csv))
        size = tmp_csv.stat().st_size
        print(f"  Downloaded: {tmp_csv.name} ({size} bytes)")
        return tmp_csv
    except Exception as e:
        print(f"  Download failed: {e}")
        page.keyboard.press("Escape")
        return None


def main():
    parser = argparse.ArgumentParser(description="Download Google Trends as Logseq pages")
    parser.add_argument("--geo", default="BR", help="Country code (default: BR)")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    args = parser.parse_args()

    print(f"Geo:        {args.geo}")
    print(f"Logseq dir: {LOGSEQ_DIR}")
    print(f"Categories: {', '.join(f'{k} ({v})' for k, v in CATEGORIES.items())}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Phase 1: Download all CSVs
        csv_files = {}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.headed)
            context = browser.new_context(
                accept_downloads=True,
                locale="pt-BR",
            )
            page = context.new_page()

            for cat_id, cat_name in CATEGORIES.items():
                result = download_category(page, args.geo, cat_id, cat_name, tmp_dir)
                if result:
                    csv_files[cat_id] = result

            browser.close()

        # Phase 2: Parse CSVs and write Logseq pages
        print(f"\n{'='*60}")
        print("Converting to Logseq format...")

        written = []
        for cat_id, csv_path in csv_files.items():
            cat_name = CATEGORIES[cat_id]
            items = parse_csv(csv_path)
            print(f"  {cat_name}: {len(items)} trends parsed")

            logseq_content = render_logseq_trends(args.geo, cat_id, cat_name, items)
            safe_name = _sanitize_logseq_filename(f"google-trends___{cat_name}")
            logseq_path = LOGSEQ_DIR / f"{safe_name}.md"
            logseq_path.write_text(logseq_content, encoding="utf-8")
            written.append(logseq_path)
            print(f"  Wrote: {logseq_path.name}")

        print(f"\n{'='*60}")
        print(f"Done. Wrote {len(written)}/{len(CATEGORIES)} Logseq pages:")
        for f in written:
            print(f"  {f}")


if __name__ == "__main__":
    main()
