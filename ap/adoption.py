"""Adoption and quality metrics computed from the system's own logs (no extra tracking, no personal data).

Everything is derived from three records the tool already keeps: runs (every check), processed (every human decision) and
events (escalations). Two things cannot be derived from logs and need a person: hands-on time saved (sample and time a few
invoices with a stopwatch) and wrongful approvals (a second person audits a sample of approved invoices).
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

AGREE = {"Approve": {"approve"}, "Reject (hold)": {"hold", "reject"}}


def _t(s) -> Optional[datetime]:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _pct(vals, q):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round(q * (len(vals) - 1))))] if vals else None


def compute(runs: list[dict], processed: list[dict], events: list[dict], *, since: Optional[datetime] = None,
            until: Optional[datetime] = None, price_in: Optional[float] = None, price_out: Optional[float] = None) -> dict:
    def in_window(d):
        t = _t(d.get("started_at"))
        return t is not None and (since is None or t >= since) and (until is None or t <= until)

    runs = [r for r in runs if in_window(r)]
    ids = {r["run_id"] for r in runs}
    dec = {p["run_id"]: p for p in processed if p.get("run_id") in ids and str(p.get("human_decision", "")).lower() != "void"}
    n = len(runs)
    days = Counter((_t(r["started_at"]).date().isoformat()) for r in runs)
    labels = Counter(r["label"] for r in runs)
    recordable = [r for r in runs if (r.get("extracted") or {}).get("vendor_name") and (r.get("extracted") or {}).get("invoice_number")]

    approve_over = [r for r in runs if r["label"] == "Approve" and r["run_id"] in dec and dec[r["run_id"]]["human_decision"] not in AGREE["Approve"]]
    approve_total = [r for r in runs if r["label"] == "Approve" and r["run_id"] in dec]
    hold_over = [r for r in runs if r["label"] == "Reject (hold)" and r["run_id"] in dec and dec[r["run_id"]]["human_decision"] not in AGREE["Reject (hold)"]]
    hold_total = [r for r in runs if r["label"] == "Reject (hold)" and r["run_id"] in dec]
    review = [r for r in runs if r["label"] == "Needs review" and r["run_id"] in dec]
    review_outcome = Counter(dec[r["run_id"]]["human_decision"] for r in review)

    ttd = []
    for r in runs:
        if r["run_id"] in dec:
            a, b = _t(r["started_at"]), _t(dec[r["run_id"]].get("confirmed_at"))
            if a and b and b >= a:
                ttd.append((b - a).total_seconds() / 60)

    codes = Counter(f["code"] for r in runs for f in r.get("findings", []) if f.get("severity") != "info")
    errors = Counter(r["error"]["error_code"] for r in runs if r.get("error"))
    lat = [r["timings_ms"].get("total", 0) - r["timings_ms"].get("rate_limit_wait", 0) for r in runs if r.get("extraction_mode") == "live"]
    tin = [(r.get("token_usage") or {}).get("prompt_tokens", 0) for r in runs if r.get("extraction_mode") == "live"]
    tout = [(r.get("token_usage") or {}).get("completion_tokens", 0) for r in runs if r.get("extraction_mode") == "live"]

    held = defaultdict(float)
    for r in runs:
        d = dec.get(r["run_id"])
        inv = r.get("extracted") or {}
        if d and d["human_decision"] in ("hold", "reject") and r["label"] != "Approve" and inv.get("total"):
            held[inv.get("currency") or "?"] += float(inv["total"])
    ev = Counter(e.get("event") for e in events if e.get("run_id") in ids)

    return {
        "window": {"since": since.isoformat() if since else None, "until": until.isoformat() if until else None},
        "runs": n, "active_days": len(days), "runs_per_active_day": (n / len(days)) if days else 0, "by_day": dict(sorted(days.items())),
        "data_origin": dict(Counter(r.get("data_origin", "?") for r in runs)),
        "modes": dict(Counter(r.get("extraction_mode", "?") for r in runs)),
        "labels": dict(labels),
        "decisions_recorded": len(dec), "follow_through": (len(dec) / len(recordable)) if recordable else None, "recordable_runs": len(recordable),
        "approve_overridden": (len(approve_over), len(approve_total)),
        "hold_overridden": (len(hold_over), len(hold_total)),
        "review_outcomes": dict(review_outcome),
        "time_to_decision_min": {"median": statistics.median(ttd) if ttd else None, "p90": _pct(ttd, .9), "n": len(ttd)},
        "findings": dict(codes.most_common()), "duplicates_caught": codes.get("EXACT_DUPLICATE", 0) + codes.get("POSSIBLE_DUPLICATE", 0),
        "amount_held_or_rejected": dict(held),
        "errors": dict(errors), "error_rate": (sum(errors.values()) / n) if n else None,
        "retry_rate": (sum(1 for r in runs if (r.get("validation") or {}).get("attempts") == 2) / n) if n else None,
        "confidence": dict(Counter((r.get("validation") or {}).get("confidence") for r in runs)),
        "escalations": {"sent": ev.get("escalated_to_manager", 0), "failed": ev.get("escalation_failed", 0)},
        "live_latency_ms": {"p50": statistics.median(lat) if lat else None, "p95": _pct(lat, .95), "n": len(lat)},
        "tokens_mean": {"in": statistics.mean(tin) if tin else None, "out": statistics.mean(tout) if tout else None},
        "notional_cost_total": (sum((a * price_in + b * price_out) / 1e6 for a, b in zip(tin, tout))
                                if price_in is not None and price_out is not None and tin else None),
    }


def _r(t):
    return "n/a" if not t[1] else f"{t[0]} of {t[1]}"


def markdown(m: dict) -> str:
    o = ["# Adoption and quality report", ""]
    synthetic = m["data_origin"] and set(m["data_origin"]) <= {"synthetic"}
    if m["runs"] == 0:
        return "# Adoption and quality report\n\nNo runs in this window.\n"
    if synthetic or set(m["modes"]) <= {"mock", "ground_truth"}:
        o += ["**READ THIS FIRST: every run in this window is synthetic or used demo-mode extraction "
              f"(data origin {m['data_origin']}, modes {m['modes']}). These figures describe test traffic, NOT real adoption "
              "or real quality. Do not quote them as results.**", ""]
    w = m["window"]
    t = m["time_to_decision_min"]
    ttd_text = "n/a" if t["median"] is None else "%.1f / %.1f (n=%d)" % (t["median"], t["p90"], t["n"])
    o += [f"Window: {w['since'] or 'start'} to {w['until'] or 'now'}", "", "## Adoption", "",
          "| Metric | Value |", "|---|---|",
          f"| Invoices checked | {m['runs']} |", f"| Days with at least one check | {m['active_days']} |",
          f"| Checks per active day | {m['runs_per_active_day']:.1f} |",
          f"| Decisions recorded (follow-through) | {m['decisions_recorded']} of {m['recordable_runs']} checks that could be recorded"
          + (f" ({100 * m['follow_through']:.0f}%)" if m['follow_through'] is not None else "") + " |",
          f"| Time from check to recorded decision (median / 90th pct, minutes; includes idle time) | {ttd_text} |",
          f"| Manager escalations sent / failed | {m['escalations']['sent']} / {m['escalations']['failed']} |", "",
          "## Recommendations vs people", "",
          "| Metric | Value | How to read it |", "|---|---|---|",
          f"| Recommendation mix | {m['labels']} | Share sent to a human is the review burden |",
          f"| 'Approve' recommendations that a person overrode | {_r(m['approve_overridden'])} | Possible missed exceptions the person caught. Review every one |",
          f"| 'Reject (hold)' recommendations that a person approved | {_r(m['hold_overridden'])} | False alarms, or a person error. Review every one |",
          f"| How people resolved 'Needs review' | {m['review_outcomes'] or 'n/a'} | |", "",
          "## Value", "",
          f"- Possible or exact duplicates flagged: {m['duplicates_caught']}",
          f"- Total value held or rejected after a flag (by currency): {m['amount_held_or_rejected'] or 'none'}",
          f"- Most common reasons for review: {dict(list(m['findings'].items())[:6]) or 'none'}", "",
          "## Reliability", "",
          f"- Runs with an error or degraded result: {m['error_rate'] * 100:.1f}% {m['errors'] or ''}",
          f"- Runs needing an extraction retry: {m['retry_rate'] * 100:.1f}%", f"- Confidence levels: {m['confidence']}"]
    if m["live_latency_ms"]["n"]:
        o.append(f"- Live latency (median / 95th pct, ms, excluding throttle waits): {m['live_latency_ms']['p50']:.0f} / {m['live_latency_ms']['p95']:.0f}")
        if m["notional_cost_total"] is not None:
            o.append(f"- Notional cost of the window: ${m['notional_cost_total']:.4f}")
    o += ["", "## Not measurable from logs (do these by hand)", "",
          "- **Hands-on time saved**: time 10 invoices a week with a stopwatch and compare with Baseline A.",
          "- **Wrongful approvals**: a second person re-checks a random sample of approved invoices every week.",
          "- **Who used it**: the tool records no user identity by design."]
    return "\n".join(o) + "\n"
