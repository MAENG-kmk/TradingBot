# overseas_futures/base_strategy.py
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


# 해외선물 계약 승수 (USD 기준)
OVERSEAS_CONTRACT_MULT = {
    "ES":  50,        # S&P500 E-mini
    "NQ":  20,        # NASDAQ E-mini
    "CL":  1000,      # WTI 원유
    "GC":  100,       # 금
    "SI":  5000,      # 은
    "6E":  125000,    # 유로FX
    "6J":  12500000,  # 엔FX
    "RTY": 50,        # Russell 2000 E-mini
}


class BaseOverseasFuturesStrategy:
    """
    해외선물 베이스 전략.
    BaseDomesticFuturesStrategy와 전략 로직 동일,
    KIS API 경로/TR_ID/통화 단위만 다르다.
    """

    # ── 전략 파라미터 (국내선물과 동일) ────────────────────────────
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

    # ── KIS API TR_ID (해외선물) ──────────────────────────────────
    # ⚠️ KIS API 포털에서 확인 필요: https://apiportal.koreainvestment.com
    _TR_CANDLE     = "HHDFS76200100"   # 해외선물 분봉
    _TR_ORDER_BUY  = "JTTT1002U"       # 매수 (실전)
    _TR_ORDER_SELL = "JTTT1001U"       # 매도 (실전)
    _TR_BALANCE    = "CTOS5011R"       # 잔고조회

    def __init__(self, kis):
        self.kis     = kis
        self._states: dict[str, dict] = {}

    # ================================================================
    #  KIS API — 해외선물 전용
    # ================================================================

    def get_candles(self, symbol: str, limit: int = 300) -> pd.DataFrame | None:
        """KIS 해외선물 60분봉 → 4H 리샘플"""
        try:
            params = {
                "FID_COND_MRKT_DIV_CODE": "Q",
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
                {"CANO": KIS_ACCOUNT_NO, "ACNT_PRDT_CD": "03", "OVRS_EXCG_CD": "CME"},
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
                {"CANO": KIS_ACCOUNT_NO, "ACNT_PRDT_CD": "03", "OVRS_EXCG_CD": "CME"},
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
            print(f"  [해외선물] 포지션 조회 오류: {e}")
            return []

    def place_order(self, symbol: str, side: str, qty: int) -> bool:
        try:
            tr_id = self._TR_ORDER_BUY if side == "BUY" else self._TR_ORDER_SELL
            body  = {
                "CANO":            KIS_ACCOUNT_NO,
                "ACNT_PRDT_CD":    "03",
                "OVRS_EXCG_CD":    "CME",
                "PDNO":            symbol,
                "SLL_BUY_DVSN_CD": "02" if side == "BUY" else "01",
                "ORD_QTY":         str(qty),
                "OVRS_ORD_UNPR":   "0",
                "ORD_DVSN":        "01",
            }
            resp = self.kis.post(
                "/uapi/overseas-futureoption/v1/trading/order",
                tr_id,
                body,
            )
            return resp.get("rt_cd", "1") == "0"
        except Exception as e:
            print(f"  [해외선물] 주문 오류 {symbol} {side}: {e}")
            return False

    def calc_quantity(self, budget: float, price: float,
                      contract_mult: int | None = None) -> int:
        """계약 수 = floor(budget_usd / (price × contract_mult))"""
        mult = contract_mult if contract_mult is not None else 50
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
        prev       = df.iloc[-2]
        cur        = df.iloc[-1]
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
        if symbol not in self._states:
            entry_doc      = getEntryDetails(symbol)
            recovered_mode = entry_doc.get("mode", "trend_following") if entry_doc else "trend_following"
            if recovered_mode == "vb":
                candle_close_ts = entry_doc.get("candle_close_ts", 0)
                if not candle_close_ts:
                    enter_time      = entry_doc.get("enter_time", time.time())
                    candle_close_ts = (enter_time // (4 * 3600) + 1) * (4 * 3600)
                self._init_state(symbol, 0, mode="vb",
                                 vb_meta={"candle_close_ts": candle_close_ts})
                print(f"  [복구] {symbol} VB 모드 재시작 복구 (청산예정: {candle_close_ts})")
            else:
                self._init_state(symbol, 0)

        state = self._states[symbol]
        mode  = state.get("mode", "trend_following")
        if mode == "vb":
            now             = time.time()
            candle_close_ts = state.get("candle_close_ts", 0)
            entry_time      = state.get("entry_time", 0)
            if now >= candle_close_ts or (entry_time and now - entry_time > 8 * 3600):
                if entry_time and now - entry_time > 8 * 3600:
                    reason = f"VB안전장치강제청산(8H초과, ROR:{ror:.1f}%)"
                else:
                    reason = f"VB다음봉청산(ROR:{ror:.1f}%)"
                self._close_position(position, reason)
            else:
                print(f"  유지: {symbol} | VB | ROR:{ror:.1f}% | 청산까지:{(candle_close_ts-now)/60:.0f}분")
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
            if not is_hard_stop and self._should_hold(position["side"], symbol):
                print(f"  보류: {symbol} | {reason} → 동일방향 시그널 존재")
            else:
                self._close_position(position, reason)
        else:
            phase_names = {1: "초기", 2: "본전확보", 3: "트레일링", 4: "타이트"}
            print(f"  유지: {symbol} | ROR:{ror:.1f}% | 손절:{state['stop_loss']:.1f}% | {phase_names.get(state['phase'],'?')}")

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
            self._states.pop(symbol, None)
        else:
            msg = f"❌ [해외선물] {symbol} 청산 주문 실패 — 수동 확인 필요"
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
            "entry_time": time.time(), "highest_ror": 0,
            "trailing_active": False, "phase": 1, "mode": "trend_following",
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
