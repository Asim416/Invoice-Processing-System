"""Reset the LOCAL demo state so a recording starts clean and predictable.

  python scripts/reset_demo.py

Deletes local run logs, events and the extraction cache, and regenerates the sample data (which restores the seeded
processed-invoice log). It never touches Google Sheets, `.env` or `secrets/`.
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def reset(root: Path = ROOT) -> list[str]:
    done = []
    for f in ("logs/runs.jsonl", "logs/events.jsonl"):
        p = root / f
        if p.exists():
            p.unlink(); done.append(f"deleted {f}")
    cache = root / "cache" / "extractions"
    if cache.exists():
        shutil.rmtree(cache); done.append("deleted cache/extractions")
    import generate_data
    generate_data.generate(root / "data"); generate_data.generate_stress(root / "data"); generate_data.generate_holdout(root / "data")
    done.append("regenerated data/ (sample invoices, purchase orders, seeded processed log)")
    return done


if __name__ == "__main__":
    for line in reset():
        print(line)
    print("Local demo state is clean. Google Sheets (if used) was NOT changed: reset those tabs by hand if needed.")
