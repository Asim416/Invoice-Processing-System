"""Baseline B: what a person gets from a plain chat assistant with a basic prompt and NO system around it.

  python scripts/baseline_prompt.py --print          # writes results/baseline_B_prompts.md: paste each prompt into any chat tool yourself
  python scripts/baseline_prompt.py --call --runs 3  # calls your configured LLM (needs LLM_API_KEY) and saves the raw answers

By design the assistant is NOT given the tolerance rules or the processed-invoice log (Day 1, section 5.2).
Afterwards, open results/baseline_B_responses.csv and fill the yellow columns yourself:
  your_label (Approve / Needs review / Reject (hold)), invented_facts (yes/no), vendor_message_score (0, 1 or 2),
  minutes_hands_on (your time to paste, read and decide).  Then run: python scripts/compare.py
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ap.config import Settings                      # noqa: E402
from ap.fmt import money, qty                       # noqa: E402
from ap.pdf_text import extract_text                # noqa: E402
from ap.storage import CsvStorage                   # noqa: E402

PROMPT = ("Here is a supplier invoice and a purchase order. Tell me whether the invoice matches the PO and whether I "
          "should pay it. If there is a problem, write a short email to the vendor.")


def po_text(po) -> str:
    if po is None:
        return "No purchase order record was found for this invoice."
    lines = "\n".join(f"- {l.description}: quantity {qty(l.quantity)}, unit price {money(l.unit_price)}" for l in po.lines)
    return f"{po.po_number} | {po.vendor_name} | {po.currency} | status: {po.status} | total {money(po.total)}\n{lines}"


def build_prompts(data: Path) -> list[dict]:
    import json
    storage = CsvStorage(data, data)
    out = []
    for r in csv.DictReader(open(data / "expected_results.csv", newline="")):
        truth = json.loads((data / "ground_truth" / f"{r['case_id']}.json").read_text())
        po = storage.get_po(truth["po_number"]) if truth["po_number"] else None
        text = extract_text(data / r["invoice_file"])
        out.append({"case_id": r["case_id"], "expected_label": r["expected_label"],
                    "prompt": f"{PROMPT}\n\n--- INVOICE ---\n{text}\n\n--- PURCHASE ORDER ---\n{po_text(po)}"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--call", action="store_true")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--data", default="data")
    a = ap.parse_args()
    prompts = build_prompts(Path(a.data))
    (ROOT / "results").mkdir(exist_ok=True)
    if a.print or not a.call:
        md = ["# Baseline B prompts (paste each into a plain chat assistant, 3 separate chats per case)\n"]
        md += [f"## {p['case_id']}\n\n```\n{p['prompt']}\n```\n" for p in prompts]
        (ROOT / "results" / "baseline_B_prompts.md").write_text("\n".join(md))
        print(f"wrote results/baseline_B_prompts.md ({len(prompts)} prompts)")
        if not a.call:
            return 0
    s = Settings.from_env()
    if not s.api_key:
        print("LLM_API_KEY is not set."); return 2
    import openai
    client = openai.OpenAI(base_url=s.base_url, api_key=s.api_key, timeout=60, max_retries=2)
    rows = []
    for run in range(1, a.runs + 1):
        for p in prompts:
            t0 = time.perf_counter()
            try:
                resp = client.chat.completions.create(model=s.model, temperature=1.0,
                                                      messages=[{"role": "user", "content": p["prompt"]}], max_completion_tokens=1200)
                answer = resp.choices[0].message.content or ""
            except Exception as exc:   # noqa: BLE001
                answer = f"[CALL FAILED: {type(exc).__name__}]"
            rows.append({"case_id": p["case_id"], "run": run, "seconds_model": round(time.perf_counter() - t0, 1),
                         "response": answer, "your_label": "", "invented_facts": "", "vendor_message_score": "",
                         "minutes_hands_on": ""})
            print(f"  {p['case_id']} run {run}: {len(answer)} chars")
            time.sleep(2)           # gentle on free-tier limits
    with open(ROOT / "results" / "baseline_B_responses.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print("wrote results/baseline_B_responses.csv: now fill your_label, invented_facts, vendor_message_score, minutes_hands_on")
    return 0


if __name__ == "__main__":
    sys.exit(main())
