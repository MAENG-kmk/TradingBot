# KIS 선물 자동매매 통합 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 한국투자증권(KIS) REST API를 사용해 국내선물·해외선물 자동매매를 기존 암호화폐 봇 위에 추가한다.

**Architecture:** 공유 KIS 클라이언트(토큰 자동갱신) + 독립 시장 모듈 2개(국내/해외). 기존 코인봇 전략 로직(레짐필터 + BB추세추종 + VB + 4단계 트레일링)을 KIS API로 이식하며, main.py 루프에 runner 2개를 추가하는 것으로 통합한다.

**Tech Stack:** Python 3.10, requests, pandas, numpy, KIS OpenAPI REST, MongoDB(기존), Telegram(기존), tools/trendFilter.py(기존)

> **⚠️ KIS API 엔드포인트 주의:** 구현 전 https://apiportal.koreainvestment.com 에서 각 TR_ID와 파라미터를 반드시 확인할 것. 아래 TR_ID는 2026년 4월 기준 최선 정보이나, KIS는 TR_ID를 업데이트할 수 있다.

---

## 파일 구조 (생성/수정 대상)

```
생성:
  kis/__init__.py
  kis/client.py

  domestic_futures/__init__.py
  domestic_futures/base_strategy.py
  domestic_futures/scanner.py
  domestic_futures/runner.py

  overseas_futures/__init__.py
  overseas_futures/base_strategy.py
  overseas_futures/scanner.py
  overseas_futures/runner.py

  tests/test_kis_client.py
  tests/test_futures_strategy.py
  tests/test_market_hours.py

수정:
  SecretVariables.py   ← KIS 키 추가
  main.py              ← runner 2개 추가
```

---

## Task 1: KIS 클라이언트 + SecretVariables

**Files:**
- Create: `kis/__init__.py`
- Create: `kis/client.py`
- Create: `tests/test_kis_client.py`
- Modify: `SecretVariables.py`

- [ ] **Step 1: SecretVariables.py에 KIS 키 추가**

```python
# SecretVariables.py 하단에 추가
KIS_APP_KEY    = "PSzhYRWCD3gA2RiPEA6meJQuqZYLb3OD5C7d"
KIS_APP_SECRET = "a+UTB0ZUJCRPDjQrjvqA2WCu7tkYzsnQ/wWJbdLTTDnPNfpCzoBQqHQWatr070wmHW/VUAzeEFRn0ltImgeWL2J0A7mBlmvyUZ825YH4AlNl2iuoVko0xqzBDkX2PbO2/RcmrcU5LYNYMNqBMwvcIru8772k9A7ndPhU0QpeGb3eZl8KoUI="
```

- [ ] **Step 2: 테스트 먼저 작성**

```python
# tests/test_kis_client.py
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

import sys, os
sys.path.insert(0, os.path.abspath("."))
from kis.client import KISClient


FAKE_KEY    = "test_key"
FAKE_SECRET = "test_secret"
FAKE_TOKEN  = "test_access_token"


def make_client_with_token():
    """이미 토큰이 발급된 상태의 클라이언트 반환"""
    client = KISClient(FAKE_KEY, FAKE_SECRET)
    client._token     = FAKE_TOKEN
    client._token_exp = datetime.now() + timedelta(hours=23)
    return client


def test_token_injected_in_headers():
    """get() 호출 시 Authorization 헤더가 자동 주입되어야 한다"""
    client = make_client_with_token()
    with patch("kis.client.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"output": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client.get("/some/path", "TR_ID_TEST", {"param": "value"})

        call_kwargs = mock_get.call_args
        headers = call_kwargs[1]["headers"]
        assert headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
        assert headers["appkey"]        == FAKE_KEY
        assert headers["appsecret"]     == FAKE_SECRET
        assert headers["tr_id"]         == "TR_ID_TEST"


def test_token_refresh_when_expired():
    """토큰이 만료되었을 때 _issue_token()이 호출되어야 한다"""
    client = KISClient(FAKE_KEY, FAKE_SECRET)
    client._token     = "old_token"
    client._token_exp = datetime.now() - timedelta(minutes=1)  # 만료

    with patch.object(client, "_issue_token") as mock_issue, \
         patch("kis.client.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        mock_issue.side_effect = lambda: setattr(client, '_token', 'new_token') or \
                                         setattr(client, '_token_exp',
                                                 datetime.now() + timedelta(hours=24))

        client.get("/path", "TR", {})
        mock_issue.assert_called_once()


def test_token_not_refreshed_when_valid():
    """토큰이 유효하면 _issue_token()이 호출되지 않아야 한다"""
    client = make_client_with_token()
    with patch.object(client, "_issue_token") as mock_issue, \
         patch("kis.client.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client.get("/path", "TR", {})
        mock_issue.assert_not_called()
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
cd /Users/kimmingi/코딩/Project/TradingBot
python -m pytest tests/test_kis_client.py -v
```
Expected: `ModuleNotFoundError: No module named 'kis'`

- [ ] **Step 4: kis/__init__.py 생성**

```python
# kis/__init__.py
```

- [ ] **Step 5: kis/client.py 구현**

```python
# kis/client.py
import requests
from datetime import datetime, timedelta


class KISClient:
    BASE_URL = "https://openapi.koreainvestment.com:9443"

    def __init__(self, app_key: str, app_secret: str):
        self._app_key    = app_key
        self._app_secret = app_secret
        self._token      = None
        self._token_exp  = None

    # ── 토큰 관리 ────────────────────────────────────────────────

    def _issue_token(self):
        url  = f"{self.BASE_URL}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey":     self._app_key,
            "appsecret":  self._app_secret,
        }
        resp = requests.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._token     = data["access_token"]
        expires_in      = int(data.get("expires_in", 86400))
        self._token_exp = datetime.now() + timedelta(seconds=expires_in)

    def _ensure_token(self):
        if (self._token is None or
                self._token_exp is None or
                datetime.now() >= self._token_exp - timedelta(minutes=5)):
            self._issue_token()

    # ── REST 래퍼 ────────────────────────────────────────────────

    def _headers(self, tr_id: str) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "appkey":        self._app_key,
            "appsecret":     self._app_secret,
            "tr_id":         tr_id,
            "Content-Type":  "application/json",
        }

    def get(self, path: str, tr_id: str, params: dict) -> dict:
        self._ensure_token()
        url  = f"{self.BASE_URL}{path}"
        resp = requests.get(url, headers=self._headers(tr_id),
                            params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, tr_id: str, body: dict) -> dict:
        self._ensure_token()
        url  = f"{self.BASE_URL}{path}"
        resp = requests.post(url, headers=self._headers(tr_id),
                             json=body, timeout=10)
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
python -m pytest tests/test_kis_client.py -v
```
Expected: `3 passed`

- [ ] **Step 7: 커밋**

```bash
git add kis/ tests/test_kis_client.py SecretVariables.py
git commit -m "feat: add KIS REST client with auto token refresh"
```

---

## Task 2: 국내선물 베이스 전략

**Files:**
- Create: `domestic_futures/__init__.py`
- Create: `domestic_futures/base_strategy.py`
- Create: `tests/test_futures_strategy.py`

**배경 지식:**
- 코스피200 선물 종목코드 예시: `101W09` (만기월 변동, KIS API로 현물월 코드 조회 필요)
- 국내선물 계약 승수: 코스피200=250,000원, 미니코스피200=50,000원, 코스닥150=10,000원
- KIS 국내선물 분봉 API: `GET /uapi/domestic-futureoption/v1/quotations/inquire-time-futureoption`
  - TR_ID: `FHMIF10010200` (확인 필요: KIS API 포털 → 국내선물옵션 → 시세 → 분봉)
  - params: FID_COND_MRKT_DIV_CODE=F, FID_INPUT_ISCD={종목코드}, FID_INPUT_HOUR_1=060000, FID_PW_DATA_INCU_YN=Y
- KIS 국내선물 주문: `POST /uapi/domestic-futureoption/v1/trading/order`
  - TR_ID 매수(실전): `JTCE1002U` / 매도(실전): `JTCE1001U`
- KIS 국내선물 잔고: `GET /uapi/domestic-futureoption/v1/trading/inquire-balance`
  - TR_ID: `CTFO6118R`

- [ ] **Step 1: 테스트 먼저 작성**

```python
# tests/test_futures_strategy.py
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, os.path.abspath("."))


# ── calc_quantity 테스트 ──────────────────────────────────────

def test_calc_quantity_kospi200():
    """코스피200 선물: 예산 2,500,000원, 지수 2500pt → 1계약"""
    from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
    s = BaseDomesticFuturesStrategy.__new__(BaseDomesticFuturesStrategy)
    # 코스피200 승수=250,000원/pt, 지수=2500pt → 계약당 가치=625,000,000원
    # 예산=2,500,000원 → 0.004 → floor → 0계약
    result = s.calc_quantity(2_500_000, 2500.0, 250_000)
    assert result == 0


def test_calc_quantity_mini_kospi200():
    """미니코스피200: 예산 500,000원, 지수 2500pt, 승수 50,000원 → 0계약"""
    from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
    s = BaseDomesticFuturesStrategy.__new__(BaseDomesticFuturesStrategy)
    result = s.calc_quantity(500_000, 2500.0, 50_000)
    assert result == 0


def test_calc_quantity_enough_budget():
    """충분한 예산: 200,000,000원, 지수 2500, 승수 250,000 → 0계약"""
    # 계약 가치 = 2500 × 250,000 = 625,000,000
    # 예산 200,000,000 < 계약 가치 → 0
    from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
    s = BaseDomesticFuturesStrategy.__new__(BaseDomesticFuturesStrategy)
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
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_futures_strategy.py -v
```
Expected: `ModuleNotFoundError: No module named 'domestic_futures'`

- [ ] **Step 3: domestic_futures/__init__.py 생성**

```python
# domestic_futures/__init__.py
```

- [ ] **Step 4: domestic_futures/base_strategy.py 구현**

```python
# domestic_futures/base_strategy.py
import math
import time
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.abspath("."))

from tools.trendFilter import checkMarketRegime
from tools.getAtr import getATR
from tools.telegram import send_message
from MongoDB_python.client import (
    addDataToMongoDB, saveEntryDetails,
    getEntryDetails, deleteEntryDetails,
)


class BaseDomesticFuturesStrategy:
    """
    국내선물 베이스 전략.
    coins/base_strategy.py와 동일한 전략 로직(레짐필터+추세추종+VB+4단계 트레일링).
    KIS API 호출 부분만 다르다.

    계약 승수 (subclass에서 오버라이드):
      KOSPI200      : 250,000원/pt
      MINI_KOSPI200 : 50,000원/pt
      KOSDAQ150     : 10,000원/pt
    """

    # ── 전략 파라미터 (코인봇과 동일) ──────────────────────────────
    TR_BB_PERIOD     = 20
    TR_BB_STD        = 2.0
    RSI_PERIOD       = 14
    RSI_OVERBUY      = 80
    RSI_OVERSELL     = 20
    ADX_THRESHOLD    = 20
    VOL_PERIOD       = 20
    VOL_MULT         = 1.5
    ATR_MULTIPLIER   = 2.2

    DEFAULT_TARGET_ROR   = 10.0
    DEFAULT_STOP_LOSS    = -2.5
    PHASE2_THRESHOLD     = 3.0
    PHASE3_THRESHOLD     = 6.0
    BREAKEVEN_STOP       = 0.5
    TRAILING_RATIO       = 0.6
    TIGHT_TRAILING_RATIO = 0.75
    TIME_EXIT_SECONDS_1  = 86400
    TIME_EXIT_ROR_1      = 1.0
    TIME_EXIT_SECONDS_2  = 172800
    TIME_EXIT_ROR_2      = 2.0
    VOLATILITY_SPIKE     = 3.0

    VB_K             = 0.3
    VB_MIN_RANGE_PCT = 0.3
    MR_SLOPE_THRESHOLD = 0.05

    # ── 종목별 오버라이드 ────────────────────────────────────────
    SYMBOL            = ""         # 종목코드 (스캐너가 동적으로 설정)
    CONTRACT_MULT     = 250_000    # 계약 승수 (원)
    CURRENCY          = "KRW"

    # ── KIS API TR_ID ─────────────────────────────────────────────
    # ⚠️ 반드시 KIS API 포털에서 확인: https://apiportal.koreainvestment.com
    _TR_CANDLE   = "FHMIF10010200"   # 분봉 (60분봉 사용)
    _TR_ORDER_BUY  = "JTCE1002U"     # 매수 (실전)
    _TR_ORDER_SELL = "JTCE1001U"     # 매도 (실전)
    _TR_BALANCE  = "CTFO6118R"       # 잔고조회

    def __init__(self, kis):
        """
        Args:
            kis: KISClient 인스턴스
        """
        self.kis    = kis
        self._state = None

    # ================================================================
    #  KIS API — 서브클래스에서 오버라이드 가능
    # ================================================================

    def get_candles(self, symbol: str, limit: int = 300) -> pd.DataFrame | None:
        """
        KIS 국내선물 60분봉 조회 → 4H 캔들로 리샘플.
        limit: 반환할 4H 봉 수. 내부에서 limit×4 개의 60분봉을 요청.
        """
        try:
            # 60분봉 기준 limit×4개 요청 (4H 캔들 한 개 = 60분봉 4개)
            # KIS는 한 번에 최대 100~120봉 반환 → 여러 번 호출 필요할 수 있음
            # 현재는 단순하게 1회 호출로 가능한 만큼만 가져옴
            params = {
                "FID_COND_MRKT_DIV_CODE": "F",
                "FID_INPUT_ISCD":         symbol,
                "FID_INPUT_HOUR_1":       "060000",  # 최근 N봉 기준 시각
                "FID_PW_DATA_INCU_YN":    "Y",
            }
            data = self.kis.get(
                "/uapi/domestic-futureoption/v1/quotations/inquire-time-futureoption",
                self._TR_CANDLE,
                params,
            )
            rows = data.get("output2", [])
            if not rows:
                return None

            df = pd.DataFrame(rows)
            # KIS 컬럼명 → 표준화 (실제 컬럼명은 KIS API 문서 확인 필요)
            df = df.rename(columns={
                "stck_bsop_date": "date",
                "bsop_hour":      "time",
                "stck_oprc":      "Open",
                "stck_hgpr":      "High",
                "stck_lwpr":      "Low",
                "stck_prpr":      "Close",
                "cntg_vol":       "Volume",
            })
            df["datetime"] = pd.to_datetime(
                df["date"] + df["time"], format="%Y%m%d%H%M%S"
            )
            df = df.set_index("datetime").sort_index()
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()

            # 60분봉 → 4H 리샘플
            df_4h = df.resample("4h").agg({
                "Open": "first", "High": "max",
                "Low": "min", "Close": "last", "Volume": "sum",
            }).dropna()

            return df_4h.tail(limit) if len(df_4h) >= limit else df_4h
        except Exception as e:
            print(f"  [국내선물] 캔들 조회 오류 {symbol}: {e}")
            return None

    def get_balance(self) -> tuple[float, float]:
        """(total_krw, available_krw) 반환"""
        try:
            data = self.kis.get(
                "/uapi/domestic-futureoption/v1/trading/inquire-balance",
                self._TR_BALANCE,
                {"CANO": "", "ACNT_PRDT_CD": "03"},   # 계좌번호는 KIS 설정에서 가져와야 함
            )
            output = data.get("output", {})
            total     = float(output.get("tot_asst_evlu_amt", 0))
            available = float(output.get("ord_psbl_cash", 0))
            return total, available
        except Exception as e:
            print(f"  [국내선물] 잔고 조회 오류: {e}")
            return 0.0, 0.0

    def get_positions(self) -> list[dict]:
        """
        보유 포지션 목록 반환.
        [{'symbol': ..., 'side': 'long'|'short', 'qty': ...,
          'entry_price': ..., 'ror': ..., 'amount': ...}]
        """
        try:
            data = self.kis.get(
                "/uapi/domestic-futureoption/v1/trading/inquire-balance",
                self._TR_BALANCE,
                {"CANO": "", "ACNT_PRDT_CD": "03"},
            )
            positions = []
            for item in data.get("output1", []):
                qty = int(item.get("hldg_qty", 0))
                if qty == 0:
                    continue
                side = "long" if int(item.get("seln_buy_dvsn_cd", "2")) == 2 else "short"
                entry_price  = float(item.get("pchs_avg_pric", 0))
                current_price = float(item.get("prpr", entry_price))
                if entry_price > 0:
                    ror = ((current_price - entry_price) / entry_price * 100
                           if side == "long"
                           else (entry_price - current_price) / entry_price * 100)
                else:
                    ror = 0.0
                positions.append({
                    "symbol":      item.get("pdno", ""),
                    "side":        side,
                    "qty":         qty,
                    "amount":      qty,
                    "entry_price": entry_price,
                    "profit":      float(item.get("evlu_pfls_amt", 0)),
                    "ror":         ror,
                })
            return positions
        except Exception as e:
            print(f"  [국내선물] 포지션 조회 오류: {e}")
            return []

    def place_order(self, symbol: str, side: str, qty: int) -> bool:
        """
        Args:
            side: 'BUY' | 'SELL'
            qty: 계약 수
        """
        try:
            tr_id = self._TR_ORDER_BUY if side == "BUY" else self._TR_ORDER_SELL
            body  = {
                "CANO":          "",          # 계좌번호 (KIS 설정)
                "ACNT_PRDT_CD":  "03",
                "SLL_BUY_DVSN_CD": "02" if side == "BUY" else "01",
                "SHTN_PDNO":     symbol,
                "ORD_QTY":       str(qty),
                "UNIT_PRICE":    "0",
                "NMPR_TYPE_CD":  "",
                "KIS_PRVS_RSQN_UNIQ_NO": "",
                "CTAC_TLNO":     "",
                "FUOP_ITEM_DVSN_CD": "",
                "ORD_DVSN":      "01",        # 시장가
            }
            resp = self.kis.post(
                "/uapi/domestic-futureoption/v1/trading/order",
                tr_id,
                body,
            )
            rt_cd = resp.get("rt_cd", "1")
            return rt_cd == "0"
        except Exception as e:
            print(f"  [국내선물] 주문 오류 {symbol} {side}: {e}")
            return False

    def calc_quantity(self, budget: float, price: float,
                      contract_mult: int | None = None) -> int:
        """
        계약 수 = floor(budget / (price × contract_mult))
        Args:
            budget: 투자 예산 (원)
            price: 현재 선물 지수/가격
            contract_mult: 계약 승수 (None이면 self.CONTRACT_MULT 사용)
        """
        mult = contract_mult if contract_mult is not None else self.CONTRACT_MULT
        contract_value = price * mult
        if contract_value <= 0:
            return 0
        return math.floor(budget / contract_value)

    def _get_current_price(self, symbol: str) -> float:
        """현재가 조회"""
        try:
            data = self.kis.get(
                "/uapi/domestic-futureoption/v1/quotations/inquire-price",
                "FHMIF10000000",
                {"FID_COND_MRKT_DIV_CODE": "F", "FID_INPUT_ISCD": symbol},
            )
            return float(data.get("output", {}).get("stck_prpr", 0))
        except Exception:
            return 0.0

    # ================================================================
    #  진입 신호 (코인봇과 동일 로직)
    # ================================================================

    def check_entry_signal(self, symbol: str):
        """
        Returns:
            ('long'|'short', target_ror, mode, meta) | (None, 0, None, None)
        """
        df = self.get_candles(symbol, limit=300)
        if df is None or len(df) < 50:
            return None, 0, None, None

        closes = df["Close"].values.astype(float)

        regime, adx, slope = checkMarketRegime(
            df, adx_threshold=self.ADX_THRESHOLD,
            slope_threshold=self.MR_SLOPE_THRESHOLD,
        )
        if regime in ("uptrend", "downtrend"):
            return self._trend_following_signal(df, closes)
        else:
            return self._vb_signal(df, closes)

    def _trend_following_signal(self, df, closes):
        if len(closes) < self.TR_BB_PERIOD:
            return None, 0, None, None

        bb_closes = closes[-self.TR_BB_PERIOD:]
        bb_mid    = float(np.mean(bb_closes))
        bb_std    = float(np.std(bb_closes))
        bb_upper  = bb_mid + self.TR_BB_STD * bb_std
        bb_lower  = bb_mid - self.TR_BB_STD * bb_std

        current_price = closes[-1]
        rsi           = self._rsi(closes)
        macd, signal  = self._macd(closes)
        if macd is None:
            return None, 0, None, None

        atr        = getATR(df)
        target_ror = abs(atr / closes[-1]) * 100

        if rsi >= self.RSI_OVERBUY or rsi <= self.RSI_OVERSELL:
            return None, 0, None, None

        volumes  = df["Volume"].values.astype(float)
        avg_vol  = float(np.mean(volumes[-self.VOL_PERIOD:]))
        cur_vol  = volumes[-1]
        if avg_vol <= 0 or cur_vol < avg_vol * self.VOL_MULT:
            return None, 0, None, None

        if current_price > bb_upper and macd > signal:
            return "long", target_ror, "trend_following", {}
        if current_price < bb_lower and macd < signal:
            return "short", target_ror, "trend_following", {}

        return None, 0, None, None

    def _vb_signal(self, df, closes):
        if len(df) < 2:
            return None, 0, None, None

        prev       = df.iloc[-2]
        cur        = df.iloc[-1]
        prev_range = float(prev["High"] - prev["Low"])
        prev_close = float(prev["Close"])

        if prev_close <= 0 or prev_range <= 0:
            return None, 0, None, None
        if prev_range / prev_close * 100 < self.VB_MIN_RANGE_PCT:
            return None, 0, None, None

        cur_open  = float(cur["Open"])
        cur_high  = float(cur["High"])
        cur_low   = float(cur["Low"])
        long_trig  = cur_open + self.VB_K * prev_range
        short_trig = cur_open - self.VB_K * prev_range

        long_ok  = cur_high >= long_trig  and long_trig  > cur_open
        short_ok = cur_low  <= short_trig and short_trig < cur_open

        if long_ok and short_ok:
            return None, 0, None, None

        import calendar
        candle_open_ts  = calendar.timegm(df.index[-1].timetuple())
        candle_close_ts = candle_open_ts + 4 * 3600

        if long_ok:
            return "long", 0, "vb", {"candle_close_ts": candle_close_ts}
        if short_ok:
            return "short", 0, "vb", {"candle_close_ts": candle_close_ts}

        return None, 0, None, None

    # ================================================================
    #  청산 (코인봇과 동일 로직)
    # ================================================================

    def manage_exit(self, position: dict):
        """포지션 청산 조건 체크 및 청산 실행"""
        symbol = position["symbol"]
        ror    = position["ror"]

        if self._state is None:
            entry_doc     = getEntryDetails(symbol)
            recovered_mode = entry_doc.get("mode", "trend_following") if entry_doc else "trend_following"
            if recovered_mode == "vb":
                candle_close_ts = entry_doc.get("candle_close_ts", 0)
                if not candle_close_ts:
                    enter_time      = entry_doc.get("enter_time", time.time())
                    candle_sec      = 4 * 3600
                    candle_close_ts = (enter_time // candle_sec + 1) * candle_sec
                self._init_state(0, mode="vb",
                                 vb_meta={"candle_close_ts": candle_close_ts})
            else:
                self._init_state(0)

        mode = self._state.get("mode", "trend_following")

        # VB 모드: 캔들 종료 후 청산
        if mode == "vb":
            candle_close_ts = self._state.get("candle_close_ts", 0)
            entry_time      = self._state.get("entry_time", 0)
            now             = time.time()
            vb_timeout = now >= candle_close_ts or (entry_time and now - entry_time > 8 * 3600)
            if vb_timeout:
                reason = f"VB다음봉청산(ROR:{ror:.1f}%)"
                self._close_position(position, reason)
            else:
                remaining_min = (candle_close_ts - now) / 60
                print(f"  유지: {symbol} | VB | ROR:{ror:.1f}% | 청산까지:{remaining_min:.0f}분")
            return

        # 추세추종 모드: 4단계 트레일링
        self._update_trailing(ror)
        should_close, reason, is_hard_stop = False, "", False

        if ror < self._state["stop_loss"]:
            should_close = True
            if self._state["trailing_active"]:
                reason = f"트레일링스탑(최고:{self._state['highest_ror']:.1f}%→{ror:.1f}%)"
            else:
                reason = f"손절({ror:.1f}%)"
                is_hard_stop = True

        if not should_close:
            should_close, reason = self._check_time()

        if should_close:
            if not is_hard_stop and self._should_hold(position["side"], position["symbol"]):
                print(f"  보류: {symbol} | {reason} → 동일방향 시그널 존재")
            else:
                self._close_position(position, reason)
        else:
            phase_names = {1: "초기", 2: "본전확보", 3: "트레일링", 4: "타이트"}
            phase = phase_names.get(self._state["phase"], "?")
            print(f"  유지: {symbol} | ROR:{ror:.1f}% | 손절:{self._state['stop_loss']:.1f}% | {phase}")

    def _close_position(self, position: dict, reason: str):
        symbol    = position["symbol"]
        close_side = "SELL" if position["side"] == "long" else "BUY"
        success   = self.place_order(symbol, close_side, position["qty"])

        if success:
            try:
                total, _ = self.get_balance()
                data = dict(position)
                data["closeTime"] = int(datetime.now().timestamp())
                data["balance"]   = total
                addDataToMongoDB([data])
            except Exception:
                pass

            deleteEntryDetails(symbol)
            msg = (f"🔴 [국내선물] {symbol} 청산 ({reason}) "
                   f"| ROR:{position['ror']:.1f}%")
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass
            self._state = None
        else:
            msg = f"❌ [국내선물] {symbol} 청산 주문 실패 — 수동 확인 필요"
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass

    def _init_state(self, target_ror, mode="trend_following", vb_meta=None):
        if mode == "vb":
            if vb_meta and vb_meta.get("candle_close_ts"):
                candle_close_ts = vb_meta["candle_close_ts"]
            else:
                now = time.time()
                candle_close_ts = (now // (4 * 3600) + 1) * (4 * 3600)
            self._state = {
                "target_ror": 0, "stop_loss": 0,
                "entry_time": time.time(),
                "candle_close_ts": candle_close_ts,
                "highest_ror": 0, "trailing_active": False,
                "phase": 1, "mode": "vb",
            }
            return

        target = target_ror if target_ror > 5 else self.DEFAULT_TARGET_ROR
        stop   = -0.33 * target if target_ror > 5 else self.DEFAULT_STOP_LOSS
        self._state = {
            "target_ror": target, "stop_loss": stop,
            "entry_time": time.time(),
            "highest_ror": 0, "trailing_active": False,
            "phase": 1, "mode": "trend_following",
        }

    def _update_trailing(self, ror: float):
        s = self._state
        if ror > s["highest_ror"]:
            s["highest_ror"] = ror
        highest = s["highest_ror"]

        if highest < self.PHASE2_THRESHOLD:
            s["phase"] = 1
        elif highest < self.PHASE3_THRESHOLD:
            s["phase"] = 2
            s["stop_loss"] = max(s["stop_loss"], self.BREAKEVEN_STOP)
        elif highest < s["target_ror"]:
            s["phase"] = 3
            s["trailing_active"] = True
            s["stop_loss"] = max(s["stop_loss"], highest * self.TRAILING_RATIO)
        else:
            s["phase"] = 4
            s["trailing_active"] = True
            s["stop_loss"] = max(s["stop_loss"], highest * self.TIGHT_TRAILING_RATIO)

    def _check_time(self):
        elapsed = time.time() - self._state["entry_time"]
        ror     = self._state["highest_ror"]
        if elapsed > self.TIME_EXIT_SECONDS_1 and ror < self.TIME_EXIT_ROR_1:
            return True, f"시간초과(24h, ROR<{self.TIME_EXIT_ROR_1}%)"
        if elapsed > self.TIME_EXIT_SECONDS_2 and ror < self.TIME_EXIT_ROR_2:
            return True, f"시간초과(48h, ROR<{self.TIME_EXIT_ROR_2}%)"
        return False, ""

    def _should_hold(self, current_side: str, symbol: str) -> bool:
        try:
            sig, _, _, _ = self.check_entry_signal(symbol)
            return sig is not None and sig == current_side
        except Exception:
            return False

    # ── 지표 유틸 ────────────────────────────────────────────────

    def _rsi(self, closes):
        if len(closes) < self.RSI_PERIOD + 1:
            return 50
        s     = pd.Series(closes)
        delta = s.diff()
        gain  = delta.where(delta > 0, 0).rolling(self.RSI_PERIOD).mean()
        loss  = (-delta.where(delta < 0, 0)).rolling(self.RSI_PERIOD).mean()
        rs    = gain / loss
        return float((100 - (100 / (1 + rs))).iloc[-1])

    def _macd(self, closes):
        if len(closes) < 26:
            return None, None
        s      = pd.Series(closes)
        ema12  = s.ewm(span=12, adjust=False).mean()
        ema26  = s.ewm(span=26, adjust=False).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        return float(macd.iloc[-1]), float(signal.iloc[-1])
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
python -m pytest tests/test_futures_strategy.py -v
```
Expected: `7 passed`

- [ ] **Step 6: 커밋**

```bash
git add domestic_futures/ tests/test_futures_strategy.py
git commit -m "feat: add domestic futures base strategy"
```

---

## Task 3: 국내선물 스캐너

**Files:**
- Create: `domestic_futures/scanner.py`

**국내선물 화이트리스트 종목코드:**
KIS 국내선물은 만기월마다 코드가 바뀐다 (예: 코스피200 선물 = `101W09` 형태).
스캐너는 KIS API에서 활성 종목 목록을 조회해 화이트리스트에 해당하는 것만 사용한다.

- [ ] **Step 1: domestic_futures/scanner.py 구현**

```python
# domestic_futures/scanner.py
import sys, os
sys.path.insert(0, os.path.abspath("."))

from tools.trendFilter import calculate_adx, checkMarketRegime

# 유동성 상위 국내선물 상품 prefix (만기월 무관)
# KIS 종목코드는 앞 3자리가 상품 구분
DOMESTIC_WHITELIST_PREFIX = {
    "101": "코스피200선물",
    "105": "미니코스피200선물",
    "106": "코스닥150선물",
    "167": "3년국채선물",
    "175": "10년국채선물",
    "196": "달러선물",
    "197": "엔선물",
    "198": "유로선물",
}

# ⚠️ 활성 종목 조회 TR_ID: KIS API 포털 → 국내선물옵션 → 기본정보 → 종목 마스터 확인 필요
_TR_MASTER = "FHMIF10000000"


class DomesticFuturesScanner:
    def __init__(self, kis, strategy):
        self.kis      = kis
        self.strategy = strategy

    def get_active_symbols(self) -> list[str]:
        """
        KIS에서 현재 활성 국내선물 종목코드 목록 조회.
        화이트리스트 prefix에 해당하는 것만 반환.
        """
        try:
            data = self.kis.get(
                "/uapi/domestic-futureoption/v1/quotations/inquire-futureoption-list",
                _TR_MASTER,
                {"FID_COND_MRKT_DIV_CODE": "F", "FID_COND_SCR_DIV_CODE": "20"},
            )
            symbols = []
            for item in data.get("output", []):
                code = item.get("shtn_pdno", "")
                prefix = code[:3]
                if prefix in DOMESTIC_WHITELIST_PREFIX:
                    symbols.append(code)
            return symbols
        except Exception as e:
            print(f"  [국내선물] 종목 목록 조회 오류: {e}")
            return []

    def scan(self, current_symbols: list[str], limit: int) -> list[str]:
        """
        ADX 상위 limit개 종목 반환.
        Args:
            current_symbols: 이미 보유 중인 종목코드 목록 (제외 대상)
            limit: 반환할 최대 종목 수
        Returns:
            진입 후보 종목코드 리스트 (ADX 내림차순)
        """
        if limit <= 0:
            return []

        active = self.get_active_symbols()
        candidates = []

        for symbol in active:
            if symbol in current_symbols:
                continue
            df = self.strategy.get_candles(symbol, limit=100)
            if df is None or len(df) < 50:
                continue
            try:
                _, adx, _ = checkMarketRegime(df, adx_threshold=self.strategy.ADX_THRESHOLD)
                # 진입 시그널 있어야 후보 등록
                sig, _, _, _ = self.strategy.check_entry_signal(symbol)
                if sig is not None:
                    candidates.append((symbol, adx))
            except Exception:
                continue

        # ADX 내림차순 정렬 → 상위 limit개
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [sym for sym, _ in candidates[:limit]]
```

- [ ] **Step 2: 커밋**

```bash
git add domestic_futures/scanner.py
git commit -m "feat: add domestic futures scanner with ADX ranking"
```

---

## Task 4: 국내선물 러너

**Files:**
- Create: `domestic_futures/runner.py`
- Create: `tests/test_market_hours.py`

- [ ] **Step 1: 장 시간 테스트 먼저 작성**

```python
# tests/test_market_hours.py
import pytest
from unittest.mock import patch
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.abspath("."))


def test_domestic_open_weekday_morning():
    """평일 10시 KST → 장중"""
    from domestic_futures.runner import DomesticFuturesRunner
    r = DomesticFuturesRunner.__new__(DomesticFuturesRunner)
    # 2026-04-27 10:00 KST (월요일) = UTC 01:00
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
    """토요일 07시 KST (CME 마감 후) → 장 마감"""
    from overseas_futures.runner import OverseasFuturesRunner
    r = OverseasFuturesRunner.__new__(OverseasFuturesRunner)
    dt = datetime(2026, 4, 25, 8, 0, 0)  # 토요일 08시
    assert r._is_market_open(now=dt) is False
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_market_hours.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: domestic_futures/runner.py 구현**

```python
# domestic_futures/runner.py
import asyncio
import time
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.abspath("."))

from tools.telegram import send_message
from MongoDB_python.client import saveEntryDetails
from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
from domestic_futures.scanner import DomesticFuturesScanner


class DomesticFuturesRunner:
    MAX_POSITIONS = 5
    POSITION_FRAC = 0.1

    def __init__(self, kis):
        self.strategy = BaseDomesticFuturesStrategy(kis)
        self.scanner  = DomesticFuturesScanner(kis, self.strategy)

    def run(self):
        """60초마다 main.py에서 호출"""
        try:
            positions = self.strategy.get_positions()

            # 청산은 항상 (장 시간 무관)
            self._manage_exits(positions)

            if not self._is_market_open():
                return

            empty = self.MAX_POSITIONS - len(positions)
            if empty <= 0:
                return

            held       = [p["symbol"] for p in positions]
            candidates = self.scanner.scan(held, limit=empty)
            total, available = self.strategy.get_balance()

            for symbol in candidates:
                self._try_enter(symbol, total, available)

        except Exception as e:
            msg = f"[국내선물] runner 오류: {e}"
            print(f"  ❌ {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass

    def _manage_exits(self, positions: list[dict]):
        for pos in positions:
            try:
                self.strategy.manage_exit(pos)
            except Exception as e:
                print(f"  ❌ [국내선물] 청산 오류 {pos.get('symbol')}: {e}")

    def _try_enter(self, symbol: str, total: float, available: float):
        budget = total * self.POSITION_FRAC
        if available < budget:
            return

        sig, target_ror, mode, meta = self.strategy.check_entry_signal(symbol)
        if sig is None:
            return

        price = self.strategy._get_current_price(symbol)
        if price <= 0:
            return

        qty = self.strategy.calc_quantity(budget, price)
        if qty <= 0:
            print(f"  [국내선물] {symbol} 예산 부족 (budget={budget:,.0f}원, price={price:.1f})")
            return

        order_side = "BUY" if sig == "long" else "SELL"
        success    = self.strategy.place_order(symbol, order_side, qty)

        if success:
            vb_meta = meta if mode == "vb" else None
            self.strategy._init_state(target_ror, mode=mode, vb_meta=vb_meta)
            candle_close_ts = self.strategy._state.get("candle_close_ts") if mode == "vb" else None
            saveEntryDetails(symbol, mode, sig, price, candle_close_ts)
            tag = "📈VB" if mode == "vb" else "✅TR"
            msg = f"{tag} [국내선물] {symbol} {sig.upper()} 진입 | qty:{qty} | target:{target_ror:.1f}%"
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass
        else:
            print(f"  ❌ [국내선물] {symbol} 주문 실패")

    def _is_market_open(self, now: datetime | None = None) -> bool:
        """
        국내선물 장 시간 체크 (KST 기준).
        주간: 09:00~15:45
        야간: 18:00~익일 05:00
        주말(토/일 주간) 제외.
        now: 테스트용 datetime 주입 (None이면 현재 시각)
        """
        if now is None:
            now = datetime.now()

        weekday = now.weekday()  # 0=월 ... 6=일
        h, m    = now.hour, now.minute
        hm      = h * 100 + m

        # 일요일 → 장 마감
        if weekday == 6:
            return False

        # 토요일: 00:00~06:00만 야간장 연장 (금요일 야간 이월)
        if weekday == 5:
            return hm < 600   # 06:00 전까지만

        # 평일: 주간 09:00~15:45 | 야간 18:00~익일 05:00
        in_day   = 900 <= hm <= 1545
        in_night = hm >= 1800 or hm < 500
        return in_day or in_night
```

- [ ] **Step 4: 테스트 통과 (국내 부분만)**

```bash
python -m pytest tests/test_market_hours.py::test_domestic_open_weekday_morning \
                 tests/test_market_hours.py::test_domestic_closed_afternoon \
                 tests/test_market_hours.py::test_domestic_open_night_session \
                 tests/test_market_hours.py::test_domestic_closed_weekend -v
```
Expected: `4 passed`

- [ ] **Step 5: 커밋**

```bash
git add domestic_futures/runner.py tests/test_market_hours.py
git commit -m "feat: add domestic futures runner with market hours check"
```

---

## Task 5: 해외선물 베이스 전략

**Files:**
- Create: `overseas_futures/__init__.py`
- Create: `overseas_futures/base_strategy.py`

**배경 지식:**
- 해외선물 4H 캔들: KIS 해외선물 분봉 API → 60분봉 리샘플
- TR_ID 분봉: `HHDFS76200100` (확인 필요: KIS 포털 → 해외선물옵션 → 시세 → 분봉)
- TR_ID 주문 매수(실전): `JTTT1002U` / 매도(실전): `JTTT1001U`
- TR_ID 잔고: `CTOS5011R`
- 계약 승수 (USD 기준): ES=$50/pt, NQ=$20/pt, CL=$1,000/bbl, GC=$100/oz
- 잔고는 USD 기준 (달러 예수금)

- [ ] **Step 1: overseas_futures/__init__.py 생성**

```python
# overseas_futures/__init__.py
```

- [ ] **Step 2: overseas_futures/base_strategy.py 구현**

`BaseDomesticFuturesStrategy`와 동일한 전략 로직, KIS API 경로와 TR_ID만 다르다.

```python
# overseas_futures/base_strategy.py
import math
import time
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.abspath("."))

from tools.trendFilter import checkMarketRegime
from tools.getAtr import getATR
from tools.telegram import send_message
from MongoDB_python.client import (
    addDataToMongoDB, saveEntryDetails,
    getEntryDetails, deleteEntryDetails,
)


# 해외선물 계약 승수 (USD 기준)
OVERSEAS_CONTRACT_MULT = {
    "ES":  50,      # S&P500 E-mini
    "NQ":  20,      # NASDAQ E-mini
    "CL":  1000,    # WTI 원유
    "GC":  100,     # 금
    "SI":  5000,    # 은 (oz당 $5000)
    "6E":  125000,  # 유로FX (유로 × 125,000)
    "6J":  12500000,# 엔FX (엔 × 12,500,000)
    "RTY": 50,      # Russell 2000 E-mini
}


class BaseOverseasFuturesStrategy:
    """
    해외선물 베이스 전략.
    BaseDomesticFuturesStrategy와 전략 로직 동일,
    KIS API 경로/TR_ID/통화 단위만 다르다.
    """

    # ── 전략 파라미터 (코인봇, 국내선물과 동일) ────────────────────
    TR_BB_PERIOD     = 20
    TR_BB_STD        = 2.0
    RSI_PERIOD       = 14
    RSI_OVERBUY      = 80
    RSI_OVERSELL     = 20
    ADX_THRESHOLD    = 20
    VOL_PERIOD       = 20
    VOL_MULT         = 1.5
    ATR_MULTIPLIER   = 2.2

    DEFAULT_TARGET_ROR   = 10.0
    DEFAULT_STOP_LOSS    = -2.5
    PHASE2_THRESHOLD     = 3.0
    PHASE3_THRESHOLD     = 6.0
    BREAKEVEN_STOP       = 0.5
    TRAILING_RATIO       = 0.6
    TIGHT_TRAILING_RATIO = 0.75
    TIME_EXIT_SECONDS_1  = 86400
    TIME_EXIT_ROR_1      = 1.0
    TIME_EXIT_SECONDS_2  = 172800
    TIME_EXIT_ROR_2      = 2.0
    VOLATILITY_SPIKE     = 3.0

    VB_K             = 0.3
    VB_MIN_RANGE_PCT = 0.3
    MR_SLOPE_THRESHOLD = 0.05

    # ── KIS API TR_ID ─────────────────────────────────────────────
    # ⚠️ KIS 포털에서 확인 필요
    _TR_CANDLE     = "HHDFS76200100"  # 해외선물 분봉
    _TR_ORDER_BUY  = "JTTT1002U"      # 매수 (실전)
    _TR_ORDER_SELL = "JTTT1001U"      # 매도 (실전)
    _TR_BALANCE    = "CTOS5011R"      # 잔고조회

    def __init__(self, kis):
        self.kis    = kis
        self._state = None

    # ================================================================
    #  KIS API — 해외선물 전용
    # ================================================================

    def get_candles(self, symbol: str, limit: int = 300) -> pd.DataFrame | None:
        """KIS 해외선물 60분봉 → 4H 리샘플"""
        try:
            params = {
                "FID_COND_MRKT_DIV_CODE": "Q",          # 해외선물
                "FID_INPUT_ISCD":         symbol,
                "FID_INPUT_HOUR_1":       "060000",
                "FID_PW_DATA_INCU_YN":    "Y",
            }
            data = self.kis.get(
                "/uapi/overseas-futureoption/v1/quotations/inquire-time-futureoption",
                self._TR_CANDLE,
                params,
            )
            rows = data.get("output2", [])
            if not rows:
                return None

            df = pd.DataFrame(rows)
            df = df.rename(columns={
                "stck_bsop_date": "date",
                "bsop_hour":      "time",
                "ovrs_nmix_prpr": "Close",
                "ovrs_nmix_oprc": "Open",
                "ovrs_nmix_hgpr": "High",
                "ovrs_nmix_lwpr": "Low",
                "acml_vol":       "Volume",
            })
            df["datetime"] = pd.to_datetime(
                df["date"] + df["time"], format="%Y%m%d%H%M%S"
            )
            df = df.set_index("datetime").sort_index()
            for col in ["Open", "High", "Low", "Close", "Volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()

            df_4h = df.resample("4h").agg({
                "Open": "first", "High": "max",
                "Low": "min", "Close": "last", "Volume": "sum",
            }).dropna()

            return df_4h.tail(limit) if len(df_4h) >= limit else df_4h
        except Exception as e:
            print(f"  [해외선물] 캔들 조회 오류 {symbol}: {e}")
            return None

    def get_balance(self) -> tuple[float, float]:
        """(total_usd, available_usd)"""
        try:
            data = self.kis.get(
                "/uapi/overseas-futureoption/v1/trading/inquire-balance",
                self._TR_BALANCE,
                {"CANO": "", "ACNT_PRDT_CD": "03", "OVRS_EXCG_CD": "CME"},
            )
            output    = data.get("output", {})
            total     = float(output.get("tot_asst_evlu_amt", 0))
            available = float(output.get("ord_psbl_cash", 0))
            return total, available
        except Exception as e:
            print(f"  [해외선물] 잔고 조회 오류: {e}")
            return 0.0, 0.0

    def get_positions(self) -> list[dict]:
        """보유 포지션 목록"""
        try:
            data = self.kis.get(
                "/uapi/overseas-futureoption/v1/trading/inquire-balance",
                self._TR_BALANCE,
                {"CANO": "", "ACNT_PRDT_CD": "03", "OVRS_EXCG_CD": "CME"},
            )
            positions = []
            for item in data.get("output1", []):
                qty = int(item.get("hldg_qty", 0))
                if qty == 0:
                    continue
                side = "long" if int(item.get("seln_buy_dvsn_cd", "2")) == 2 else "short"
                entry_price   = float(item.get("pchs_avg_pric", 0))
                current_price = float(item.get("prpr", entry_price))
                ror = ((current_price - entry_price) / entry_price * 100
                       if side == "long"
                       else (entry_price - current_price) / entry_price * 100) if entry_price > 0 else 0.0
                positions.append({
                    "symbol": item.get("pdno", ""),
                    "side": side, "qty": qty, "amount": qty,
                    "entry_price": entry_price,
                    "profit": float(item.get("evlu_pfls_amt", 0)),
                    "ror": ror,
                })
            return positions
        except Exception as e:
            print(f"  [해외선물] 포지션 조회 오류: {e}")
            return []

    def place_order(self, symbol: str, side: str, qty: int) -> bool:
        try:
            tr_id = self._TR_ORDER_BUY if side == "BUY" else self._TR_ORDER_SELL
            body  = {
                "CANO":            "",
                "ACNT_PRDT_CD":    "03",
                "OVRS_EXCG_CD":    "CME",
                "PDNO":            symbol,
                "SLL_BUY_DVSN_CD": "02" if side == "BUY" else "01",
                "ORD_QTY":         str(qty),
                "OVRS_ORD_UNPR":   "0",
                "ORD_DVSN":        "01",   # 시장가
            }
            resp  = self.kis.post(
                "/uapi/overseas-futureoption/v1/trading/order",
                tr_id, body,
            )
            return resp.get("rt_cd", "1") == "0"
        except Exception as e:
            print(f"  [해외선물] 주문 오류 {symbol} {side}: {e}")
            return False

    def calc_quantity(self, budget: float, price: float,
                      contract_mult: int | None = None) -> int:
        """계약 수 = floor(budget_usd / (price × contract_mult))"""
        mult = contract_mult if contract_mult is not None else 50  # 기본 ES 승수
        contract_value = price * mult
        if contract_value <= 0:
            return 0
        return math.floor(budget / contract_value)

    def _get_current_price(self, symbol: str) -> float:
        try:
            data = self.kis.get(
                "/uapi/overseas-futureoption/v1/quotations/inquire-price",
                "HHDFS76200200",
                {"FID_COND_MRKT_DIV_CODE": "Q", "FID_INPUT_ISCD": symbol},
            )
            return float(data.get("output", {}).get("ovrs_nmix_prpr", 0))
        except Exception:
            return 0.0

    # ================================================================
    #  진입/청산 — BaseDomesticFuturesStrategy와 완전히 동일한 로직
    # ================================================================

    def check_entry_signal(self, symbol: str):
        df = self.get_candles(symbol, limit=300)
        if df is None or len(df) < 50:
            return None, 0, None, None
        closes = df["Close"].values.astype(float)
        regime, adx, slope = checkMarketRegime(
            df, adx_threshold=self.ADX_THRESHOLD,
            slope_threshold=self.MR_SLOPE_THRESHOLD,
        )
        if regime in ("uptrend", "downtrend"):
            return self._trend_following_signal(df, closes)
        return self._vb_signal(df, closes)

    def _trend_following_signal(self, df, closes):
        if len(closes) < self.TR_BB_PERIOD:
            return None, 0, None, None
        bb_closes = closes[-self.TR_BB_PERIOD:]
        bb_mid    = float(np.mean(bb_closes))
        bb_std    = float(np.std(bb_closes))
        bb_upper  = bb_mid + self.TR_BB_STD * bb_std
        bb_lower  = bb_mid - self.TR_BB_STD * bb_std
        current   = closes[-1]
        rsi       = self._rsi(closes)
        macd, sig = self._macd(closes)
        if macd is None or rsi >= self.RSI_OVERBUY or rsi <= self.RSI_OVERSELL:
            return None, 0, None, None
        atr        = getATR(df)
        target_ror = abs(atr / closes[-1]) * 100
        volumes    = df["Volume"].values.astype(float)
        avg_vol    = float(np.mean(volumes[-self.VOL_PERIOD:]))
        if avg_vol <= 0 or volumes[-1] < avg_vol * self.VOL_MULT:
            return None, 0, None, None
        if current > bb_upper and macd > sig:
            return "long", target_ror, "trend_following", {}
        if current < bb_lower and macd < sig:
            return "short", target_ror, "trend_following", {}
        return None, 0, None, None

    def _vb_signal(self, df, closes):
        if len(df) < 2:
            return None, 0, None, None
        prev = df.iloc[-2]; cur = df.iloc[-1]
        prev_range = float(prev["High"] - prev["Low"])
        prev_close = float(prev["Close"])
        if prev_close <= 0 or prev_range <= 0:
            return None, 0, None, None
        if prev_range / prev_close * 100 < self.VB_MIN_RANGE_PCT:
            return None, 0, None, None
        cur_open   = float(cur["Open"])
        long_trig  = cur_open + self.VB_K * prev_range
        short_trig = cur_open - self.VB_K * prev_range
        long_ok    = float(cur["High"]) >= long_trig  and long_trig  > cur_open
        short_ok   = float(cur["Low"])  <= short_trig and short_trig < cur_open
        if long_ok and short_ok:
            return None, 0, None, None
        import calendar
        candle_close_ts = calendar.timegm(df.index[-1].timetuple()) + 4 * 3600
        if long_ok:
            return "long", 0, "vb", {"candle_close_ts": candle_close_ts}
        if short_ok:
            return "short", 0, "vb", {"candle_close_ts": candle_close_ts}
        return None, 0, None, None

    def manage_exit(self, position: dict):
        symbol = position["symbol"]
        ror    = position["ror"]
        if self._state is None:
            entry_doc      = getEntryDetails(symbol)
            recovered_mode = entry_doc.get("mode", "trend_following") if entry_doc else "trend_following"
            if recovered_mode == "vb":
                candle_close_ts = entry_doc.get("candle_close_ts", 0)
                if not candle_close_ts:
                    enter_time      = entry_doc.get("enter_time", time.time())
                    candle_close_ts = (enter_time // (4 * 3600) + 1) * (4 * 3600)
                self._init_state(0, mode="vb",
                                 vb_meta={"candle_close_ts": candle_close_ts})
            else:
                self._init_state(0)

        mode = self._state.get("mode", "trend_following")
        if mode == "vb":
            now = time.time()
            candle_close_ts = self._state.get("candle_close_ts", 0)
            entry_time      = self._state.get("entry_time", 0)
            if now >= candle_close_ts or (entry_time and now - entry_time > 8 * 3600):
                self._close_position(position, f"VB다음봉청산(ROR:{ror:.1f}%)")
            else:
                print(f"  유지: {symbol} | VB | ROR:{ror:.1f}% | 청산까지:{(candle_close_ts-now)/60:.0f}분")
            return

        self._update_trailing(ror)
        should_close, reason, is_hard_stop = False, "", False
        if ror < self._state["stop_loss"]:
            should_close = True
            reason = f"트레일링스탑({ror:.1f}%)" if self._state["trailing_active"] else f"손절({ror:.1f}%)"
            is_hard_stop = not self._state["trailing_active"]
        if not should_close:
            should_close, reason = self._check_time()
        if should_close:
            if not is_hard_stop and self._should_hold(position["side"], symbol):
                print(f"  보류: {symbol} | 동일방향 시그널")
            else:
                self._close_position(position, reason)
        else:
            phase_names = {1: "초기", 2: "본전확보", 3: "트레일링", 4: "타이트"}
            print(f"  유지: {symbol} | ROR:{ror:.1f}% | {phase_names.get(self._state['phase'],'?')}")

    def _close_position(self, position: dict, reason: str):
        symbol     = position["symbol"]
        close_side = "SELL" if position["side"] == "long" else "BUY"
        success    = self.place_order(symbol, close_side, position["qty"])
        if success:
            try:
                total, _ = self.get_balance()
                data = dict(position)
                data["closeTime"] = int(datetime.now().timestamp())
                data["balance"]   = total
                addDataToMongoDB([data])
            except Exception:
                pass
            deleteEntryDetails(symbol)
            msg = f"🔴 [해외선물] {symbol} 청산 ({reason}) | ROR:{position['ror']:.1f}%"
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass
            self._state = None
        else:
            msg = f"❌ [해외선물] {symbol} 청산 주문 실패"
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass

    def _init_state(self, target_ror, mode="trend_following", vb_meta=None):
        if mode == "vb":
            if vb_meta and vb_meta.get("candle_close_ts"):
                candle_close_ts = vb_meta["candle_close_ts"]
            else:
                now = time.time()
                candle_close_ts = (now // (4 * 3600) + 1) * (4 * 3600)
            self._state = {
                "target_ror": 0, "stop_loss": 0,
                "entry_time": time.time(),
                "candle_close_ts": candle_close_ts,
                "highest_ror": 0, "trailing_active": False,
                "phase": 1, "mode": "vb",
            }
            return
        target = target_ror if target_ror > 5 else self.DEFAULT_TARGET_ROR
        stop   = -0.33 * target if target_ror > 5 else self.DEFAULT_STOP_LOSS
        self._state = {
            "target_ror": target, "stop_loss": stop,
            "entry_time": time.time(), "highest_ror": 0,
            "trailing_active": False, "phase": 1, "mode": "trend_following",
        }

    def _update_trailing(self, ror: float):
        s = self._state
        if ror > s["highest_ror"]:
            s["highest_ror"] = ror
        highest = s["highest_ror"]
        if highest < self.PHASE2_THRESHOLD:
            s["phase"] = 1
        elif highest < self.PHASE3_THRESHOLD:
            s["phase"] = 2
            s["stop_loss"] = max(s["stop_loss"], self.BREAKEVEN_STOP)
        elif highest < s["target_ror"]:
            s["phase"] = 3
            s["trailing_active"] = True
            s["stop_loss"] = max(s["stop_loss"], highest * self.TRAILING_RATIO)
        else:
            s["phase"] = 4
            s["trailing_active"] = True
            s["stop_loss"] = max(s["stop_loss"], highest * self.TIGHT_TRAILING_RATIO)

    def _check_time(self):
        elapsed = time.time() - self._state["entry_time"]
        ror     = self._state["highest_ror"]
        if elapsed > self.TIME_EXIT_SECONDS_1 and ror < self.TIME_EXIT_ROR_1:
            return True, f"시간초과(24h)"
        if elapsed > self.TIME_EXIT_SECONDS_2 and ror < self.TIME_EXIT_ROR_2:
            return True, f"시간초과(48h)"
        return False, ""

    def _should_hold(self, current_side: str, symbol: str) -> bool:
        try:
            sig, _, _, _ = self.check_entry_signal(symbol)
            return sig is not None and sig == current_side
        except Exception:
            return False

    def _rsi(self, closes):
        if len(closes) < self.RSI_PERIOD + 1:
            return 50
        s = pd.Series(closes); delta = s.diff()
        gain = delta.where(delta > 0, 0).rolling(self.RSI_PERIOD).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.RSI_PERIOD).mean()
        return float((100 - (100 / (1 + gain / loss))).iloc[-1])

    def _macd(self, closes):
        if len(closes) < 26:
            return None, None
        s = pd.Series(closes)
        macd = s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()
        return float(macd.iloc[-1]), float(macd.ewm(span=9, adjust=False).mean().iloc[-1])
```

- [ ] **Step 3: 커밋**

```bash
git add overseas_futures/ 
git commit -m "feat: add overseas futures base strategy"
```

---

## Task 6: 해외선물 스캐너 + 러너

**Files:**
- Create: `overseas_futures/scanner.py`
- Create: `overseas_futures/runner.py`

- [ ] **Step 1: overseas_futures/scanner.py 구현**

```python
# overseas_futures/scanner.py
import sys, os
sys.path.insert(0, os.path.abspath("."))
from tools.trendFilter import checkMarketRegime

# CME 주요 선물 화이트리스트 (KIS 종목코드 형식 확인 필요)
# KIS 해외선물 종목코드: 거래소코드+티커+만기월 형태
# ⚠️ 정확한 형식은 KIS API 포털 → 해외선물 종목 마스터 확인
OVERSEAS_WHITELIST = [
    "ES",   # S&P500 E-mini (CME)
    "NQ",   # NASDAQ E-mini (CME)
    "CL",   # WTI 원유 (NYMEX)
    "GC",   # 금 (COMEX)
    "SI",   # 은 (COMEX)
    "6E",   # 유로FX (CME)
    "6J",   # 엔FX (CME)
    "RTY",  # Russell 2000 E-mini (CME)
]

_TR_MASTER = "HHDFS76200000"  # 해외선물 종목 마스터 (확인 필요)


class OverseasFuturesScanner:
    def __init__(self, kis, strategy):
        self.kis      = kis
        self.strategy = strategy

    def get_active_symbols(self) -> list[str]:
        """
        KIS 해외선물 활성 종목 조회 → 화이트리스트 기준 필터링.
        KIS 종목코드가 티커 기반인지 전체코드인지 확인 후 조정 필요.
        """
        try:
            data = self.kis.get(
                "/uapi/overseas-futureoption/v1/quotations/inquire-futureoption-list",
                _TR_MASTER,
                {"FID_COND_MRKT_DIV_CODE": "Q", "FID_COND_SCR_DIV_CODE": "20",
                 "FID_OVRS_EXCG_CD": "CME"},
            )
            symbols = []
            for item in data.get("output", []):
                code = item.get("shtn_pdno", "")
                # 코드 앞부분이 화이트리스트 티커와 일치하는 것만
                for ticker in OVERSEAS_WHITELIST:
                    if code.startswith(ticker):
                        symbols.append(code)
                        break
            return symbols if symbols else OVERSEAS_WHITELIST  # 폴백: 티커 직접 사용
        except Exception as e:
            print(f"  [해외선물] 종목 목록 조회 오류: {e} — 화이트리스트 직접 사용")
            return OVERSEAS_WHITELIST

    def scan(self, current_symbols: list[str], limit: int) -> list[str]:
        if limit <= 0:
            return []
        active     = self.get_active_symbols()
        candidates = []
        for symbol in active:
            if symbol in current_symbols:
                continue
            df = self.strategy.get_candles(symbol, limit=100)
            if df is None or len(df) < 50:
                continue
            try:
                _, adx, _ = checkMarketRegime(df, adx_threshold=self.strategy.ADX_THRESHOLD)
                sig, _, _, _ = self.strategy.check_entry_signal(symbol)
                if sig is not None:
                    candidates.append((symbol, adx))
            except Exception:
                continue
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [sym for sym, _ in candidates[:limit]]
```

- [ ] **Step 2: overseas_futures/runner.py 구현**

```python
# overseas_futures/runner.py
import asyncio
import time
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.abspath("."))

from tools.telegram import send_message
from MongoDB_python.client import saveEntryDetails
from overseas_futures.base_strategy import BaseOverseasFuturesStrategy, OVERSEAS_CONTRACT_MULT
from overseas_futures.scanner import OverseasFuturesScanner


class OverseasFuturesRunner:
    MAX_POSITIONS = 5
    POSITION_FRAC = 0.1

    def __init__(self, kis):
        self.strategy = BaseOverseasFuturesStrategy(kis)
        self.scanner  = OverseasFuturesScanner(kis, self.strategy)

    def run(self):
        try:
            positions = self.strategy.get_positions()
            self._manage_exits(positions)

            if not self._is_market_open():
                return

            empty = self.MAX_POSITIONS - len(positions)
            if empty <= 0:
                return

            held       = [p["symbol"] for p in positions]
            candidates = self.scanner.scan(held, limit=empty)
            total, available = self.strategy.get_balance()

            for symbol in candidates:
                self._try_enter(symbol, total, available)

        except Exception as e:
            msg = f"[해외선물] runner 오류: {e}"
            print(f"  ❌ {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass

    def _manage_exits(self, positions: list[dict]):
        for pos in positions:
            try:
                self.strategy.manage_exit(pos)
            except Exception as e:
                print(f"  ❌ [해외선물] 청산 오류 {pos.get('symbol')}: {e}")

    def _try_enter(self, symbol: str, total: float, available: float):
        budget = total * self.POSITION_FRAC
        if available < budget:
            return

        sig, target_ror, mode, meta = self.strategy.check_entry_signal(symbol)
        if sig is None:
            return

        price = self.strategy._get_current_price(symbol)
        if price <= 0:
            return

        # 티커 앞부분으로 계약 승수 결정
        ticker = symbol[:2]
        mult   = OVERSEAS_CONTRACT_MULT.get(ticker, OVERSEAS_CONTRACT_MULT.get(symbol[:3], 50))
        qty    = self.strategy.calc_quantity(budget, price, mult)

        if qty <= 0:
            print(f"  [해외선물] {symbol} 예산 부족 (budget=${budget:,.0f}, price={price:.2f})")
            return

        order_side = "BUY" if sig == "long" else "SELL"
        success    = self.strategy.place_order(symbol, order_side, qty)

        if success:
            vb_meta = meta if mode == "vb" else None
            self.strategy._init_state(target_ror, mode=mode, vb_meta=vb_meta)
            candle_close_ts = self.strategy._state.get("candle_close_ts") if mode == "vb" else None
            saveEntryDetails(symbol, mode, sig, price, candle_close_ts)
            tag = "📈VB" if mode == "vb" else "✅TR"
            msg = f"{tag} [해외선물] {symbol} {sig.upper()} 진입 | qty:{qty} | target:{target_ror:.1f}%"
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass
        else:
            print(f"  ❌ [해외선물] {symbol} 주문 실패")

    def _is_market_open(self, now: datetime | None = None) -> bool:
        """
        CME 선물 장 시간 (KST 기준).
        월~금: 07:00 ~ 익일 06:00 (거의 24시간)
        주말: 일요일 07:00 개장 / 토요일 06:00 마감
        now: 테스트용 datetime 주입
        """
        if now is None:
            now = datetime.now()

        weekday = now.weekday()  # 0=월 ... 6=일
        h, m    = now.hour, now.minute
        hm      = h * 100 + m

        # 토요일: 00:00~06:00 (금요일 야간 이월) → 장중
        if weekday == 5:
            return hm < 600

        # 일요일: 07:00 이후 → 장중 (주간 개장)
        if weekday == 6:
            return hm >= 700

        # 평일: 06:00~07:00 만 마감 (일일 유지보수)
        return not (600 <= hm < 700)
```

- [ ] **Step 3: 장 시간 테스트 통과**

```bash
python -m pytest tests/test_market_hours.py -v
```
Expected: `6 passed`

- [ ] **Step 4: 커밋**

```bash
git add overseas_futures/scanner.py overseas_futures/runner.py
git commit -m "feat: add overseas futures scanner and runner"
```

---

## Task 7: main.py 통합

**Files:**
- Modify: `main.py`

- [ ] **Step 1: main.py 수정**

기존 코드는 변경하지 않는다. 아래 블록을 지정된 위치에 추가한다.

```python
# main.py 상단 import 블록에 추가 (기존 import 아래):
from kis.client import KISClient
from domestic_futures.runner import DomesticFuturesRunner
from overseas_futures.runner import OverseasFuturesRunner
from SecretVariables import KIS_APP_KEY, KIS_APP_SECRET
```

```python
# addVersionAndDate(COLLECTION, balance) 바로 아래에 추가:
kis_client      = KISClient(KIS_APP_KEY, KIS_APP_SECRET)
domestic_runner = DomesticFuturesRunner(kis_client)
overseas_runner = OverseasFuturesRunner(kis_client)
```

```python
# run_trading_bot() 내 updateHeartbeat() 바로 위에 추가:
domestic_runner.run()
overseas_runner.run()
```

최종 run_trading_bot() 함수:
```python
def run_trading_bot():
    while True:
        try:
            positions = getPositions(client)
            total_balance, available_balance = getBalance(client)

            for strategy in strategies:
                strategy.run(positions, total_balance, available_balance)

            domestic_runner.run()   # ← 추가
            overseas_runner.run()   # ← 추가

            updateHeartbeat()
            time.sleep(60)

        except Exception as e:
            print(f"❌ 오류: {e}")
            asyncio.run(send_message(f"Error: {e}"))
            time.sleep(60)
```

- [ ] **Step 2: import 오류 없는지 확인**

```bash
python -c "
from kis.client import KISClient
from domestic_futures.runner import DomesticFuturesRunner
from overseas_futures.runner import OverseasFuturesRunner
print('import OK')
"
```
Expected: `import OK`

- [ ] **Step 3: 전체 테스트 통과 확인**

```bash
python -m pytest tests/ -v
```
Expected: 전체 passed (KIS API 호출은 mock이므로 네트워크 불필요)

- [ ] **Step 4: 커밋**

```bash
git add main.py
git commit -m "feat: integrate KIS futures runners into main trading loop"
```

---

## 구현 후 수동 검증 절차

KIS API는 실제 계좌 연결 없이는 자동 테스트 불가. 아래 순서로 수동 확인한다.

1. **토큰 발급 확인**
```python
from SecretVariables import KIS_APP_KEY, KIS_APP_SECRET
from kis.client import KISClient
client = KISClient(KIS_APP_KEY, KIS_APP_SECRET)
client._issue_token()
print(client._token[:20])  # 토큰 앞 20자 출력
```

2. **국내선물 잔고 조회**
```python
from domestic_futures.base_strategy import BaseDomesticFuturesStrategy
s = BaseDomesticFuturesStrategy(client)
print(s.get_balance())
```

3. **국내선물 캔들 조회 (코스피200 선물 활성 종목코드 확인 후)**
```python
df = s.get_candles("101W09", limit=10)  # 종목코드는 KIS에서 확인
print(df)
```

4. **TR_ID 오류 시**: KIS API 포털(https://apiportal.koreainvestment.com) → 
   해당 메뉴 → TR_ID 확인 후 base_strategy.py의 `_TR_*` 상수 수정

5. **계좌번호(CANO) 추가**: KIS API 계좌번호를 `SecretVariables.py`에 `KIS_ACCOUNT_NO = "XXXXXXXX"`로 추가하고 각 base_strategy.py의 `get_balance()`, `get_positions()`, `place_order()` 호출 시 CANO 파라미터에 주입.
