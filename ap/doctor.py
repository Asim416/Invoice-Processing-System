"""Setup checker in plain language: `python -m ap.doctor [--online] [--send-test]`

Offline checks never touch the network. --online also opens the Google Sheet read-only.
--send-test sends ONE clearly labelled test message to Slack (the only check that sends anything).
It never calls the LLM (that would use quota); use scripts/check_llm.py for that.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

from ap.config import ROOT, Settings


@dataclass
class Check:
    name: str
    status: str          # ok | warn | fail
    message: str
    fix: str = ""


def run_checks(s: Settings, online: bool = False, send_test: bool = False) -> list[Check]:
    out: list[Check] = []
    add = lambda *a, **k: out.append(Check(*a, **k))   # noqa: E731

    v = sys.version_info
    add("Python", "ok" if v >= (3, 10) else "fail", f"{v.major}.{v.minor}",
        "Install Python 3.10 or newer from python.org." if v < (3, 10) else "")

    required = ["pydantic", "pdfplumber", "openai", "yaml", "streamlit"] + (["gspread"] if s.storage_backend == "sheets" else [])
    missing = []
    for m in required:
        try:
            importlib.import_module(m)
        except ImportError:
            missing.append(m)
    add("Required packages", "fail" if missing else "ok", "missing: " + ", ".join(missing) if missing else "all installed",
        "Run: pip install -r requirements.txt" if missing else "")

    env = ROOT / ".env"
    add("Settings file (.env)", "ok" if env.exists() else "warn",
        "found" if env.exists() else "not found, built-in defaults are used (demo mode)",
        "" if env.exists() else "Copy .env.example to .env if you want live mode, Google Sheets or Slack.")

    # reader
    if s.extraction_mode == "live":
        add("AI reader", "ok" if s.api_key else "fail", f"live mode, model {s.model}" if s.api_key else "live mode but no API key",
            "" if s.api_key else "Put your key in .env as LLM_API_KEY=... (never share it).")
    else:
        add("AI reader", "warn", "demo mode: only the built-in sample invoices can be read",
            "For your own invoices set EXTRACTION_MODE=live and LLM_API_KEY in .env.")

    # data
    if s.storage_backend == "csv":
        ok = (s.data_dir / "pos.csv").exists() and (s.data_dir / "po_lines.csv").exists()
        add("Purchase orders", "ok" if ok else "fail", "local sample files found" if ok else "no purchase order files",
            "" if ok else "Run: python scripts/generate_data.py")
    elif s.storage_backend == "sheets":
        problems = [n for n, val in (("GOOGLE_SHEET_ID", s.google_sheet_id), ("GOOGLE_CREDENTIALS_FILE", s.google_credentials_file)) if not val]
        if problems:
            add("Google Sheets", "fail", "not configured: " + ", ".join(problems) + " missing", "Follow docs/day3/SETUP_GOOGLE_SHEETS.md")
        elif not Path(s.google_credentials_file).exists():
            add("Google Sheets", "fail", "the key file was not found", "Check GOOGLE_CREDENTIALS_FILE in .env.")
        elif not online:
            add("Google Sheets", "ok", "configured (connection not tested; use --online)")
        else:
            try:
                from ap.storage_sheets import SheetsStorage, TABS
                st = SheetsStorage.from_settings(s)
                titles = {w.title for w in st.sh.worksheets()}
                miss = [t for t in TABS if t not in titles]
                if miss:
                    add("Google Sheets", "fail", "connected, but missing tabs: " + ", ".join(miss), "Run: python scripts/setup_sheet.py")
                else:
                    n = len(st.list_pos())
                    add("Google Sheets", "ok" if n else "warn", f"connected; {n} purchase orders found",
                        "" if n else "The POs tab is empty. Run: python scripts/setup_sheet.py")
            except Exception as exc:    # noqa: BLE001
                add("Google Sheets", "fail", str(exc), "Follow docs/day3/SETUP_GOOGLE_SHEETS.md")
    else:
        add("Data source", "fail", f"unknown STORAGE_BACKEND '{s.storage_backend}'", "Use csv or sheets in .env.")

    # notifications
    if s.notify_backend == "slack":
        url = s.slack_webhook_url
        if not url:
            add("Manager alerts", "fail", "Slack selected but SLACK_WEBHOOK_URL is empty", "Follow docs/day3/SETUP_SLACK.md")
        elif not url.startswith("https://hooks.slack.com/"):
            add("Manager alerts", "warn", "the webhook address does not look like a Slack webhook", "Check SLACK_WEBHOOK_URL in .env.")
        elif send_test:
            from ap.notify import SlackWebhookNotifier
            o = SlackWebhookNotifier(url).send("Test message from Invoice Checker setup. No action needed.")
            add("Manager alerts", "ok" if o.sent else "fail", o.detail, "" if o.sent else "Check SLACK_WEBHOOK_URL in .env.")
        else:
            add("Manager alerts", "ok", "Slack configured (no test message sent; use --send-test)")
    else:
        add("Manager alerts", "warn" if s.notify_backend == "none" else "ok",
            {"none": "off", "console": "demo: printed on screen only"}.get(s.notify_backend, s.notify_backend),
            "Set NOTIFY_BACKEND=slack and SLACK_WEBHOOK_URL in .env to alert a manager." if s.notify_backend == "none" else "")

    # writable logs
    try:
        s.logs_dir.mkdir(parents=True, exist_ok=True)
        t = s.logs_dir / ".write_test"; t.write_text("x"); t.unlink()
        add("Run log folder", "ok", "writable")
    except OSError:
        add("Run log folder", "fail", "cannot write to the logs folder", "Check folder permissions.")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Check that Invoice Checker is set up correctly")
    ap.add_argument("--online", action="store_true", help="also test the Google Sheets connection (read-only)")
    ap.add_argument("--send-test", action="store_true", help="send one test message to Slack")
    a = ap.parse_args()
    checks = run_checks(Settings.from_env(), online=a.online, send_test=a.send_test)
    icons = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]"}
    for c in checks:
        print(f"{icons[c.status]} {c.name}: {c.message}")
        if c.fix and c.status != "ok":
            print(f"        fix: {c.fix}")
    bad = [c for c in checks if c.status == "fail"]
    print("\n" + ("Everything needed is in place." if not bad else f"{len(bad)} problem(s) to fix before using the app."))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
