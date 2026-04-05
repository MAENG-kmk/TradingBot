"""
XGBoost 레짐 필터 Walk-Forward 백테스트

접근법:
  - VB(k=0.3, close) 시그널 발생 시점의 시장 피처로 "이 거래가 수익인가?" 학습
  - Walk-forward: 처음 MIN_TRAIN개 시그널 수집 → 이후 RETRAIN_EVERY개마다 재학습
  - 기준선(필터없음) vs XGB 필터 성과 비교
  - 최종 전체 데이터로 학습한 모델을 models/ 에 저장

사용법:
  python backtest_xgb_regime.py              # 전체 코인
  python backtest_xgb_regime.py --coin doge  # 단일 코인 상세
  python backtest_xgb_regime.py --save       # 모델 저장 포함
"""

import argparse, os, sys
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from tools.regime_filter import RegimeFilter, build_features, FEATURE_NAMES

COMMISSION   = 0.0005
INITIAL      = 100_000.0
POSITION_PCT = 0.10

VB_K          = 0.3
MIN_RANGE_PCT = 0.3

# 코인별 슬리피지 (편도, bid-ask 스프레드 시뮬레이션)
# BTC/ETH: 0.02% / SOL/BNB/XRP/LINK: 0.03% / DOGE/AVAX/ARB/AAVE: 0.05%
COIN_SLIPPAGE = {
    'btc' : 0.0002,
    'eth' : 0.0002,
    'sol' : 0.0003,
    'bnb' : 0.0003,
    'xrp' : 0.0003,
    'link': 0.0003,
    'doge': 0.0005,
    'avax': 0.0005,
    'arb' : 0.0005,
    'aave': 0.0005,
}

# Walk-forward 파라미터
MIN_TRAIN      = 200   # 학습 시작 최소 시그널 수
RETRAIN_EVERY  = 50    # 재학습 주기 (시그널 기준)
THRESHOLD      = 0.55  # 진입 확률 임계값


COIN_DATA = {
    'btc' : ('backtestDatas/btcusdt_4h.csv',  'BTCUSDT'),
    'eth' : ('backtestDatas/ethusdt_4h.csv',  'ETHUSDT'),
    'sol' : ('backtestDatas/solusdt_4h.csv',  'SOLUSDT'),
    'bnb' : ('backtestDatas/bnbusdt_4h.csv',  'BNBUSDT'),
    'xrp' : ('backtestDatas/xrpusdt_4h.csv',  'XRPUSDT'),
    'link': ('backtestDatas/linkusdt_4h.csv', 'LINKUSDT'),
    'doge': ('backtestDatas/dogeusdt_4h.csv', 'DOGEUSDT'),
    'avax': ('backtestDatas/avaxusdt_4h.csv', 'AVAXUSDT'),
    'arb' : ('backtestDatas/arbusdt_4h.csv',  'ARBUSDT'),
    'aave': ('backtestDatas/aaveusdt_4h.csv', 'AAVEUSDT'),
}


# ── 데이터 로드 ──────────────────────────────────────────────────
def load_ohlcv(path):
    df = pd.read_csv(path, index_col='Date', parse_dates=True)
    df.index = df.index.tz_localize(None)
    return df[['Open','High','Low','Close','Volume']].astype(float).sort_index()


# ── 통계 계산 ────────────────────────────────────────────────────
def _stats(trades: list, equity: list, final_cash: float) -> dict | None:
    if not trades:
        return None
    td  = pd.DataFrame(trades)
    eq  = pd.Series(equity)
    tot = len(td)
    won = (td['pnl'] > 0).sum()
    lst = (td['pnl'] <= 0).sum()
    ap  = td.loc[td['pnl'] > 0, 'pnl'].mean() if won > 0 else 0
    al  = td.loc[td['pnl'] <= 0, 'pnl'].mean() if lst > 0 else 0
    pl  = abs(ap / al) if al != 0 else 0
    ror = (final_cash - INITIAL) / INITIAL * 100
    rm  = eq.cummax()
    mdd = ((eq - rm) / rm * 100).min()
    ret = eq.pct_change().dropna()
    sh  = ret.mean() / ret.std() * np.sqrt(365*6) if ret.std() > 0 else 0
    return dict(total=tot, won=won, lost=lst, win_rate=won/tot*100,
                pl_ratio=pl, ror=ror, sharpe=sh, mdd=mdd,
                avg_win=ap, avg_loss=al, final=final_cash, trades=td)


# ── Walk-Forward 시뮬레이션 ──────────────────────────────────────
def run_walkforward(df: pd.DataFrame, slippage_pct: float = 0.0003, verbose=False):
    """
    반환: (base_result, xgb_result, final_model, signal_X, signal_y)

    slippage_pct: 편도 슬리피지 비율 (0.0003 = 0.03%)
      - 롱 진입: entry × (1 + slip) 에 매수 체결
      - 롱 청산: exit  × (1 - slip) 에 매도 체결
      - 숏은 반대 방향
    """
    feat_df = build_features(df)

    o = df['Open']; h = df['High']; l = df['Low']; c = df['Close']
    prev_range = (h - l).shift(1)
    prev_close = c.shift(1)
    range_pct  = prev_range / (prev_close + 1e-9) * 100
    long_trig  = o + VB_K * prev_range
    short_trig = o - VB_K * prev_range

    warmup = 252

    cash_b = INITIAL;  eq_b = [];  tr_b = []
    cash_x = INITIAL;  eq_x = [];  tr_x = []

    signal_X:  list = []
    signal_y:  list = []
    retrain_cnt = 0
    model = None

    for i in range(warmup, len(df) - 1):
        pr    = prev_range.iloc[i]
        rng_p = range_pct.iloc[i]
        lt    = long_trig.iloc[i]
        st    = short_trig.iloc[i]
        hi    = h.iloc[i]; lo = l.iloc[i]
        cl    = c.iloc[i]; op = o.iloc[i]

        # 기본 VB 조건
        if pd.isna(pr) or pr <= 0 or rng_p < MIN_RANGE_PCT:
            eq_b.append(cash_b); eq_x.append(cash_x); continue

        long_ok  = hi >= lt and lt > op
        short_ok = lo <= st and st < op
        if long_ok and short_ok:
            eq_b.append(cash_b); eq_x.append(cash_x); continue

        dir_now = 'long' if long_ok else ('short' if short_ok else None)
        if dir_now is None:
            eq_b.append(cash_b); eq_x.append(cash_x); continue

        entry  = lt if dir_now == 'long' else st
        exit_p = cl

        # 슬리피지 적용: 롱은 진입 비싸게·청산 싸게, 숏은 반대
        slip = slippage_pct
        if dir_now == 'long':
            entry_eff = entry  * (1 + slip)
            exit_eff  = exit_p * (1 - slip)
        else:
            entry_eff = entry  * (1 - slip)
            exit_eff  = exit_p * (1 + slip)

        # 기준선 (항상 진입)
        sz_b   = cash_b * POSITION_PCT / entry_eff
        comm_b = (entry_eff + exit_eff) * sz_b * COMMISSION
        pnl_b  = ((exit_eff - entry_eff) if dir_now == 'long'
                  else (entry_eff - exit_eff)) * sz_b - comm_b
        cash_b += pnl_b
        tr_b.append(dict(dt=df.index[i], dir=dir_now, entry=entry_eff, exit_p=exit_eff, pnl=pnl_b))

        # 피처 추출
        feat_row = feat_df.iloc[i][list(FEATURE_NAMES[:-1])].values.astype(float)
        label    = 1 if pnl_b > 0 else 0
        recent_wr = np.mean(signal_y[-20:]) if len(signal_y) >= 20 else 0.5
        feat_full = np.append(feat_row, recent_wr)

        # XGB 예측
        enter_xgb = True
        if model is not None and len(signal_y) >= MIN_TRAIN:
            if not np.isnan(feat_full).any():
                prob      = float(model.predict_proba(feat_full.reshape(1, -1))[0][1])
                enter_xgb = prob >= THRESHOLD
                if verbose:
                    print(f"    bar {i}: prob={prob:.3f} enter={enter_xgb}")

        if enter_xgb:
            sz_x   = cash_x * POSITION_PCT / entry_eff
            comm_x = (entry_eff + exit_eff) * sz_x * COMMISSION
            pnl_x  = ((exit_eff - entry_eff) if dir_now == 'long'
                      else (entry_eff - exit_eff)) * sz_x - comm_x
            cash_x += pnl_x
            tr_x.append(dict(dt=df.index[i], dir=dir_now, entry=entry_eff, exit_p=exit_eff, pnl=pnl_x))

        eq_b.append(cash_b)
        eq_x.append(cash_x)

        # 시그널 적재 & 재학습
        # signal_X에는 기본 13개 피처만 저장 (recent_wr 제외)
        # → fit_with_history / 재학습 시 recent_wr를 실제 히스토리로 계산해 추가
        signal_X.append(feat_row)
        signal_y.append(label)
        retrain_cnt += 1

        if len(signal_y) >= MIN_TRAIN and retrain_cnt >= RETRAIN_EVERY:
            X_base = np.array(signal_X)          # (n, 13)
            y_arr  = np.array(signal_y)
            n      = len(y_arr)
            # 각 샘플의 recent_wr: 해당 시점까지의 과거 승패 기반
            rw     = np.array([np.mean(y_arr[max(0, i-20):i]) if i > 0 else 0.5
                                for i in range(n)])
            X_train = np.hstack([X_base, rw.reshape(-1, 1)])  # (n, 14)
            mask    = ~np.isnan(X_train).any(axis=1)
            if mask.sum() >= MIN_TRAIN:
                rf = RegimeFilter()
                rf.model.fit(X_train[mask], y_arr[mask])
                rf._fitted = True
                model = rf.model
            retrain_cnt = 0

    # 최종 모델 (전체 데이터로 재학습)
    final_rf = None
    if signal_X:
        X_all = np.array(signal_X)
        y_all = np.array(signal_y)
        mask  = ~np.isnan(X_all).any(axis=1)
        if mask.sum() >= MIN_TRAIN:
            final_rf = RegimeFilter()
            final_rf.fit_with_history(X_all[mask], y_all[mask])

    # equity 시리즈 — 날짜 인덱스 부여
    eq_idx    = df.index[warmup: warmup + len(eq_b)]
    eq_base_s = pd.Series(eq_b, index=eq_idx)
    eq_xgb_s  = pd.Series(eq_x, index=eq_idx)

    return (
        _stats(tr_b, eq_b, cash_b),
        _stats(tr_x, eq_x, cash_x),
        final_rf,
        np.array(signal_X),
        np.array(signal_y),
        eq_base_s,
        eq_xgb_s,
    )


# ── 출력 ─────────────────────────────────────────────────────────
def print_detail(coin: str, base, xgb):
    print(f"\n{'='*65}")
    print(f"  {coin.upper()}  —  XGBoost 레짐 필터 비교 (k={VB_K}, pos={POSITION_PCT*100:.0f}%)")
    print(f"{'='*65}")
    print(f"  {'':>12}  {'거래':>5}  {'승률':>6}  {'ROR':>8}  {'Sharpe':>7}  {'MDD':>6}  {'P/L':>5}")
    print(f"  {'-'*55}")
    for label, r in [('필터없음', base), ('XGB필터', xgb)]:
        if r is None:
            print(f"  {label:>12}  결과없음")
            continue
        print(f"  {label:>12}  {r['total']:>5}  {r['win_rate']:>5.1f}%  "
              f"{r['ror']:>+7.1f}%  {r['sharpe']:>6.2f}  {r['mdd']:>5.1f}%  {r['pl_ratio']:>4.2f}")
    print(f"{'='*65}")

    if base and xgb:
        diff_ror   = xgb['ror']   - base['ror']
        diff_sh    = xgb['sharpe']- base['sharpe']
        diff_mdd   = xgb['mdd']   - base['mdd']
        diff_trade = xgb['total'] - base['total']
        print(f"  차이:  ROR {diff_ror:>+7.1f}%  Sharpe {diff_sh:>+5.2f}  "
              f"MDD {diff_mdd:>+5.1f}%  거래수 {diff_trade:>+5}")

    # 연도별 비교
    if base and xgb:
        print(f"\n  연도별 성과:")
        print(f"  {'년':>4}  {'기준ROR':>8}  {'XGB ROR':>8}  {'기준거래':>8}  {'XGB거래':>8}")
        print(f"  {'-'*45}")
        td_b = base['trades'].copy(); td_b['year'] = td_b['dt'].dt.year
        td_x = xgb['trades'].copy();  td_x['year'] = td_x['dt'].dt.year
        cb = INITIAL; cx = INITIAL
        for yr in sorted(set(td_b['year']) | set(td_x['year'])):
            gb = td_b[td_b['year'] == yr]
            gx = td_x[td_x['year'] == yr]
            rb = gb['pnl'].sum() / cb * 100 if len(gb) > 0 else 0
            rx = gx['pnl'].sum() / cx * 100 if len(gx) > 0 else 0
            cb += gb['pnl'].sum(); cx += gx['pnl'].sum()
            mark = '▲' if rx > rb else ('▼' if rx < rb else '─')
            print(f"  {yr:>4}  {rb:>+7.1f}%  {rx:>+7.1f}% {mark}  "
                  f"{len(gb):>8}  {len(gx):>8}")


def print_importance(rf: RegimeFilter, top_n=10):
    if rf is None:
        return
    imp = sorted(rf.feature_importances.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  피처 중요도 (상위 {top_n}):")
    for name, score in imp[:top_n]:
        bar = '█' * int(score * 200)
        print(f"    {name:>16}: {score:.4f}  {bar}")


# ── 차트 ─────────────────────────────────────────────────────────

def plot_results(coin: str,
                 base, xgb_r,
                 eq_base: pd.Series, eq_xgb: pd.Series,
                 df: pd.DataFrame,
                 save: bool = False):
    """
    4-패널 차트:
      1. 가격 + 진입 마커 (수익=초록▲, 손실=빨강▼)
      2. 자산 곡선 비교 (Base vs XGB)
      3. 드로우다운
      4. 연도별 수익률 바 차트
    """
    import matplotlib
    if save:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.gridspec import GridSpec

    # ── 색상 ──
    BG    = '#0d1117'
    PANEL = '#161b22'
    GRID  = '#30363d'
    TEXT  = '#c9d1d9'
    BASE  = '#8b949e'
    XGB   = '#58a6ff'
    WIN   = '#3fb950'
    LOSS  = '#f85149'

    fig = plt.figure(figsize=(18, 11), facecolor=BG)
    gs  = GridSpec(3, 2, figure=fig,
                   height_ratios=[3, 2, 1.2],
                   width_ratios=[3, 1],
                   hspace=0.08, wspace=0.25)

    ax_price  = fig.add_subplot(gs[0, 0])
    ax_equity = fig.add_subplot(gs[1, 0], sharex=ax_price)
    ax_dd     = fig.add_subplot(gs[2, 0], sharex=ax_price)
    ax_annual = fig.add_subplot(gs[:, 1])

    for ax in [ax_price, ax_equity, ax_dd, ax_annual]:
        ax.set_facecolor(PANEL)
        ax.tick_params(colors=TEXT, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(GRID)
        ax.grid(True, color=GRID, linewidth=0.5, alpha=0.6)

    # ── 패널 1: 가격 + 진입 마커 ──────────────────────────────────
    ax_price.plot(df.index, df['Close'],
                  color='#30363d', linewidth=0.7, alpha=0.9, zorder=1)

    if xgb_r:
        td = xgb_r['trades']
        wins   = td[td['pnl'] > 0]
        losses = td[td['pnl'] <= 0]
        ax_price.scatter(wins['dt'],   wins['entry'],
                         marker='^', color=WIN,  s=18, alpha=0.75, zorder=3,
                         label=f"Win  ({len(wins)})")
        ax_price.scatter(losses['dt'], losses['entry'],
                         marker='v', color=LOSS, s=18, alpha=0.75, zorder=3,
                         label=f"Loss ({len(losses)})")

    title = (f"{coin.upper()}  VB(k={VB_K}) + XGB Filter  |  "
             f"ROR: {xgb_r['ror']:+.1f}%  "
             f"Sharpe: {xgb_r['sharpe']:.2f}  "
             f"MDD: {xgb_r['mdd']:.1f}%  "
             f"WinRate: {xgb_r['win_rate']:.1f}%"
             if xgb_r else coin.upper())
    ax_price.set_title(title, color=TEXT, fontsize=10, fontweight='bold', pad=8)
    ax_price.set_ylabel('Price', color=TEXT, fontsize=9)
    ax_price.legend(fontsize=8, facecolor=PANEL, labelcolor=TEXT,
                    loc='upper left', markerscale=1.5)
    plt.setp(ax_price.get_xticklabels(), visible=False)

    # ── 패널 2: 자산 곡선 ─────────────────────────────────────────
    ax_equity.plot(eq_base.index, eq_base.values,
                   color=BASE, linewidth=1.0, alpha=0.7,
                   label=f"Base  {base['ror']:+.1f}%" if base else "Base")
    ax_equity.plot(eq_xgb.index, eq_xgb.values,
                   color=XGB, linewidth=1.5,
                   label=f"XGB   {xgb_r['ror']:+.1f}%" if xgb_r else "XGB")
    ax_equity.axhline(INITIAL, color=GRID, linewidth=0.8, linestyle='--')
    ax_equity.set_ylabel('Portfolio ($)', color=TEXT, fontsize=9)
    ax_equity.legend(fontsize=8, facecolor=PANEL, labelcolor=TEXT, loc='upper left')
    plt.setp(ax_equity.get_xticklabels(), visible=False)

    # ── 패널 3: 드로우다운 ────────────────────────────────────────
    for eq_s, color, alpha in [(eq_base, BASE, 0.4), (eq_xgb, XGB, 0.65)]:
        dd = (eq_s - eq_s.cummax()) / eq_s.cummax() * 100
        ax_dd.fill_between(dd.index, dd.values, 0,
                           color=color, alpha=alpha)
    ax_dd.set_ylabel('Drawdown (%)', color=TEXT, fontsize=9)
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax_dd.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax_dd.get_xticklabels(), rotation=30, ha='right', color=TEXT)

    # ── 패널 4: 연도별 수익률 ─────────────────────────────────────
    if base and xgb_r:
        td_b = base['trades'].copy();  td_b['year'] = td_b['dt'].dt.year
        td_x = xgb_r['trades'].copy(); td_x['year'] = td_x['dt'].dt.year
        years = sorted(set(td_b['year']) | set(td_x['year']))
        cb = INITIAL; cx = INITIAL
        rb_list = []; rx_list = []
        for yr in years:
            gb = td_b[td_b['year'] == yr]
            gx = td_x[td_x['year'] == yr]
            rb = gb['pnl'].sum() / cb * 100 if len(gb) > 0 else 0.0
            rx = gx['pnl'].sum() / cx * 100 if len(gx) > 0 else 0.0
            cb += gb['pnl'].sum(); cx += gx['pnl'].sum()
            rb_list.append(rb); rx_list.append(rx)

        y  = np.arange(len(years))
        bw = 0.35
        ax_annual.barh(y - bw/2, rb_list, bw,
                       color=[WIN if v >= 0 else LOSS for v in rb_list],
                       alpha=0.55, label='Base')
        ax_annual.barh(y + bw/2, rx_list, bw,
                       color=[WIN if v >= 0 else LOSS for v in rx_list],
                       alpha=0.9, label='XGB')
        ax_annual.set_yticks(y)
        ax_annual.set_yticklabels([str(yr) for yr in years], color=TEXT, fontsize=9)
        ax_annual.axvline(0, color=GRID, linewidth=1.0)
        ax_annual.set_xlabel('Annual ROR (%)', color=TEXT, fontsize=9)
        ax_annual.set_title('Annual Returns\n(light=Base, dark=XGB)',
                             color=TEXT, fontsize=9)

        # 값 라벨
        for i, (rb, rx) in enumerate(zip(rb_list, rx_list)):
            ax_annual.text(rb + (1 if rb >= 0 else -1), i - bw/2,
                           f"{rb:+.0f}%", va='center', fontsize=7,
                           color=TEXT, alpha=0.7)
            ax_annual.text(rx + (1 if rx >= 0 else -1), i + bw/2,
                           f"{rx:+.0f}%", va='center', fontsize=7,
                           color=TEXT)

    os.makedirs('charts', exist_ok=True)
    if save:
        out = f"charts/{coin}_backtest.png"
        plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=BG)
        print(f"  차트 저장: {out}")
        plt.close(fig)
    else:
        plt.show()


# ── main ─────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--coin', default='all')
    parser.add_argument('--save', action='store_true', help='models/ 에 모델 저장')
    parser.add_argument('--threshold', type=float, default=THRESHOLD)
    parser.add_argument('--slippage', type=float, default=None,
                        help='슬리피지 (소수, ex. 0.0003). 미지정 시 코인별 기본값 사용')
    parser.add_argument('--plot', action='store_true', help='차트 표시 (단일 코인 모드)')
    parser.add_argument('--chart-save', action='store_true', help='차트를 PNG로 저장')
    args = parser.parse_args()

    THRESHOLD = args.threshold
    coins = {args.coin: COIN_DATA[args.coin]} if args.coin != 'all' else COIN_DATA

    summary_rows = []

    for coin, (path, symbol) in coins.items():
        if not os.path.exists(path):
            print(f"  {coin}: 데이터 없음"); continue

        slip = args.slippage if args.slippage is not None else COIN_SLIPPAGE.get(coin, 0.0003)

        print(f"\n[{coin.upper()}] 피처 계산 + Walk-Forward 중...")
        df = load_ohlcv(path)
        print(f"  데이터: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df):,}봉)")
        print(f"  수수료: {COMMISSION*100:.3f}%  슬리피지: {slip*100:.3f}% (편도)")

        base, xgb_r, final_rf, sig_X, sig_y, eq_base_s, eq_xgb_s = run_walkforward(df, slippage_pct=slip)

        summary_rows.append(dict(
            coin=coin.upper(),
            base_ror=base['ror'] if base else 0,
            xgb_ror=xgb_r['ror'] if xgb_r else 0,
            base_sh=base['sharpe'] if base else 0,
            xgb_sh=xgb_r['sharpe'] if xgb_r else 0,
            base_mdd=base['mdd'] if base else 0,
            xgb_mdd=xgb_r['mdd'] if xgb_r else 0,
            base_tot=base['total'] if base else 0,
            xgb_tot=xgb_r['total'] if xgb_r else 0,
            base_wr=base['win_rate'] if base else 0,
            xgb_wr=xgb_r['win_rate'] if xgb_r else 0,
        ))

        if args.coin != 'all':
            print_detail(coin, base, xgb_r)
            print_importance(final_rf)
            if args.plot or args.chart_save:
                plot_results(coin, base, xgb_r, eq_base_s, eq_xgb_s, df,
                             save=args.chart_save)

        if args.save and final_rf is not None:
            save_path = f'models/regime_{symbol}.pkl'
            final_rf.save(save_path)

    # 전체 요약
    if len(summary_rows) > 1 or args.coin == 'all':
        print(f"\n{'='*78}")
        print(f"  XGBoost 레짐 필터 전 코인 요약  "
              f"(threshold={THRESHOLD}, min_train={MIN_TRAIN})")
        print(f"{'='*78}")
        print(f"  {'코인':<6}  "
              f"{'기준ROR':>8}  {'XGBROR':>8}  {'Δ':>7}  "
              f"{'기준Sh':>6}  {'XGBSh':>6}  "
              f"{'기준MDD':>7}  {'XGBMDD':>7}  "
              f"{'기준거래':>6}  {'XGB거래':>6}  "
              f"{'기준승률':>6}  {'XGB승률':>6}")
        print(f"  {'-'*100}")
        for r in summary_rows:
            delta = r['xgb_ror'] - r['base_ror']
            mark  = '▲' if delta > 0 else '▼'
            print(f"  {r['coin']:<6}  "
                  f"{r['base_ror']:>+7.1f}%  {r['xgb_ror']:>+7.1f}%  "
                  f"{mark}{delta:>+6.1f}%  "
                  f"{r['base_sh']:>6.2f}  {r['xgb_sh']:>6.2f}  "
                  f"{r['base_mdd']:>6.1f}%  {r['xgb_mdd']:>6.1f}%  "
                  f"{r['base_tot']:>6}  {r['xgb_tot']:>6}  "
                  f"{r['base_wr']:>5.1f}%  {r['xgb_wr']:>5.1f}%")
        print(f"{'='*78}")

        # 개선/악화 집계
        improved = sum(1 for r in summary_rows if r['xgb_ror'] > r['base_ror'])
        print(f"\n  ROR 개선: {improved}/{len(summary_rows)}코인  "
              f"| 평균 Δ ROR: {np.mean([r['xgb_ror']-r['base_ror'] for r in summary_rows]):+.1f}%")
        print(f"  평균 거래 감소: "
              f"{np.mean([(r['base_tot']-r['xgb_tot'])/r['base_tot']*100 for r in summary_rows if r['base_tot']>0]):.1f}%")

        if args.save:
            print(f"\n  모델이 models/ 폴더에 저장되었습니다.")
            print(f"  라이브 사용: from tools.regime_filter import RegimeFilter")
            print(f"              rf = RegimeFilter.load('models/regime_DOGEUSDT.pkl')")
