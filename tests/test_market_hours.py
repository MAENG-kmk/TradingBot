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


def test_overseas_open_weekday():
    """CME 평일 12시 KST → 장중"""
    from overseas_futures.runner import OverseasFuturesRunner
    r = OverseasFuturesRunner.__new__(OverseasFuturesRunner)
    dt = datetime(2026, 4, 27, 12, 0, 0)
    assert r._is_market_open(now=dt) is True


def test_overseas_closed_saturday_morning():
    """토요일 08시 KST (CME 마감 후) → 장 마감"""
    from overseas_futures.runner import OverseasFuturesRunner
    r = OverseasFuturesRunner.__new__(OverseasFuturesRunner)
    dt = datetime(2026, 4, 25, 8, 0, 0)  # 토요일 08시 (hm=800 >= 600)
    assert r._is_market_open(now=dt) is False
