import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock


# ── calc_quantity 테스트 ──────────────────────────────────────

def test_calc_quantity_kospi200():
    """코스피200 선물: 예산 2,500,000원, 지수 2500pt → 0계약 (예산 < 계약가치)"""
    from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
    s = BaseDomesticFuturesStrategy.__new__(BaseDomesticFuturesStrategy)
    # 계약가치 = 2500 × 250,000 = 625,000,000원 > 예산 2,500,000원 → 0
    result = s.calc_quantity(2_500_000, 2500.0, 250_000)
    assert result == 0


def test_calc_quantity_mini_kospi200():
    """미니코스피200: 예산 500,000원, 지수 2500pt, 승수 50,000원 → 0계약"""
    from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
    s = BaseDomesticFuturesStrategy.__new__(BaseDomesticFuturesStrategy)
    result = s.calc_quantity(500_000, 2500.0, 50_000)
    assert result == 0


def test_calc_quantity_enough_budget():
    """예산 200,000,000원, 지수 2500, 승수 250,000 → 0계약 (예산 < 계약가치)"""
    from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
    s = BaseDomesticFuturesStrategy.__new__(BaseDomesticFuturesStrategy)
    # 계약가치 = 2500 × 250,000 = 625,000,000 > 200,000,000 → 0
    result = s.calc_quantity(200_000_000, 2500.0, 250_000)
    assert result == 0


def test_calc_quantity_large_budget():
    """예산이 계약 가치보다 크면 1 이상 반환"""
    from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
    s = BaseDomesticFuturesStrategy.__new__(BaseDomesticFuturesStrategy)
    # 계약가치 = 2500 × 250,000 = 625,000,000
    # 예산 = 1,300,000,000 → 2계약
    result = s.calc_quantity(1_300_000_000, 2500.0, 250_000)
    assert result == 2


# ── _update_trailing 테스트 (코인봇과 동일 로직) ────────────────

def make_state(target=10.0, stop=-2.5):
    return {
        'target_ror': target, 'stop_loss': stop,
        'highest_ror': 0.0, 'trailing_active': False, 'phase': 1,
    }


def test_trailing_phase1_no_change():
    """Phase1: highest < 3% → stop_loss 변동 없음"""
    from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
    s = BaseDomesticFuturesStrategy.__new__(BaseDomesticFuturesStrategy)
    s.PHASE2_THRESHOLD    = 3.0
    s.PHASE3_THRESHOLD    = 6.0
    s.BREAKEVEN_STOP      = 0.5
    s.TRAILING_RATIO      = 0.6
    s.TIGHT_TRAILING_RATIO = 0.75
    s._state = make_state()
    s._update_trailing(2.0)
    assert s._state['phase'] == 1
    assert s._state['stop_loss'] == -2.5


def test_trailing_phase2_breakeven():
    """Phase2: highest >= 3% → stop_loss >= BREAKEVEN_STOP"""
    from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
    s = BaseDomesticFuturesStrategy.__new__(BaseDomesticFuturesStrategy)
    s.PHASE2_THRESHOLD    = 3.0
    s.PHASE3_THRESHOLD    = 6.0
    s.BREAKEVEN_STOP      = 0.5
    s.TRAILING_RATIO      = 0.6
    s.TIGHT_TRAILING_RATIO = 0.75
    s._state = make_state()
    s._update_trailing(4.0)
    assert s._state['phase'] == 2
    assert s._state['stop_loss'] >= 0.5


def test_trailing_phase3_trailing():
    """Phase3: highest >= 6% → trailing_active=True, stop >= highest*0.6"""
    from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
    s = BaseDomesticFuturesStrategy.__new__(BaseDomesticFuturesStrategy)
    s.PHASE2_THRESHOLD    = 3.0
    s.PHASE3_THRESHOLD    = 6.0
    s.BREAKEVEN_STOP      = 0.5
    s.TRAILING_RATIO      = 0.6
    s.TIGHT_TRAILING_RATIO = 0.75
    s._state = make_state()
    s._update_trailing(8.0)
    assert s._state['phase'] == 3
    assert s._state['trailing_active'] is True
    assert s._state['stop_loss'] >= 8.0 * 0.6


def test_trailing_phase4_tight():
    """Phase4: highest >= target → stop >= highest*0.75"""
    from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
    s = BaseDomesticFuturesStrategy.__new__(BaseDomesticFuturesStrategy)
    s.PHASE2_THRESHOLD    = 3.0
    s.PHASE3_THRESHOLD    = 6.0
    s.BREAKEVEN_STOP      = 0.5
    s.TRAILING_RATIO      = 0.6
    s.TIGHT_TRAILING_RATIO = 0.75
    s._state = make_state(target=10.0)
    s._update_trailing(12.0)
    assert s._state['phase'] == 4
    assert s._state['stop_loss'] >= 12.0 * 0.75
