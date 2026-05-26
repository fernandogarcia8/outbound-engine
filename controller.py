"""
Outbound Engine — CLI Controller

Usage:
  python controller.py scrape   --market savannah [--dry-run]
  python controller.py prep     --market savannah [--dry-run]
  python controller.py outreach --market savannah --phase 1 [--dry-run] [--yes]
  python controller.py outreach --market savannah --phase 2 [--dry-run] [--yes]
  python controller.py outreach --market savannah --phase 3 [--dry-run] [--yes]

Phases:
  1 — Cross-List   (BS - Live → Getmyboat pitch | GMB - Live → Boatsetter pitch)
  2 — BS - Not Live (reactivate + get_live)
  3 — Prospect     (cold outreach via Casey alias)

Markets are auto-discovered from Google Drive. Share a Sheets document with
the service account (or place it in MARKETS_DRIVE_FOLDER_ID) to add a market.
"""

import argparse
import sys
import os

# Make outbound_engine modules importable from the project root
_ENGINE_DIR = os.path.join(os.path.dirname(__file__), "outbound_engine")
sys.path.insert(0, _ENGINE_DIR)

# Load .env from outbound_engine/ before any module-level load_dotenv() calls
from dotenv import load_dotenv
load_dotenv(os.path.join(_ENGINE_DIR, ".env"))

# Resolve any relative paths in env vars to absolute paths anchored to the engine dir
# so the controller works when run from the project root.
for _var in ("GOOGLE_SHEETS_CREDENTIALS_JSON",):
    _val = os.getenv(_var, "")
    if _val and not os.path.isabs(_val):
        os.environ[_var] = os.path.join(_ENGINE_DIR, _val)

from markets import get_markets
from split_not_live import split_not_live
from classify_not_live import classify_not_live
from cross_list import detect_cross_list
from engine import run_campaign


# ── Helpers ────────────────────────────────────────────────────────────────────

def _divider(char="─", width=62):
    print(char * width)


def _header(title: str):
    _divider("═")
    print(f"  {title}")
    _divider("═")


def resolve_market(key: str) -> tuple[str, dict]:
    """
    Accepts 'savannah', 'Savannah', or a partial name.
    Tries exact key match first, then falls back to substring match on display name.
    """
    import re
    markets    = get_markets()
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")

    # Exact key match
    if normalized in markets:
        return normalized, markets[normalized]

    # Substring match on display name (case-insensitive)
    needle = key.lower()
    for k, cfg in markets.items():
        if needle in cfg["display_name"].lower():
            return k, cfg

    available = ", ".join(f"{k} ({v['display_name']})" for k, v in markets.items()) or "(none found)"
    print(f"\n  Unknown market '{key}'.")
    print(f"  Available: {available}")
    print(f"\n  Share a Google Sheets document with the service account to add a market.\n")
    sys.exit(1)


# ── Scrape ─────────────────────────────────────────────────────────────────────

def cmd_scrape(cfg: dict, dry_run: bool) -> None:
    """Scrapes boat charter operators and writes them to the Prospects tab."""
    market_name = cfg["display_name"]

    _header(f"Scrape — {market_name}")
    print()
    print("  Prospect scraping uses the /boat-charter-prospector skill in Claude Code.")
    print()
    print("  Steps:")
    print(f"    1. Open Claude Code in this project directory.")
    print(f"    2. Run:  /boat-charter-prospector  (or the equivalent skill)")
    print(f"    3. When prompted, enter market: {market_name}")
    print(f"    4. Results will be written to the 'Prospects' tab in the sheet.")
    print(f"    5. Review the tab, then come back and run prep + outreach.")
    print()
    print("  Web app will automate this step — coming soon.")
    print()


# ── Prep ───────────────────────────────────────────────────────────────────────

def cmd_prep(cfg: dict, dry_run: bool) -> None:
    """Runs all detection and classification steps for a market."""
    market_name = cfg["display_name"]
    sheet_id    = cfg["sheet_id"]
    sheets      = cfg.get("sheets", {})
    bs_not_live  = sheets.get("bs_not_live",  "BS - Not Live")
    bs_churn     = sheets.get("bs_churn",     "BS - Churn")
    bs_live      = sheets.get("bs_live",      "BS - Live")
    gmb_live     = sheets.get("gmb_live",     "GMB - Live")
    gmb_not_live = sheets.get("gmb_not_live", "GMB - Not Live")

    mode = " [DRY RUN]" if dry_run else ""
    _header(f"Prep{mode} — {market_name}")

    # ── Step 1: Split ──────────────────────────────────────────────────────────
    print(f"\n[1/3] Splitting BS - Not Live...")
    _divider()
    result = split_not_live(
        sheet_id=sheet_id,
        source_sheet=bs_not_live,
        churn_sheet=bs_churn,
        dry_run=dry_run,
    )
    print(
        f"\n  Split complete: "
        f"{result.get('kept', 0)} kept · "
        f"{result.get('moved', 0)} moved to churn · "
        f"{result.get('unknown', 0)} unknown state"
    )

    # ── Step 2: Classify ───────────────────────────────────────────────────────
    print(f"\n[2/3] Classifying BS - Not Live...")
    _divider()
    result = classify_not_live(
        sheet_id=sheet_id,
        sheet_name=bs_not_live,
        dry_run=dry_run,
    )
    print(
        f"\n  Classification complete: "
        f"{result.get('classified', 0)} classified · "
        f"{result.get('skipped_already_set', 0)} already set"
    )

    # ── Step 3: Cross-list detection ───────────────────────────────────────────
    print(f"\n[3/3] Running cross-list detection...")
    _divider()
    result = detect_cross_list(
        spreadsheet_id=sheet_id,
        bs_sheet_name=bs_live,
        gmb_sheet_name=gmb_live,
        churn_sheet_name=bs_churn,
        not_live_sheet_name=bs_not_live,
        gmb_not_live_sheet_name=gmb_not_live,
        dry_run=dry_run,
    )

    # ── Summary ────────────────────────────────────────────────────────────────
    print()
    _divider("═")
    print(f"  Prep complete{mode} — {market_name}")
    _divider("═")
    print()
    print("  Review the sheet before running outreach.")
    print("  When ready:")
    print(f"    python controller.py outreach --market {cfg['display_name'].lower()} --phase 1 --dry-run")
    print()


# ── Outreach ───────────────────────────────────────────────────────────────────

def cmd_outreach(cfg: dict, phase: int, dry_run: bool, yes: bool, test_only: bool = False) -> None:
    """Runs outreach for the given phase."""
    market_name = cfg["display_name"]
    sheet_id    = cfg["sheet_id"]
    sheets      = cfg.get("sheets", {})
    bs_live     = sheets.get("bs_live",     "BS - Live")
    gmb_live    = sheets.get("gmb_live",    "GMB - Live")
    bs_not_live = sheets.get("bs_not_live", "BS - Not Live")
    prospects   = sheets.get("prospects",   "Prospects")

    phase_labels = {
        1: "Phase 1 - Cross-List",
        2: "Phase 2 - BS Not Live",
        3: "Phase 3 - Prospect",
    }
    mode = " [DRY RUN]" if dry_run else (" [TEST]" if test_only else "")
    _header(f"Outreach{mode} — {phase_labels[phase]} · {market_name}")
    if test_only:
        print("  ⚠  Test mode — only rows where Notes = 'test' will be contacted.\n")

    base = dict(
        market=market_name,
        sheet_id=sheet_id,
        dry_run=dry_run,
        test_only=test_only,
        require_approval=not yes,
    )

    if phase == 1:
        print(f"\n[1/2] BS - Live  →  Getmyboat pitch (email + SMS)")
        _divider()
        run_campaign(segment="cross_list", sheet_name=bs_live, **base)

        print(f"\n[2/2] GMB - Live  →  Boatsetter pitch (SMS only)")
        _divider()
        run_campaign(segment="cross_list", sheet_name=gmb_live, sms_only=True, **base)

    elif phase == 2:
        print(f"\n[1/2] Reactivate  (BS - Not Live)")
        _divider()
        run_campaign(segment="reactivate", sheet_name=bs_not_live, **base)

        print(f"\n[2/2] Get Live  (BS - Not Live)")
        _divider()
        run_campaign(segment="get_live", sheet_name=bs_not_live, **base)

    elif phase == 3:
        print(f"\n[1/1] Prospect  (Casey alias)")
        _divider()
        run_campaign(segment="prospect", sheet_name=prospects, **base)

    print()
    _divider("═")
    print(f"  {phase_labels[phase]}{mode} — Done.")
    _divider("═")

    if phase < 3 and not dry_run:
        next_phase = phase + 1
        market_key = market_name.lower()
        print()
        print("  Review the sheet. When ready for the next phase:")
        print(f"    python controller.py outreach --market {market_key} --phase {next_phase} --dry-run")
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="controller",
        description="Outbound Engine — run scrape, prep, or outreach for any market.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python controller.py prep     --market savannah\n"
            "  python controller.py outreach --market savannah --phase 1 --dry-run\n"
            "  python controller.py outreach --market savannah --phase 1\n"
            "  python controller.py outreach --market savannah --phase 2\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # scrape
    p = sub.add_parser("scrape", help="Instructions for scraping prospects for a market")
    p.add_argument("--market", required=True, help="Market key, e.g. savannah")
    p.add_argument("--dry-run", action="store_true")

    # prep
    p = sub.add_parser("prep", help="Run split + classify + cross-list detection")
    p.add_argument("--market", required=True, help="Market key, e.g. savannah")
    p.add_argument("--dry-run", action="store_true", help="Preview only, no writes")

    # outreach
    p = sub.add_parser("outreach", help="Send outreach for a given phase")
    p.add_argument("--market",  required=True, help="Market key, e.g. savannah")
    p.add_argument("--phase",   required=True, type=int, choices=[1, 2, 3],
                   help="1=Cross-List  2=BS-Not-Live  3=Prospect")
    p.add_argument("--dry-run", action="store_true", help="Preview only, no messages sent")
    p.add_argument("--yes",     action="store_true", help="Skip approval prompt")
    p.add_argument("--test",    action="store_true", help="Only contact rows where Notes = 'test'")

    args = parser.parse_args()
    _, cfg = resolve_market(args.market)

    if args.command == "scrape":
        cmd_scrape(cfg, args.dry_run)
    elif args.command == "prep":
        cmd_prep(cfg, args.dry_run)
    elif args.command == "outreach":
        cmd_outreach(cfg, args.phase, args.dry_run, args.yes, getattr(args, "test", False))


if __name__ == "__main__":
    main()
