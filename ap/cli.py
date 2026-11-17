"""Command line interface: `python -m ap.cli process <invoice.pdf>` and `python -m ap.cli confirm <run_id> ...`"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ap.config import Policy, Settings
from ap.extraction.factory import build_provider
from ap.pipeline import Pipeline
from ap.schemas import ErrorResponse, RunResult
from ap.services import build_notifier, build_storage
from ap.storage import StorageError
from ap.ui_logic import AppService


def build(args) -> tuple[Pipeline, Settings]:
    over = {}
    if args.data_dir:
        over["data_dir"] = Path(args.data_dir)
    if args.logs_dir:
        over["logs_dir"] = Path(args.logs_dir)
    settings = Settings.from_env(**over)
    mode = getattr(args, "mode", None) or settings.extraction_mode
    policy = Policy.load()
    try:
        storage = build_storage(settings)
    except StorageError as exc:
        print(json.dumps({"error_code": "PO_SOURCE_UNAVAILABLE", "message": str(exc), "retryable": False}, indent=2))
        sys.exit(2)
    provider = None
    if mode in ("live", "mock") and getattr(args, "command", "") == "process":
        if mode == "live" and not settings.api_key:
            print(json.dumps(ErrorResponse(error_code="LLM_UNAVAILABLE", retryable=False,
                  message="LLM_API_KEY is not set. Copy .env.example to .env, or use --mode mock.").model_dump(mode="json"), indent=2))
            sys.exit(2)
        provider = build_provider(settings, mode)
    return Pipeline(settings, policy, storage, provider, mode), settings


def summary(r: RunResult) -> str:
    inv = r.extracted
    head = f"Run {r.run_id} | mode: {r.extraction_mode}" + (f" ({r.provider}/{r.model})" if r.model else "")
    lines = [head, f"RESULT: {r.label.value.upper()}   (confidence: {r.validation.confidence}, "
                   f"human confirmation required)"]
    if inv:
        lines.append(f"Invoice {inv.invoice_number} | {inv.vendor_name} | PO: {inv.po_number or 'none'} | "
                     f"total: {inv.total if inv.total is not None else 'NOT FOUND'} {inv.currency or ''}")
    lines.append("Findings:" if r.findings else "Findings: none, all checks passed")
    lines += [f"  [{f.severity.value}] {f.code.value}: {f.message}" for f in r.findings]
    if r.vendor_email:
        lines += ["", "--- Draft vendor email (not sent) ---", r.vendor_email, "--- end draft ---"]
    t = r.timings_ms
    lines += ["", f"Time: {t['total']} ms (extraction {t['extraction']} ms, rules {t['rules']} ms, "
                  f"rate-limit wait {t['rate_limit_wait']} ms)"]
    if r.token_usage:
        lines.append(f"Tokens: {r.token_usage}")
    if r.error:
        lines.append(f"Note: {r.error.error_code.value}: {r.error.message}")
    lines.append(f"Next: python -m ap.cli confirm {r.run_id} --decision approve|hold|reject")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ap", description="AP invoice exception handling (v0)")
    sub = p.add_subparsers(dest="command", required=True)
    pr = sub.add_parser("process", help="Process one invoice PDF")
    pr.add_argument("invoice")
    pr.add_argument("--mode", choices=["live", "mock"], help="Extraction mode (default from EXTRACTION_MODE)")
    pr.add_argument("--no-cache", action="store_true", help="Ignore cached extractions (use for evaluation)")
    pr.add_argument("--json", action="store_true", help="Print the full RunResult JSON")
    cf = sub.add_parser("confirm", help="Human confirmation: record the final decision")
    cf.add_argument("run_id")
    cf.add_argument("--decision", required=True, choices=["approve", "hold", "reject"])
    cf.add_argument("--note", default="")
    nf = sub.add_parser("notify", help="Send a manager escalation for a run (human-triggered)")
    nf.add_argument("run_id")
    nf.add_argument("--note", default="")
    hs = sub.add_parser("history", help="List recent runs")
    for s in (pr, cf, nf, hs):
        s.add_argument("--data-dir")
        s.add_argument("--logs-dir")
    args = p.parse_args(argv)
    pipeline, _ = build(args)

    if args.command == "process":
        res = pipeline.process_file(args.invoice, use_cache=not args.no_cache)
        if isinstance(res, ErrorResponse):
            print(res.model_dump_json(indent=2))
            return 2
        print(res.model_dump_json(indent=2) if args.json else summary(res))
        return 0
    if args.command == "history":
        try:
            rows = pipeline.storage.recent_runs(15)
        except StorageError as exc:
            print(f"Could not read the run history: {exc}")
            return 2
        for h in rows:
            print(f"{h['started_at']}  {h['run_id']}  {h['label']:<14} {h['file']}")
        return 0
    if args.command == "notify":
        svc = AppService(pipeline.settings, pipeline.policy, pipeline, pipeline.storage, build_notifier(pipeline.settings))
        o = svc.escalate(args.run_id, args.note)
        print(("Sent: " if o.sent else "Not sent: ") + o.detail)
        return 0 if o.sent else 2
    try:
        out = pipeline.confirm(args.run_id, args.decision, args.note)
    except StorageError as exc:
        print(f"Your decision could not be saved: {exc}")
        return 2
    if isinstance(out, ErrorResponse):
        print(out.model_dump_json(indent=2))
        return 2
    print(f"Recorded: run {out['run_id']} -> {out['human_decision']} (recommended: {out['recommended_label']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
