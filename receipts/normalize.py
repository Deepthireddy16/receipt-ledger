"""Turns raw text into values we can compare fairly.

"RM 12.50" and "12.5" are the same amount. "25/12/2018" and "25-12-2018"
are the same date. These functions make that comparison possible.
All of them return None when they cannot understand the input.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# Day-first formats come first because SROIE receipts are from Malaysia,
# where 03/04/2018 means 3 April. This is an assumption about the data.
DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
    "%Y-%m-%d", "%Y/%m/%d",
    "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%b-%y", "%d %b %y",
    "%b %d, %Y", "%B %d, %Y",
]


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    cleaned = " ".join(text.split())
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(text: str | None) -> Decimal | None:
    """Reads a money amount. Uses Decimal because floats round money wrongly.

    Known limit: treats a comma as a thousands separator, so the European
    style "1.234,56" is read wrongly.
    """
    if not text:
        return None
    digits = re.sub(r"[^\d.,-]", "", text).replace(",", "")
    try:
        return Decimal(digits).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def clean_text(text: str | None) -> str | None:
    """Lower-case and keep only letters and digits, so spacing and punctuation do not matter."""
    if not text:
        return None
    return re.sub(r"[^a-z0-9]", "", text.casefold()) or None
