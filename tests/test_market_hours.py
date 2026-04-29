import pytest
from datetime import datetime


def test_domestic_open_weekday_morning():
    """평일 10시 KST → 장중"""
    from domestic_futures.runner import DomesticFuturesRunner
    r = DomesticFuturesRunner.__new__(DomesticFuturesRunner)
    dt = datetime(2026, 4, 27, 10, 0, 0)
    assert r._is_market_open(now=dt) is True


def test_domestic_closed_afternoon():
    """평일 16시 KST (15:45 이후) → 장 마감"""
    from domestic_futures.runner import DomesticFuturesRunner
    r = DomesticFuturesRunner.__new__(DomesticFuturesRunner)
    dt = datetime(2026, 4, 27, 16, 0, 0)
    assert r._is_market_open(now=dt) is False


def test_domestic_open_night_session():
    """평일 20시 KST (야간장) → 장중"""
    from domestic_futures.runner import DomesticFuturesRunner
    r = DomesticFuturesRunner.__new__(DomesticFuturesRunner)
    dt = datetime(2026, 4, 27, 20, 0, 0)
    assert r._is_market_open(now=dt) is True


def test_domestic_closed_weekend():
    """토요일 → 장 마감"""
    from domestic_futures.runner import DomesticFuturesRunner
    r = DomesticFuturesRunner.__new__(DomesticFuturesRunner)
    dt = datetime(2026, 4, 25, 10, 0, 0)  # 토요일
    assert r._is_market_open(now=dt) is False
