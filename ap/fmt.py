"""Number formatting helpers (shared by rules and templates so text always matches evidence)."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

TWO = Decimal("0.01")


def d2(x) -> Decimal:
    return Decimal(str(x)).quantize(TWO, rounding=ROUND_HALF_UP)


def money(x) -> str:
    return f"{d2(x):,.2f}"


def pct(x) -> str:
    return f"{d2(x):.2f}"


def qty(x) -> str:
    x = Decimal(str(x))
    return str(int(x)) if x == x.to_integral_value() else str(x.normalize())
