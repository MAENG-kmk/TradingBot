"""
BTC SDE 전략 백테스트 — XGBoost 레짐 필터 효과 비교
coins/btc/strategy.py 로직 그대로 재현 (pandas 기반)

비교:
  필터없음 : XGB 조건 무관, GBM 확률만으로 진입
  XGB필터  : prob >= 0.55 인 경우에만 진입 허용

진입:
  최근 50봉 GBM(μ,σ) 추정 →
  P(+4% 도달 > -2% 도달) > 0.58 → 롱
  P(-4% 도달 > +2% 도달) > 0.58 → 숏

청산 (우선순위):
  1. 하드스탑  : 현재가 ≤ stop_price (intrabar low/high 체크)
  2. 목표달성  : 현재가 ≥ target_price (intrabar)
  3. 확률역전  : P_continue < 0.35 (봉 종가 기준)
  4. 시간초과  : 보유 48봉 초과

사용법:
  python backtest_sde_xgb.py           # 레버리지 스윕 (1x~5x)
  python backtest_sde_xgb.py --plot
  python backtest_sde_xgb.py --chart-save
"""

import argparse, os, sys
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd

from tools.sdeTools import estimate_gbm, sde_entry_probs, barrier_prob
from tools.regime_filter import RegimeFilter, build_features, FEATURE_NAMES

# ── 파라미터 (coins/btc/strategy.py 와 동일) ─────────────────────
COMMISSION    = 0.0005
INITIAL       = 100_000.0
POSITION_PCT  = 0.10

SDE_EST_WINDOW = 50
SDE_TARGET_ROR = 0.04
SDE_STOP_ROR   = 0.02
SDE_ENTRY_PROB = 0.58
SDE_EXIT_PROB  = 0.35
SDE_MAX_BARS   = 48
XGB_THRESHOLD  = 0.55

DATA_PATH = 'backtestDatas/btcusdt_4h.csv'
SYMBOL    = 'BTCUSDT'


# ── 데이터 로드 ──────────────────────────────────────────────────
def load_ohlcv(path):
    df = pd.read_csv(path, index_col='Date', parse_dates=True)
    df.index = df.index.tz_localize(None)
    return df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float).sort_index()


# ── 통계 ─────────────────────────────────────────────────────────
def _stats(trades: list, equity: list, final_cash: float):
    if not trades:
        return None
    td  = pd.DataFrame(trades)
    eq  = pd.Series(equity)
    tot = len(td)
    won = (td['pnl'] > 0).sum()
    lst = tot - won
    ap  = td.loc[td['pnl'] > 0, 'pnl'].mean() if won > 0 else 0
    al  = td.loc[td['pnl'] <= 0, 'pnl'].mean() if lst > 0 else 0
    pl  = abs(ap / al) if al != 0 else 0
    ror = (final_cash - INITIAL) / INITIAL * 100
    rm  = eq.cummax()
    mdd = ((eq - rm) / rm * 100).min()
    ret = eq.pct_change().dropna()
    sh  = ret.mean() / ret.std() * np.sqrt(365 * 6) if ret.std() > 0 else 0
    return dict(total=tot, won=won, lost=lst, win_rate=won/tot*100,
                pl_ratio=pl, ror=ror, sharpe=sh, mdd=mdd,
                avg_win=ap, avg_loss=al, final=final_cash, trades=td)


# ── 시뮬레이션 ───────────────────────────────────────────────────
def simulate(df: pd.DataFrame, leverage: int = 5, use_xgb: bool = False):
    """
    단일 조건 시뮬레이션

    leverage : 레버리지 배수 (P&L 증폭)
    use_xgb  : XGB 레짐 필터 적용 여부

    반환: (stats | None, equity_series)
    """
    feat_df = build_features(df)

    rf = None
    if use_xgb:
        try:
            rf = RegimeFilter.load(f'models/regime_{SYMBOL}.pkl')
        except Exception as e:
            print(f"  XGB 모델 로드 실패 ({e}) → 필터 없이 실행")

    closes = df['Close'].values.astype(float)
    warmup = max(SDE_EST_WINDOW + 1, 300)   # XGB 피처도 300봉 필요

    cash   = INITIAL
    equity = []
    trades = []
    pos    = None

    for i in range(warmup, len(df)):
        bar_high  = df['High'].iloc[i]
        bar_low   = df['Low'].iloc[i]
        bar_close = df['Close'].iloc[i]

        # ── 청산 체크 ──────────────────────────────────────────────
        if pos is not None:
            bars_held  = i - pos['entry_bar']
            entry      = pos['entry_price']
            side       = pos['side']
            sde_target = pos['sde_target']
            sde_stop   = pos['sde_stop']

            exit_p = None
            reason = ''

            if side == 'long':
                # 1. 하드스탑 (intrabar)
                if bar_low <= sde_stop:
                    exit_p, reason = sde_stop, 'SDE하드스탑'
                # 2. 목표달성 (intrabar)
                elif bar_high >= sde_target:
                    exit_p, reason = sde_target, 'SDE목표달성'
            else:
                sde_target_s = pos['sde_target_s']
                sde_stop_s   = pos['sde_stop_s']
                if bar_high >= sde_stop_s:
                    exit_p, reason = sde_stop_s, 'SDE하드스탑'
                elif bar_low <= sde_target_s:
                    exit_p, reason = sde_target_s, 'SDE목표달성'

            if exit_p is None:
                # 3. 확률역전 (봉 종가 기준 GBM 재추정)
                mu, sigma = estimate_gbm(closes[:i+1], SDE_EST_WINDOW)
                if mu is not None:
                    S = bar_close
                    if side == 'long':
                        p_cont = barrier_prob(S, sde_target, sde_stop, mu, sigma)
                    else:
                        p_cont = 1.0 - barrier_prob(S, pos['sde_stop_s'],
                                                     pos['sde_target_s'], mu, sigma)
                    if p_cont < SDE_EXIT_PROB:
                        exit_p, reason = bar_close, f'SDE확률역전(P:{p_cont:.2f})'

            # 4. 시간 초과
            if exit_p is None and bars_held >= SDE_MAX_BARS:
                exit_p, reason = bar_close, f'SDE시간초과({bars_held}봉)'

            if exit_p is not None:
                if side == 'long':
                    raw_pnl = (exit_p - entry) * pos['size']
                else:
                    raw_pnl = (entry - exit_p) * pos['size']

                raw_pnl *= leverage
                comm     = (entry + exit_p) * pos['size'] * COMMISSION
                pnl      = raw_pnl - comm
                cash    += pnl

                trades.append({
                    'dt'    : df.index[i],
                    'dt_in' : df.index[pos['entry_bar']],
                    'side'  : side,
                    'entry' : entry,
                    'exit_p': exit_p,
                    'pnl'   : pnl,
                    'reason': reason,
                    'bars'  : bars_held,
                })
                pos = None

        # ── 자산 기록 ──────────────────────────────────────────────
        if pos is not None:
            unreal = ((bar_close - pos['entry_price']) if pos['side'] == 'long'
                      else (pos['entry_price'] - bar_close)) * pos['size'] * leverage
            equity.append(cash + unreal)
        else:
            equity.append(cash)

        # ── 진입 체크 ──────────────────────────────────────────────
        if pos is not None:
            continue

        # XGB 필터
        if rf is not None:
            feat_row  = feat_df.iloc[i]
            feat_vals = feat_row[list(FEATURE_NAMES[:-1])].values.astype(float)
            if not np.isnan(feat_vals).any():
                row  = np.append(feat_vals, 0.5).reshape(1, -1)
                prob = float(rf.model.predict_proba(row)[0][1])
                if prob < XGB_THRESHOLD:
                    continue

        # GBM 파라미터 추정
        mu, sigma = estimate_gbm(closes[:i+1], SDE_EST_WINDOW)
        if mu is None:
            continue

        S = bar_close
        p_long, p_short = sde_entry_probs(S, SDE_TARGET_ROR, SDE_STOP_ROR, mu, sigma)

        if p_long > SDE_ENTRY_PROB and p_long >= p_short:
            direction = 'long'
        elif p_short > SDE_ENTRY_PROB and p_short > p_long:
            direction = 'short'
        else:
            continue

        size = cash * POSITION_PCT / S
        pos  = {
            'side'       : direction,
            'entry_price': S,
            'size'       : size,
            'entry_bar'  : i,
            'sde_target' : S * (1.0 + SDE_TARGET_ROR),
            'sde_stop'   : S * (1.0 - SDE_STOP_ROR),
            'sde_target_s': S * (1.0 - SDE_TARGET_ROR),
            'sde_stop_s'  : S * (1.0 + SDE_STOP_ROR),
        }

    eq_idx = df.index[warmup: warmup + len(equity)]
    return (_stats(trades, equity, cash),
            pd.Series(equity, index=eq_idx))


# ── 출력 ─────────────────────────────────────────────────────────
def print_comparison(leverage: int, base_r, xgb_r):
    print(f"\n  Lev {leverage}x  {'거래':>5}  {'승률':>6}  {'ROR':>8}  "
          f"{'Sharpe':>7}  {'MDD':>6}  {'P/L':>5}")
    print(f"  {'-'*50}")
    for label, r in [('필터없음', base_r), ('XGB필터 ', xgb_r)]:
        if r is None:
            print(f"  {label}  결과없음"); continue
        print(f"  {label}  {r['total']:>5}  {r['win_rate']:>5.1f}%  "
              f"{r['ror']:>+7.1f}%  {r['sharpe']:>6.2f}  "
              f"{r['mdd']:>5.1f}%  {r['pl_ratio']:>4.2f}")
    if base_r and xgb_r:
        dr = xgb_r['ror'] - base_r['ror']
        ds = xgb_r['sharpe'] - base_r['sharpe']
        dm = xgb_r['mdd']   - base_r['mdd']
        print(f"  {'Δ(XGB-base)':>10}  {xgb_r['total']-base_r['total']:>+5}  "
              f"{'':>6}  {dr:>+7.1f}%  {ds:>+6.2f}  {dm:>+5.1f}%")


def plot_results(base_results: dict, xgb_results: dict,
                 eq_base_lev: dict, eq_xgb_lev: dict,
                 df: pd.DataFrame, save: bool = False):
    import matplotlib
    if save:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.gridspec import GridSpec

    BG    = '#0d1117'; PANEL = '#161b22'; GRID = '#30363d'; TEXT = '#c9d1d9'
    COLORS_B = ['#8b949e', '#58a6ff', '#3fb950', '#e3b341', '#f85149']
    COLORS_X = ['#c9d1d9', '#79c0ff', '#56d364', '#f0b429', '#ff7b72']
    LEVERS   = [1, 2, 3, 5]

    fig = plt.figure(figsize=(18, 10), facecolor=BG)
    gs  = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.28)
    ax_eq  = fig.add_subplot(gs[0, :])   # 자산 곡선 (상단 전체)
    ax_ror = fig.add_subplot(gs[1, 0])   # ROR 바 차트
    ax_mdd = fig.add_subplot(gs[1, 1])   # MDD 바 차트

    for ax in [ax_eq, ax_ror, ax_mdd]:
        ax.set_facecolor(PANEL)
        ax.tick_params(colors=TEXT, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(GRID)
        ax.grid(True, color=GRID, linewidth=0.5, alpha=0.6)

    # ── 자산 곡선 ─────────────────────────────────────────────────
    for idx, lev in enumerate(LEVERS):
        eq_b = eq_base_lev.get(lev)
        eq_x = eq_xgb_lev.get(lev)
        if eq_b is not None:
            ax_eq.plot(eq_b.index, eq_b.values,
                       color=COLORS_B[idx], linewidth=1.0, alpha=0.5,
                       label=f"Base {lev}x ({base_results[lev]['ror']:+.0f}%)" if base_results.get(lev) else f"Base {lev}x")
        if eq_x is not None:
            ax_eq.plot(eq_x.index, eq_x.values,
                       color=COLORS_X[idx], linewidth=1.5,
                       label=f"XGB  {lev}x ({xgb_results[lev]['ror']:+.0f}%)" if xgb_results.get(lev) else f"XGB {lev}x",
                       linestyle='--')

    ax_eq.axhline(INITIAL, color=GRID, linewidth=0.8, linestyle=':')
    ax_eq.set_ylabel('Portfolio ($)', color=TEXT, fontsize=9)
    ax_eq.set_title('BTC SDE Strategy — 자산 곡선  (실선=필터없음, 점선=XGB필터)',
                    color=TEXT, fontsize=10, fontweight='bold')
    ax_eq.legend(fontsize=7.5, facecolor=PANEL, labelcolor=TEXT,
                 loc='upper left', ncol=2)
    ax_eq.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax_eq.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax_eq.get_xticklabels(), rotation=20, ha='right', color=TEXT)

    # ── ROR 바 차트 ───────────────────────────────────────────────
    x = np.arange(len(LEVERS)); bw = 0.35
    rors_b = [base_results[l]['ror'] if base_results.get(l) else 0 for l in LEVERS]
    rors_x = [xgb_results[l]['ror']  if xgb_results.get(l)  else 0 for l in LEVERS]
    ax_ror.bar(x - bw/2, rors_b, bw, color='#8b949e', alpha=0.7, label='필터없음')
    ax_ror.bar(x + bw/2, rors_x, bw, color='#58a6ff', alpha=0.9, label='XGB필터')
    ax_ror.axhline(0, color=GRID, linewidth=1.0)
    ax_ror.set_xticks(x)
    ax_ror.set_xticklabels([f'{l}x' for l in LEVERS], color=TEXT)
    ax_ror.set_ylabel('ROR (%)', color=TEXT, fontsize=9)
    ax_ror.set_title('레버리지별 ROR', color=TEXT, fontsize=9)
    ax_ror.legend(fontsize=8, facecolor=PANEL, labelcolor=TEXT)
    for i, (rb, rx) in enumerate(zip(rors_b, rors_x)):
        ax_ror.text(i - bw/2, rb + (5 if rb >= 0 else -10),
                    f"{rb:+.0f}%", ha='center', fontsize=7, color=TEXT)
        ax_ror.text(i + bw/2, rx + (5 if rx >= 0 else -10),
                    f"{rx:+.0f}%", ha='center', fontsize=7, color=TEXT)

    # ── MDD 바 차트 ───────────────────────────────────────────────
    mdds_b = [base_results[l]['mdd'] if base_results.get(l) else 0 for l in LEVERS]
    mdds_x = [xgb_results[l]['mdd']  if xgb_results.get(l)  else 0 for l in LEVERS]
    ax_mdd.bar(x - bw/2, mdds_b, bw, color='#f85149', alpha=0.55, label='필터없음')
    ax_mdd.bar(x + bw/2, mdds_x, bw, color='#ff9bce', alpha=0.85, label='XGB필터')
    ax_mdd.set_xticks(x)
    ax_mdd.set_xticklabels([f'{l}x' for l in LEVERS], color=TEXT)
    ax_mdd.set_ylabel('MDD (%)', color=TEXT, fontsize=9)
    ax_mdd.set_title('레버리지별 MDD', color=TEXT, fontsize=9)
    ax_mdd.legend(fontsize=8, facecolor=PANEL, labelcolor=TEXT)
    for i, (mb, mx) in enumerate(zip(mdds_b, mdds_x)):
        ax_mdd.text(i - bw/2, mb + 1, f"{mb:.0f}%", ha='center', fontsize=7, color=TEXT)
        ax_mdd.text(i + bw/2, mx + 1, f"{mx:.0f}%", ha='center', fontsize=7, color=TEXT)

    os.makedirs('charts', exist_ok=True)
    if save:
        out = 'charts/btc_sde_xgb.png'
        plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=BG)
        print(f"\n  차트 저장: {out}")
        plt.close(fig)
    else:
        plt.show()


# ── main ─────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plot',       action='store_true', help='차트 표시')
    parser.add_argument('--chart-save', action='store_true', help='차트 PNG 저장')
    args = parser.parse_args()

    if not os.path.exists(DATA_PATH):
        print(f"데이터 없음: {DATA_PATH}"); sys.exit(1)

    df = load_ohlcv(DATA_PATH)
    print(f"\nBTC SDE 전략 — XGB 레짐 필터 비교")
    print(f"데이터: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df):,}봉)")

    LEVERAGES = [1, 2, 3, 5]

    base_results: dict = {}
    xgb_results:  dict = {}
    eq_base_lev:  dict = {}
    eq_xgb_lev:   dict = {}

    print(f"\n{'='*60}")
    print(f"  BTC SDE  (target={SDE_TARGET_ROR*100:.0f}%  stop={SDE_STOP_ROR*100:.0f}%  "
          f"entry_prob={SDE_ENTRY_PROB}  exit_prob={SDE_EXIT_PROB}  max_bars={SDE_MAX_BARS})")
    print(f"{'='*60}")

    for lev in LEVERAGES:
        print(f"\n  [leverage={lev}x]")

        print(f"    필터없음...", end=' ', flush=True)
        r_b, eq_b = simulate(df, leverage=lev, use_xgb=False)
        base_results[lev] = r_b
        eq_base_lev[lev]  = eq_b
        print(f"{r_b['total']}거래  ROR {r_b['ror']:+.1f}%  MDD {r_b['mdd']:.1f}%" if r_b else "결과없음")

        print(f"    XGB필터 ...", end=' ', flush=True)
        r_x, eq_x = simulate(df, leverage=lev, use_xgb=True)
        xgb_results[lev] = r_x
        eq_xgb_lev[lev]  = eq_x
        print(f"{r_x['total']}거래  ROR {r_x['ror']:+.1f}%  MDD {r_x['mdd']:.1f}%" if r_x else "결과없음")

        print_comparison(lev, r_b, r_x)

    # ── 전체 요약 ─────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  전체 요약")
    print(f"{'='*65}")
    print(f"  {'레버':>5}  {'기준ROR':>8}  {'XGBROR':>8}  {'ΔROR':>7}  "
          f"{'기준MDD':>7}  {'XGBMDD':>7}  {'ΔMDD':>6}  "
          f"{'기준거래':>6}  {'XGB거래':>6}")
    print(f"  {'-'*63}")
    for lev in LEVERAGES:
        rb = base_results.get(lev)
        rx = xgb_results.get(lev)
        if not rb or not rx:
            continue
        dr = rx['ror'] - rb['ror']
        dm = rx['mdd'] - rb['mdd']
        mark = '▲' if dr > 0 else '▼'
        print(f"  {lev:>4}x  {rb['ror']:>+7.1f}%  {rx['ror']:>+7.1f}%  "
              f"{mark}{abs(dr):>5.1f}%  "
              f"{rb['mdd']:>6.1f}%  {rx['mdd']:>6.1f}%  {dm:>+5.1f}%  "
              f"{rb['total']:>6}  {rx['total']:>6}")
    print(f"{'='*65}")

    # 연도별 상세 (leverage=5x, XGB 기준)
    r = xgb_results.get(5)
    if r:
        td = r['trades'].copy()
        td['year'] = td['dt'].dt.year
        print(f"\n  연도별 성과 (leverage=5x, XGB필터):")
        print(f"  {'년':>4}  {'거래':>5}  {'승률':>6}  {'ROR':>8}")
        print(f"  {'-'*30}")
        cb = INITIAL
        for yr in sorted(td['year'].unique()):
            g  = td[td['year'] == yr]
            rb = g['pnl'].sum() / cb * 100
            cb += g['pnl'].sum()
            wr = (g['pnl'] > 0).mean() * 100
            print(f"  {yr:>4}  {len(g):>5}  {wr:>5.1f}%  {rb:>+7.1f}%")

    if args.plot or args.chart_save:
        plot_results(base_results, xgb_results,
                     eq_base_lev, eq_xgb_lev, df,
                     save=args.chart_save)
