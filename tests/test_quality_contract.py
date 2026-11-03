"""Fast contract tests for core business logic. Run: pytest -q"""
from decimal import Decimal

def signed_amount(direction, amount):
    amt = Decimal(str(amount))
    return amt if direction == "CREDIT" else -amt

def is_late(event_ts, ingested_ts, sla_hours=24):
    return (ingested_ts-event_ts).total_seconds() > sla_hours*3600

def test_money_is_decimal_and_directional():
    assert signed_amount("CREDIT", "10.20") == Decimal("10.20")
    assert signed_amount("DEBIT", "10.20") == Decimal("-10.20")

def test_exactly_sla_boundary_is_not_late():
    from datetime import datetime, timedelta, timezone
    event = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert not is_late(event, event+timedelta(hours=24))
    assert is_late(event, event+timedelta(hours=24, seconds=1))

def test_reversal_offsets_original():
    original = signed_amount("DEBIT", "120.00")
    reversal = signed_amount("CREDIT", "120.00")
    assert original + reversal == Decimal("0.00")

def test_currency_reference_is_explicit():
    allowed = {"ZAR", "USD", "GBP", "EUR"}
    assert "ZAR" in allowed
    assert "ZRX" not in allowed

def test_spike_threshold_logic():
    avg, stddev = 1000, 100
    assert 1400 > avg + 3*stddev
    assert not (1290 > avg + 3*stddev)
