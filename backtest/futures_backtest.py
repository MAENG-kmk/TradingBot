"""
KIS 선물 백테스트 (국내 + 해외)

전략: 레짐필터 + BB 추세추종 + VB + 4단계 트레일링 스탑
      → domestic_futures/base_strategy.py, overseas_futures/base_strategy.py 와 동일

사용법:
  # 단일 종목
  python -m backtest.futures_backtest --instrument ES
  python -m backtest.futures_backtest --instrument KS200 --years 2

  # 그룹
  python -m backtest.futures_backtest --instrument overseas
  python -m backtest.futures_backtest --instrument domestic
  python -m backtest.futures_backtest --instrument all

데이터:
  해외선물: Yahoo Finance 1H 캔들 → 4H 리샘플 (yfinance 제한: 1h interval 최대 730일)
  국내선물: ^KS11 / ^KQ11 daily 캔들 (1H 미지원) → Sharpe 연율화 252 적용
  로컬 캐시: backtestDatas/futures/{symbol}_4h.csv / {symbol}_1d.csv
  --refresh 옵션으로 강제 재다운로드
"""
import argparse
import os
import sys
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

from tools.trendFilter import checkMarketRegime


# ─────────────────────────────────────────
# 종목 설정
# ─────────────────────────────────────────
FUTURES_CONFIGS = {
    # ── 해외선물 (USD, CME 그룹) ─────────────────
    "ES":   {"yf": "ES=F",  "mult": 50,    "currency": "USD", "name": "S&P500 E-mini"},
    "NQ":   {"yf": "NQ=F",  "mult": 20,    "currency": "USD", "name": "NASDAQ E-mini"},
    "RTY":  {"yf": "RTY=F", "mult": 50,    "currency": "USD", "name": "Russell 2000"},
    "CL":   {"yf": "CL=F",  "mult": 1000,  "currency": "USD", "name": "WTI Crude"},
    "GC":   {"yf": "GC=F",  "mult": 100,   "currency": "USD", "name": "Gold"},
    "SI":   {"yf": "SI=F",  "mult": 5000,  "currency": "USD", "name": "Silver"},
    # ── 국내선물 (KRW) — 종합지수 daily 대용 ──
    # Yahoo Finance 1H 국내 데이터 불안정 → daily ^KS11/^KQ11 사용
    # 가격 단위: 지수 포인트 (≈2500) → 계약가치 = pt × 승수
    "KS200":      {"yf": "^KS11",     "mult": 250_000, "currency": "KRW", "name": "코스피200선물"},
    "MINI_KS200": {"yf": "^KS11",     "mult": 50_000,  "currency": "KRW", "name": "미니코스피200선물"},
    "KQ150":      {"yf": "^KQ11",     "mult": 10_000,  "currency": "KRW", "name": "코스닥150선물"},
}

INITIAL_CAPITAL = {
    "USD": 1_000_000.0,
    "KRW": 1_000_000_000.0,
}

# ─────────────────────────────────────────
# 전략 파라미터 (라이브 봇과 동일)
# ─────────────────────────────────────────
TR_BB_PERIOD     = 20
TR_BB_STD        = 2.0
RSI_PERIOD       = 14
RSI_OVERBUY      = 80
RSI_OVERSELL     = 20
ADX_THRESHOLD    = 20
VOL_PERIOD       = 20
VOL_MULT         = 1.5

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

VB_K               = 0.3
VB_MIN_RANGE_PCT   = 0.3
MR_SLOPE_THRESHOLD = 0.05

POSITION_FRAC  = 0.1     # 총잔고의 10%
COMMISSION_PCT = 0.0001  # 선물 수수료 ≈ 0.01%
SLIPPAGE_PCT   = 0.0002  # 슬리피지 ≈ 0.02%
LEVERAGE       = 10      # 선물 마진 배율 (국내선물 ≈ 6~10배, 해외선물 ≈ 5~15배)


# ─────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────
def load_data(instrument: str, years: int = 2,
              refresh: bool = False) -> tuple[pd.DataFrame | None, str]:
    """캔들 다운로드. 1h 가능하면 4H 리샘플, 아니면 daily로 폴백.

    Returns: (df, interval) — interval은 '4h' 또는 '1d'
    """
    cfg       = FUTURES_CONFIGS[instrument]
    cache_dir = "backtestDatas/futures"
    os.makedirs(cache_dir, exist_ok=True)
    cache_4h = f"{cache_dir}/{instrument.lower()}_4h.csv"
    cache_1d = f"{cache_dir}/{instrument.lower()}_1d.csv"

    if not refresh:
        if os.path.exists(cache_4h):
            df = pd.read_csv(cache_4h, index_col=0, parse_dates=True)
            if len(df) >= 100:
                return df, "4h"
        if os.path.exists(cache_1d):
            df = pd.read_csv(cache_1d, index_col=0, parse_dates=True)
            if len(df) >= 100:
                return df, "1d"

    if yf is None:
        print(f"  [오류] yfinance 미설치. pip install yfinance")
        return None, ""

    end = pd.Timestamp.now()

    # 1차 시도: 1h interval (최대 730일) → 4H 리샘플
    start_1h = end - pd.DateOffset(days=min(729, years * 365))
    print(f"  [{instrument}] {cfg['yf']} 1h 다운로드 시도 ({start_1h.date()} ~ {end.date()})...")
    try:
        df = yf.download(cfg["yf"], start=start_1h, end=end,
                         interval="1h", progress=False, auto_adjust=False)
        if df is not None and not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            df_4h = df[["Open", "High", "Low", "Close", "Volume"]].resample("4h").agg({
                "Open": "first", "High": "max",
                "Low": "min", "Close": "last", "Volume": "sum",
            }).dropna()
            if len(df_4h) >= 100:
                df_4h.to_csv(cache_4h)
                print(f"  [{instrument}] 4H 저장: {cache_4h}  ({len(df_4h)}봉)")
                return df_4h, "4h"
    except Exception as e:
        print(f"  [{instrument}] 1h 실패: {e}")

    # 2차 시도: daily (장기간 가능)
    start_1d = end - pd.DateOffset(years=max(years, 5))
    print(f"  [{instrument}] {cfg['yf']} daily 다운로드 시도 ({start_1d.date()} ~ {end.date()})...")
    try:
        df = yf.download(cfg["yf"], start=start_1d, end=end,
                         interval="1d", progress=False, auto_adjust=False)
    except Exception as e:
        print(f"  [오류] daily 다운로드 실패: {e}")
        return None, ""

    if df is None or df.empty:
        print(f"  [오류] {cfg['yf']} 데이터 없음")
        return None, ""

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    df_1d = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if len(df_1d) < 100:
        print(f"  [오류] daily 봉 부족 ({len(df_1d)}개)")
        return None, ""

    df_1d.to_csv(cache_1d)
    print(f"  [{instrument}] daily 저장: {cache_1d}  ({len(df_1d)}봉)")
    return df_1d, "1d"


# ─────────────────────────────────────────
# 지표
# ─────────────────────────────────────────
def _rsi(closes: np.ndarray) -> float:
    if len(closes) < RSI_PERIOD + 1:
        return 50.0
    s     = pd.Series(closes)
    delta = s.diff()
    gain  = delta.where(delta > 0, 0).rolling(RSI_PERIOD).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(RSI_PERIOD).mean()
    rs    = gain / loss
    return float((100 - (100 / (1 + rs))).iloc[-1])


def _macd(closes: np.ndarray):
    if len(closes) < 26:
        return None, None
    s      = pd.Series(closes)
    ema12  = s.ewm(span=12, adjust=False).mean()
    ema26  = s.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return float(macd.iloc[-1]), float(signal.iloc[-1])


def _atr(df: pd.DataFrame, period: int = 5) -> float:
    rng = (df["High"] - df["Low"]).iloc[-period:]
    return float(rng.mean())


# ─────────────────────────────────────────
# 진입 신호 (라이브 봇 로직과 동일)
# ─────────────────────────────────────────
def _trend_following_signal(window: pd.DataFrame):
    closes = window["Close"].values.astype(float)
    if len(closes) < TR_BB_PERIOD:
        return None, 0

    bb_closes = closes[-TR_BB_PERIOD:]
    bb_mid    = float(np.mean(bb_closes))
    bb_std    = float(np.std(bb_closes))
    bb_upper  = bb_mid + TR_BB_STD * bb_std
    bb_lower  = bb_mid - TR_BB_STD * bb_std

    cur          = closes[-1]
    rsi_val      = _rsi(closes)
    macd, signal = _macd(closes)
    if macd is None:
        return None, 0
    if rsi_val >= RSI_OVERBUY or rsi_val <= RSI_OVERSELL:
        return None, 0

    atr        = _atr(window)
    target_ror = abs(atr / cur) * 100 if cur > 0 else 0

    volumes = window["Volume"].values.astype(float)
    avg_vol = float(np.mean(volumes[-VOL_PERIOD:]))
    cur_vol = volumes[-1]
    if avg_vol <= 0 or cur_vol < avg_vol * VOL_MULT:
        return None, 0

    if cur > bb_upper and macd > signal:
        return "long", target_ror
    if cur < bb_lower and macd < signal:
        return "short", target_ror
    return None, 0


def _vb_signal(window: pd.DataFrame):
    """VB 신호. 진입가는 트리거 가격(돌파 시점)."""
    if len(window) < 2:
        return None

    prev       = window.iloc[-2]
    cur        = window.iloc[-1]
    prev_range = float(prev["High"] - prev["Low"])
    prev_close = float(prev["Close"])
    if prev_close <= 0 or prev_range <= 0:
        return None
    if prev_range / prev_close * 100 < VB_MIN_RANGE_PCT:
        return None

    cur_open   = float(cur["Open"])
    long_trig  = cur_open + VB_K * prev_range
    short_trig = cur_open - VB_K * prev_range

    long_ok  = float(cur["High"]) >= long_trig  and long_trig  > cur_open
    short_ok = float(cur["Low"])  <= short_trig and short_trig < cur_open

    if long_ok and short_ok:
        return None
    if long_ok:
        return ("long",  long_trig)
    if short_ok:
        return ("short", short_trig)
    return None


# ─────────────────────────────────────────
# 4단계 트레일링 스탑
# ─────────────────────────────────────────
def _update_trailing(state: dict, ror: float):
    if ror > state["highest_ror"]:
        state["highest_ror"] = ror
    h = state["highest_ror"]
    if h < PHASE2_THRESHOLD:
        state["phase"] = 1
    elif h < PHASE3_THRESHOLD:
        state["phase"] = 2
        state["stop_loss"] = max(state["stop_loss"], BREAKEVEN_STOP)
    elif h < state["target_ror"]:
        state["phase"] = 3
        state["trailing_active"] = True
        state["stop_loss"] = max(state["stop_loss"], h * TRAILING_RATIO)
    else:
        state["phase"] = 4
        state["trailing_active"] = True
        state["stop_loss"] = max(state["stop_loss"], h * TIGHT_TRAILING_RATIO)


def _make_state(target_ror: float) -> dict:
    target = target_ror if target_ror > 5 else DEFAULT_TARGET_ROR
    stop   = -0.33 * target if target_ror > 5 else DEFAULT_STOP_LOSS
    return {
        "target_ror":      target,
        "stop_loss":       stop,
        "highest_ror":     0.0,
        "trailing_active": False,
        "phase":           1,
    }


# ─────────────────────────────────────────
# 백테스트 메인
# ─────────────────────────────────────────
def run_backtest(instrument: str, years: int = 2,
                 refresh: bool = False, quiet: bool = False) -> dict | None:
    cfg            = FUTURES_CONFIGS[instrument]
    df, interval   = load_data(instrument, years=years, refresh=refresh)
    if df is None or len(df) < 100:
        return None

    initial_cash = INITIAL_CAPITAL[cfg["currency"]]
    cash         = initial_cash
    fee_pct      = COMMISSION_PCT + SLIPPAGE_PCT
    mult         = cfg["mult"]

    pos: dict | None = None
    trades = []
    equity = []

    bar_seconds = 24 * 3600 if interval == "1d" else 4 * 3600

    for i in range(50, len(df)):
        ts        = df.index[i]
        bar       = df.iloc[i]
        cur_price = float(bar["Close"])

        # ── 포지션 관리 ──────────────────────────
        if pos is not None:
            if pos["side"] == "long":
                ror = (cur_price - pos["entry_price"]) / pos["entry_price"] * 100
            else:
                ror = (pos["entry_price"] - cur_price) / pos["entry_price"] * 100

            should_close = False
            reason       = ""
            exit_price   = cur_price

            if pos["mode"] == "vb":
                # VB: 1봉 보유 후 다음 봉 청산
                if i - pos["entry_idx"] >= 1:
                    should_close = True
                    reason       = "vb_next_bar"
                    exit_price   = cur_price
                # 안전장치: 2봉 초과 시 강제 청산
                elif (ts - pos["entry_time"]).total_seconds() > 2 * bar_seconds:
                    should_close = True
                    reason       = "vb_safety"
                    exit_price   = cur_price
            else:
                # trend_following: 4단계 트레일링
                _update_trailing(pos["state"], ror)

                if ror < pos["state"]["stop_loss"]:
                    should_close = True
                    reason       = ("trailing" if pos["state"]["trailing_active"]
                                    else "stop_loss")
                    # 손절가/트레일링가에서 체결 가정
                    sl = pos["state"]["stop_loss"]
                    if pos["side"] == "long":
                        exit_price = pos["entry_price"] * (1 + sl / 100)
                    else:
                        exit_price = pos["entry_price"] * (1 - sl / 100)
                else:
                    elapsed = (ts - pos["entry_time"]).total_seconds()
                    h_ror   = pos["state"]["highest_ror"]
                    if elapsed > TIME_EXIT_SECONDS_1 and h_ror < TIME_EXIT_ROR_1:
                        should_close = True
                        reason       = "time_24h"
                        exit_price   = cur_price
                    elif elapsed > TIME_EXIT_SECONDS_2 and h_ror < TIME_EXIT_ROR_2:
                        should_close = True
                        reason       = "time_48h"
                        exit_price   = cur_price

            if should_close:
                # 슬리피지 + 수수료 (편도)
                if pos["side"] == "long":
                    exit_price *= (1 - fee_pct)
                    pnl_pts = exit_price - pos["entry_price"]
                else:
                    exit_price *= (1 + fee_pct)
                    pnl_pts = pos["entry_price"] - exit_price

                profit    = pnl_pts * pos["qty"] * mult
                cash     += profit
                ror_final = (pnl_pts / pos["entry_price"]) * 100

                trades.append({
                    "entry_time":  pos["entry_time"],
                    "exit_time":   ts,
                    "side":        pos["side"],
                    "mode":        pos["mode"],
                    "qty":         pos["qty"],
                    "entry_price": pos["entry_price"],
                    "exit_price":  exit_price,
                    "ror":         ror_final,
                    "profit":      profit,
                    "reason":      reason,
                })
                pos = None

        # ── 진입 ──────────────────────────────────
        if pos is None:
            window = df.iloc[max(0, i - 299): i + 1]

            try:
                regime, _, _ = checkMarketRegime(
                    window, adx_threshold=ADX_THRESHOLD,
                    slope_threshold=MR_SLOPE_THRESHOLD,
                )
            except Exception:
                regime = "ranging"

            sig          = None
            mode         = None
            target_ror   = 0.0
            entry_price  = cur_price

            if regime in ("uptrend", "downtrend"):
                tf_sig = _trend_following_signal(window)
                if tf_sig[0] is not None:
                    sig, target_ror = tf_sig
                    mode = "trend_following"
                    entry_price = cur_price
            else:
                vb_res = _vb_signal(window)
                if vb_res is not None:
                    sig, trig = vb_res
                    mode = "vb"
                    entry_price = trig

            if sig is not None and entry_price > 0:
                # 슬리피지 + 수수료 (편도)
                if sig == "long":
                    entry_price *= (1 + fee_pct)
                else:
                    entry_price *= (1 - fee_pct)

                budget         = cash * POSITION_FRAC * LEVERAGE
                contract_value = entry_price * mult
                qty            = int(budget / contract_value) if contract_value > 0 else 0

                if qty > 0:
                    pos = {
                        "side":        sig,
                        "qty":         qty,
                        "entry_price": entry_price,
                        "entry_time":  ts,
                        "entry_idx":   i,
                        "mode":        mode,
                        "state":       _make_state(target_ror) if mode == "trend_following"
                                       else None,
                    }

        # ── 자산 기록 ─────────────────────────────
        if pos is not None:
            if pos["side"] == "long":
                unrealized = (cur_price - pos["entry_price"]) * pos["qty"] * mult
            else:
                unrealized = (pos["entry_price"] - cur_price) * pos["qty"] * mult
            equity.append(cash + unrealized)
        else:
            equity.append(cash)

    # 미청산 포지션 마감
    if pos is not None and len(df) > 0:
        last_price = float(df["Close"].iloc[-1])
        if pos["side"] == "long":
            exit_price = last_price * (1 - fee_pct)
            pnl_pts    = exit_price - pos["entry_price"]
        else:
            exit_price = last_price * (1 + fee_pct)
            pnl_pts    = pos["entry_price"] - exit_price
        profit = pnl_pts * pos["qty"] * mult
        cash  += profit
        trades.append({
            "entry_time":  pos["entry_time"],
            "exit_time":   df.index[-1],
            "side":        pos["side"],
            "mode":        pos["mode"],
            "qty":         pos["qty"],
            "entry_price": pos["entry_price"],
            "exit_price":  exit_price,
            "ror":         (pnl_pts / pos["entry_price"]) * 100,
            "profit":      profit,
            "reason":      "force_close",
        })
        if equity:
            equity[-1] = cash

    # ── 성과 집계 ────────────────────────────
    if not trades:
        if not quiet:
            print(f"\n  [{instrument}] 거래 없음 ({len(df)}봉)")
        return None

    df_t = pd.DataFrame(trades)
    eq   = np.array(equity, dtype=float)

    total      = len(df_t)
    won        = (df_t["ror"] > 0).sum()
    lost       = (df_t["ror"] <= 0).sum()
    win_rate   = won / total * 100
    final      = eq[-1]
    ror_total  = (final - initial_cash) / initial_cash * 100

    avg_win  = df_t.loc[df_t["ror"] > 0,  "ror"].mean() if won  > 0 else 0
    avg_loss = df_t.loc[df_t["ror"] <= 0, "ror"].mean() if lost > 0 else 0
    pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    tr_trades = (df_t["mode"] == "trend_following").sum()
    vb_trades = (df_t["mode"] == "vb").sum()

    returns = pd.Series(eq).pct_change().dropna()
    bars_per_year = 252 if interval == "1d" else 2190  # 4H: 365×6, 1D: 252
    sharpe  = (returns.mean() / returns.std() * np.sqrt(bars_per_year)
               if len(returns) > 0 and returns.std() > 0 else 0)

    running_max = np.maximum.accumulate(eq)
    dd          = (eq - running_max) / running_max * 100
    mdd         = float(dd.min()) if len(dd) > 0 else 0

    if not quiet:
        sym = "$" if cfg["currency"] == "USD" else "₩"
        print(f"\n{'='*60}")
        print(f"  {instrument:>10}  {cfg['name']}")
        print(f"  데이터: {df.index[0].date()} ~ {df.index[-1].date()}  ({len(df):,}봉)")
        print(f"  계약승수: {sym}{mult:,}/pt   초기자본: {sym}{initial_cash:,.0f}")
        print(f"{'='*60}")
        print(f"  총 거래:   {total}회  (TR {tr_trades} / VB {vb_trades})")
        print(f"             롱 {(df_t['side']=='long').sum()} / 숏 {(df_t['side']=='short').sum()}")
        print(f"  승률:      {win_rate:.1f}%  (수익 {won} / 손실 {lost})")
        print(f"  P/L 비:    {pl_ratio:.2f}  (avg win {avg_win:+.2f}% / loss {avg_loss:+.2f}%)")
        print(f"\n  ROR:       {ror_total:+.2f}%")
        print(f"  Sharpe:    {sharpe:.2f}")
        print(f"  MDD:       {mdd:.2f}%")
        print(f"  최종자본:  {sym}{final:,.0f}")

        eq_index  = df.index[50:50 + len(eq)]
        eq_series = pd.Series(eq, index=eq_index)
        prev      = initial_cash
        print(f"\n  연도별 수익:")
        for year, grp in eq_series.groupby(eq_series.index.year):
            end_val = grp.iloc[-1]
            yr      = (end_val - prev) / prev * 100
            sign    = "+" if yr >= 0 else ""
            bar     = "█" * min(int(abs(yr) / 5), 40)
            print(f"    {year}: {sign}{yr:6.1f}%  {bar}")
            prev = end_val

    return {
        "instrument": instrument,
        "currency":   cfg["currency"],
        "ror":        ror_total,
        "sharpe":     sharpe,
        "mdd":        mdd,
        "trades":     total,
        "tr_trades":  tr_trades,
        "vb_trades":  vb_trades,
        "win_rate":   win_rate,
        "final":      final,
    }


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────
def _resolve_targets(instrument: str) -> list[str]:
    if instrument == "all":
        return list(FUTURES_CONFIGS.keys())
    if instrument == "overseas":
        return [k for k, v in FUTURES_CONFIGS.items() if v["currency"] == "USD"]
    if instrument == "domestic":
        return [k for k, v in FUTURES_CONFIGS.items() if v["currency"] == "KRW"]
    return [instrument]


def _print_summary(results: list[dict]):
    if len(results) <= 1:
        return
    print(f"\n{'='*70}")
    print(f"  요약 ({len(results)}개 종목)")
    print(f"{'='*70}")
    print(f"  {'종목':<12} {'통화':<5} {'ROR':>10}  {'Sharpe':>7}  {'MDD':>7}  {'거래':>5}  {'승률':>6}")
    print(f"  {'─'*68}")
    for r in sorted(results, key=lambda x: x["sharpe"], reverse=True):
        print(f"  {r['instrument']:<12} {r['currency']:<5} "
              f"{r['ror']:>+9.1f}%  {r['sharpe']:>7.2f}  "
              f"{r['mdd']:>6.1f}%  {r['trades']:>5}  {r['win_rate']:>5.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KIS 선물 백테스트")
    choices = list(FUTURES_CONFIGS.keys()) + ["all", "overseas", "domestic"]
    parser.add_argument("--instrument", default="ES", choices=choices,
                        help="종목 코드, 또는 all/overseas/domestic")
    parser.add_argument("--years",   type=int, default=2,
                        help="다운로드 기간 (년, 최대 2년)")
    parser.add_argument("--refresh", action="store_true",
                        help="캐시 무시하고 재다운로드")
    args = parser.parse_args()

    targets = _resolve_targets(args.instrument)
    results = []
    for inst in targets:
        r = run_backtest(inst, years=args.years, refresh=args.refresh)
        if r:
            results.append(r)
    _print_summary(results)
