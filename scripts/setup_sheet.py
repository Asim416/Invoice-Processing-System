"""One-time setup: create the required tabs in YOUR Google Sheet and copy the sample purchase orders into it.

  python scripts/setup_sheet.py            # creates missing tabs, fills POs/PO_Lines/Processed only if they are empty
  python scripts/setup_sheet.py --no-seed  # create the tabs only (use your own purchase orders)

Needs STORAGE_BACKEND=sheets, GOOGLE_SHEET_ID and GOOGLE_CREDENTIALS_FILE in .env (see docs/day3/SETUP_GOOGLE_SHEETS.md).
Sample data is synthetic. Writes use RAW mode, so nothing is interpreted as a formula.
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ap.config import Settings                                  # noqa: E402
from ap.storage import StorageError                             # noqa: E402
from ap.storage_sheets import SheetsStorage, TABS               # noqa: E402

SEED = {"POs": "pos.csv", "PO_Lines": "po_lines.csv", "Processed": "processed_invoices.csv"}


def seed(storage: SheetsStorage, data_dir: Path) -> list[str]:
    done = []
    for tab, fname in SEED.items():
        ws = storage._ws(tab)
        if len(storage._call(ws.get_all_values)) > 1:
            continue                                            # never overwrite existing data
        with open(data_dir / fname, newline="") as f:
            rows = list(csv.DictReader(f))
        values = [[r.get(h, "") for h in TABS[tab]] for r in rows]
        if values:
            storage._call(ws.append_rows, values, value_input_option="RAW")
        done.append(f"{tab} ({len(values)} rows)")
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-seed", action="store_true")
    a = ap.parse_args()
    s = Settings.from_env(storage_backend="sheets")
    try:
        st = SheetsStorage.from_settings(s)
        created = st.ensure_tabs()
        print("Created tabs:", ", ".join(created) if created else "none (all tabs already exist)")
        if not a.no_seed:
            done = seed(st, s.data_dir)
            print("Filled with sample data:", ", ".join(done) if done else "nothing (tabs already had data)")
    except StorageError as exc:
        print(f"Setup stopped: {exc}")
        return 1
    print("Done. Check it with: python -m ap.doctor --online")
    return 0


if __name__ == "__main__":
    sys.exit(main())
