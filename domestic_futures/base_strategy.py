import math
import time
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime

from tools.trendFilter import checkMarketRegime
from tools.getAtr import getATR
from tools.telegram import send_message
from MongoDB_python.client import (
    addDataToMongoDB, saveEntryDetails,
    getEntryDetails, deleteEntryDetails,
)
from SecretVariables import KIS_ACCOUNT_NO


class BaseDomesticFuturesStrategy:
    """
    국내선물 베이스 전략.
    coins/base_strategy.py와 동일한 전략 로직(레짐필터+추세추종+VB+4단계 트레일링).
    KIS API 호출 부분만 다르다.
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
    VB_K             = 0.3
    VB_MIN_RANGE_PCT = 0.3
    MR_SLOPE_THRESHOLD = 0.05

    # ── 종목별 오버라이드 ────────────────────────────────────────
    SYMBOL            = ""
    CONTRACT_MULT     = 250_000    # 계약 승수 (원)
    CURRENCY          = "KRW"

    # ── KIS API TR_ID ─────────────────────────────────────────────
    # ⚠️ 반드시 KIS API 포털에서 확인: https://apiportal.koreainvestment.com
    _TR_CANDLE     = "FHMIF10010200"
    _TR_ORDER_BUY  = "JTCE1002U"
    _TR_ORDER_SELL = "JTCE1001U"
    _TR_BALANCE    = "CTFO6118R"

    def __init__(self, kis):
        self.kis     = kis
        self._states: dict[str, dict] = {}

    # ================================================================
    #  KIS API
    # ================================================================

    def get_candles(self, symbol: str, limit: int = 300) -> pd.DataFrame | None:
        """KIS 국내선물 60분봉 조회 → 4H 캔들로 리샘플"""
        try:
            params = {
                "FID_COND_MRKT_DIV_CODE": "F",
                "FID_INPUT_ISCD":         symbol,
                "FID_INPUT_HOUR_1":       "060000",
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
                {"CANO": KIS_ACCOUNT_NO, "ACNT_PRDT_CD": "03"},
            )
            output    = data.get("output", {})
            total     = float(output.get("tot_asst_evlu_amt", 0))
            available = float(output.get("ord_psbl_cash", 0))
            return total, available
        except Exception as e:
            print(f"  [국내선물] 잔고 조회 오류: {e}")
            return 0.0, 0.0

    def get_positions(self) -> list[dict]:
        """보유 포지션 목록 반환"""
        try:
            data = self.kis.get(
                "/uapi/domestic-futureoption/v1/trading/inquire-balance",
                self._TR_BALANCE,
                {"CANO": KIS_ACCOUNT_NO, "ACNT_PRDT_CD": "03"},
            )
            positions = []
            for item in data.get("output1", []):
                qty = int(item.get("hldg_qty", 0))
                if qty == 0:
                    continue
                side = "long" if int(item.get("seln_buy_dvsn_cd", "2")) == 2 else "short"
                entry_price   = float(item.get("pchs_avg_pric", 0))
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
        """side: 'BUY' | 'SELL'"""
        try:
            tr_id = self._TR_ORDER_BUY if side == "BUY" else self._TR_ORDER_SELL
            body  = {
                "CANO":          KIS_ACCOUNT_NO,
                "ACNT_PRDT_CD":  "03",
                "SLL_BUY_DVSN_CD": "02" if side == "BUY" else "01",
                "SHTN_PDNO":     symbol,
                "ORD_QTY":       str(qty),
                "UNIT_PRICE":    "0",
                "NMPR_TYPE_CD":  "",
                "KIS_PRVS_RSQN_UNIQ_NO": "",
                "CTAC_TLNO":     "",
                "FUOP_ITEM_DVSN_CD": "",
                "ORD_DVSN":      "01",
            }
            resp  = self.kis.post(
                "/uapi/domestic-futureoption/v1/trading/order",
                tr_id,
                body,
            )
            return resp.get("rt_cd", "1") == "0"
        except Exception as e:
            print(f"  [국내선물] 주문 오류 {symbol} {side}: {e}")
            return False

    def calc_quantity(self, budget: float, price: float,
                      contract_mult: int | None = None) -> int:
        """계약 수 = floor(budget / (price × contract_mult))"""
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
        """Returns: ('long'|'short', target_ror, mode, meta) | (None, 0, None, None)"""
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

        volumes = df["Volume"].values.astype(float)
        avg_vol = float(np.mean(volumes[-self.VOL_PERIOD:]))
        cur_vol = volumes[-1]
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

        cur_open   = float(cur["Open"])
        cur_high   = float(cur["High"])
        cur_low    = float(cur["Low"])
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

        if symbol not in self._states:
            entry_doc      = getEntryDetails(symbol)
            recovered_mode = entry_doc.get("mode", "trend_following") if entry_doc else "trend_following"
            if recovered_mode == "vb":
                candle_close_ts = entry_doc.get("candle_close_ts", 0)
                if not candle_close_ts:
                    enter_time      = entry_doc.get("enter_time", time.time())
                    candle_sec      = 4 * 3600
                    candle_close_ts = (enter_time // candle_sec + 1) * candle_sec
                self._init_state(symbol, 0, mode="vb",
                                 vb_meta={"candle_close_ts": candle_close_ts})
                print(f"  [복구] {symbol} VB 모드 재시작 복구 (청산예정: {candle_close_ts})")
            else:
                self._init_state(symbol, 0)

        state = self._states[symbol]
        mode  = state.get("mode", "trend_following")

        if mode == "vb":
            candle_close_ts = state.get("candle_close_ts", 0)
            entry_time      = state.get("entry_time", 0)
            now             = time.time()
            vb_timeout = now >= candle_close_ts or (entry_time and now - entry_time > 8 * 3600)
            if vb_timeout:
                if entry_time and now - entry_time > 8 * 3600:
                    reason = f"VB안전장치강제청산(8H초과, ROR:{ror:.1f}%)"
                else:
                    reason = f"VB다음봉청산(ROR:{ror:.1f}%)"
                self._close_position(position, reason)
            else:
                remaining_min = (candle_close_ts - now) / 60
                print(f"  유지: {symbol} | VB | ROR:{ror:.1f}% | 청산까지:{remaining_min:.0f}분")
            return

        self._update_trailing(symbol, ror)
        state = self._states[symbol]
        should_close, reason, is_hard_stop = False, "", False

        if ror < state["stop_loss"]:
            should_close = True
            if state["trailing_active"]:
                reason = f"트레일링스탑(최고:{state['highest_ror']:.1f}%→{ror:.1f}%)"
            else:
                reason = f"손절({ror:.1f}%)"
                is_hard_stop = True

        if not should_close:
            should_close, reason = self._check_time(symbol)

        if should_close:
            if not is_hard_stop and self._should_hold(position["side"], position["symbol"]):
                print(f"  보류: {symbol} | {reason} → 동일방향 시그널 존재")
            else:
                self._close_position(position, reason)
        else:
            phase_names = {1: "초기", 2: "본전확보", 3: "트레일링", 4: "타이트"}
            phase = phase_names.get(state["phase"], "?")
            print(f"  유지: {symbol} | ROR:{ror:.1f}% | 손절:{state['stop_loss']:.1f}% | {phase}")

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
            msg = (f"🔴 [국내선물] {symbol} 청산 ({reason}) "
                   f"| ROR:{position['ror']:.1f}%")
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass
            self._states.pop(symbol, None)
        else:
            msg = f"❌ [국내선물] {symbol} 청산 주문 실패 — 수동 확인 필요"
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass

    def _init_state(self, symbol: str, target_ror, mode="trend_following", vb_meta=None):
        if mode == "vb":
            if vb_meta and vb_meta.get("candle_close_ts"):
                candle_close_ts = vb_meta["candle_close_ts"]
            else:
                now = time.time()
                candle_close_ts = (now // (4 * 3600) + 1) * (4 * 3600)
            self._states[symbol] = {
                "target_ror": 0, "stop_loss": 0,
                "entry_time": time.time(),
                "candle_close_ts": candle_close_ts,
                "highest_ror": 0, "trailing_active": False,
                "phase": 1, "mode": "vb",
            }
            return

        target = target_ror if target_ror > 5 else self.DEFAULT_TARGET_ROR
        stop   = -0.33 * target if target_ror > 5 else self.DEFAULT_STOP_LOSS
        self._states[symbol] = {
            "target_ror": target, "stop_loss": stop,
            "entry_time": time.time(),
            "highest_ror": 0, "trailing_active": False,
            "phase": 1, "mode": "trend_following",
        }

    def _update_trailing(self, symbol: str, ror: float):
        s = self._states[symbol]
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

    def _check_time(self, symbol: str):
        elapsed = time.time() - self._states[symbol]["entry_time"]
        ror     = self._states[symbol]["highest_ror"]
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
