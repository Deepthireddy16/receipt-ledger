from datetime import date
from decimal import Decimal

from receipts.normalize import clean_text, parse_amount, parse_date


def test_dates_are_read_day_first():
    assert parse_date("03/04/2018") == date(2018, 4, 3)
    assert parse_date("25-12-2018") == date(2018, 12, 25)
    assert parse_date("25 DEC 2018") == date(2018, 12, 25)


def test_unknown_date_returns_none():
    assert parse_date("yesterday") is None
    assert parse_date(None) is None


def test_amounts():
    assert parse_amount("RM 12.50") == Decimal("12.50")
    assert parse_amount("12.5") == Decimal("12.50")
    assert parse_amount("1,234.00") == Decimal("1234.00")
    assert parse_amount("abc") is None


def test_clean_text_ignores_case_spacing_punctuation():
    assert clean_text("ABC Sdn. Bhd.") == clean_text("abc sdn bhd")
