"""Manager escalation notifications (Day 3, integration 2).

Design rules
- A notification is sent only when a HUMAN presses "Send to manager" (or runs `ap notify`). Nothing is sent automatically.
- The message contains only: vendor, invoice number, PO, total, recommended label, reason titles, run id.
  Never invoice text, line items, bank details or the vendor email draft (data minimisation).
- The webhook URL is a secret: it is never logged and never shown in error messages.
- A failed notification never loses or changes the invoice result; the caller shows a warning and the reviewer
  can contact the manager another way.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional, Protocol

from ap.config import Policy
from ap.fmt import money
from ap.friendly import finding_info
from ap.logging_setup import get_logger
from ap.schemas import Label, RunResult

log = get_logger("ap.notify")


@dataclass
class NotifyOutcome:
    sent: bool
    backend: str
    detail: str


class Notifier(Protocol):
    backend: str

    def send(self, text: str) -> NotifyOutcome: ...


def should_suggest_escalation(result: RunResult, policy: Policy) -> bool:
    """Exceptions above the manager threshold (or with an unknown total) should go to the manager."""
    if result.label == Label.APPROVE:
        return False
    inv = result.extracted
    total = inv.total if inv else None
    return total is None or total > Decimal(str(policy.manager_escalation_threshold))


def build_message(result: RunResult, reviewer_note: str = "") -> str:
    inv = result.extracted
    vendor = inv.vendor_name if inv and inv.vendor_name else "unknown vendor"
    number = inv.invoice_number if inv and inv.invoice_number else "unknown number"
    total = f"{money(inv.total)} {inv.currency or ''}".strip() if inv and inv.total is not None else "total not found"
    po = inv.po_number if inv and inv.po_number else "no PO"
    reasons = "; ".join(finding_info(f.code).title for f in result.findings if f.severity.value != "info") or "none"
    lines = [f"Invoice {number} from {vendor} needs manager review.",
             f"Recommendation: {result.label.value} | Total: {total} | PO: {po}",
             f"Reasons: {reasons}",
             f"Run: {result.run_id}"]
    if reviewer_note.strip():
        lines.append(f"Reviewer note: {reviewer_note.strip()[:300]}")
    return "\n".join(lines)


class NullNotifier:
    backend = "none"

    def send(self, text: str) -> NotifyOutcome:
        return NotifyOutcome(False, self.backend, "Notifications are switched off (NOTIFY_BACKEND=none).")


class ConsoleNotifier:
    """Prints instead of sending. For demos and for running without Slack."""
    backend = "console"

    def __init__(self):
        self.sent_messages: list[str] = []

    def send(self, text: str) -> NotifyOutcome:
        self.sent_messages.append(text)
        print("--- manager notification (console) ---\n" + text + "\n--------------------------------------")
        return NotifyOutcome(True, self.backend, "Printed to the console (no Slack configured).")


class SlackWebhookNotifier:
    backend = "slack"

    def __init__(self, webhook_url: str, timeout: float = 10.0, max_attempts: int = 3,
                 sleep: Callable[[float], None] = time.sleep):
        self._url, self.timeout, self.max_attempts, self._sleep = webhook_url, timeout, max_attempts, sleep

    def send(self, text: str) -> NotifyOutcome:
        body = json.dumps({"text": text}).encode()
        last = "unknown error"
        for attempt in range(1, self.max_attempts + 1):
            req = urllib.request.Request(self._url, data=body, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:      # noqa: S310 - https webhook
                    if 200 <= resp.status < 300:
                        log.info("slack_sent", extra={"attempt": attempt})
                        return NotifyOutcome(True, self.backend, "Sent to Slack.")
                    last = f"HTTP {resp.status}"
            except urllib.error.HTTPError as exc:
                last = f"HTTP {exc.code}"
                if exc.code in (400, 401, 403, 404):
                    return NotifyOutcome(False, self.backend,
                                         f"Slack did not accept the message ({last}). Check SLACK_WEBHOOK_URL in .env.")
                if exc.code == 429 or exc.code >= 500:
                    try:
                        delay = min(float(exc.headers.get("Retry-After", 2 ** attempt)), 30.0)
                    except (TypeError, ValueError):
                        delay = float(2 ** attempt)
                    if attempt < self.max_attempts:
                        self._sleep(delay)
                    continue
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = type(exc).__name__
                if attempt < self.max_attempts:
                    self._sleep(2 ** attempt)
                continue
        log.warning("slack_failed", extra={"reason": last})
        return NotifyOutcome(False, self.backend,
                             f"Slack could not be reached ({last}). The invoice result is saved; contact the manager another way.")
