"""Vendor-name comparison that tolerates legal-suffix and punctuation differences but not look-alike names."""
from __future__ import annotations

import difflib
import re

_SUFFIXES = {"ltd", "limited", "inc", "incorporated", "llc", "llp", "co", "company", "corp", "corporation", "gmbh",
             "ag", "plc", "srl", "sa", "pvt", "pty", "bv", "nv", "the"}
SIMILARITY = 0.95   # high on purpose: look-alike vendor names are a known fraud pattern


def vendor_key(name: str) -> str:
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    core = [w for w in words if w not in _SUFFIXES]
    return "".join(core or words)


def same_vendor(a: str, b: str) -> bool:
    ka, kb = vendor_key(a), vendor_key(b)
    return bool(ka and kb) and (ka == kb or difflib.SequenceMatcher(None, ka, kb).ratio() >= SIMILARITY)
