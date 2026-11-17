"""Heuristic scan for instructions embedded in invoice text (prompt-injection indicators)."""
from __future__ import annotations

import re

PATTERNS = {
    "ignore_instructions": r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+(instructions|directions)",
    "mark_approved": r"(mark|set|treat|record)\s+(this\s+)?(invoice\s+)?(as\s+)?(approved|paid)",
    "skip_checks": r"skip\s+(all\s+|any\s+|the\s+)?(checks?|validation|verification)",
    "role_prefix": r"\b(system|assistant|developer)\s*(note|prompt|message|instruction)s?\s*:",
    "disregard_rules": r"disregard\s+(the\s+)?(rules|policy|instructions)",
    "do_not_flag": r"do\s+not\s+(flag|report|review)",
}
_COMPILED = {k: re.compile(v, re.IGNORECASE) for k, v in PATTERNS.items()}


def scan(text: str) -> list[str]:
    """Return the NAMES of matched patterns (never the matched text, to keep logs clean)."""
    return [name for name, rx in _COMPILED.items() if rx.search(text or "")]
