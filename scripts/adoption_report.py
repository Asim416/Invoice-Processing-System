"""Adoption and quality report from the system's own logs (runs, recorded decisions, escalations).

  python scripts/adoption_report.py --days 14
  python scripts/adoption_report.py --since 2026-12-01 --until 2026-12-14 --out results/adoption_week2.md

Works with the local files or your Google Sheet, whichever .env selects. The report says loudly when the data is
synthetic or demo-mode, so test traffic can never be mistaken for real adoption.
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ap import adoption                                  # noqa: E402
from ap.config import Settings                           # noqa: E402
from ap.services import build_storage                    # noqa: E402
from ap.storage import StorageError                      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, help="the last N days")
    ap.add_argument("--since"); ap.add_argument("--until"); ap.add_argument("--out")
    ap.add_argument("--price-in", type=float); ap.add_argument("--price-out", type=float)
    a = ap.parse_args()
    since = until = None
    if a.days:
        since = datetime.now(timezone.utc) - timedelta(days=a.days)
    if a.since:
        since = datetime.fromisoformat(a.since).replace(tzinfo=timezone.utc)
    if a.until:
        until = datetime.fromisoformat(a.until).replace(tzinfo=timezone.utc) + timedelta(days=1)
    try:
        st = build_storage(Settings.from_env())
        m = adoption.compute(st.all_runs(), st.processed_entries(), st.all_events(), since=since, until=until,
                             price_in=a.price_in, price_out=a.price_out)
    except StorageError as exc:
        print(f"Could not read the logs: {exc}")
        return 2
    md = adoption.markdown(m)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
