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
def run_walkforward(df: pd.DataFrame, verbose=False):
    """
    반환: (base_result, xgb_result, final_model, signal_X, signal_y)
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

        # 기준선 (항상 진입)
        sz_b   = cash_b * POSITION_PCT / entry
        comm_b = (entry + exit_p) * sz_b * COMMISSION
        pnl_b  = ((exit_p - entry) if dir_now == 'long' else (entry - exit_p)) * sz_b - comm_b
        cash_b += pnl_b
        tr_b.append(dict(dt=df.index[i], dir=dir_now, entry=entry, exit_p=exit_p, pnl=pnl_b))

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
            sz_x   = cash_x * POSITION_PCT / entry
            comm_x = (entry + exit_p) * sz_x * COMMISSION
            pnl_x  = ((exit_p - entry) if dir_now == 'long' else (entry - exit_p)) * sz_x - comm_x
            cash_x += pnl_x
            tr_x.append(dict(dt=df.index[i], dir=dir_now, entry=entry, exit_p=exit_p, pnl=pnl_x))

        eq_b.append(cash_b)
        eq_x.append(cash_x)

        # 시그널 적재 & 재학습
        signal_X.append(feat_full)
        signal_y.append(label)
        retrain_cnt += 1

        if len(signal_y) >= MIN_TRAIN and retrain_cnt >= RETRAIN_EVERY:
            X_arr = np.array(signal_X)
            y_arr = np.array(signal_y)
            mask  = ~np.isnan(X_arr).any(axis=1)
            if mask.sum() >= MIN_TRAIN:
                rf = RegimeFilter()
                rf.model.fit(X_arr[mask], y_arr[mask])
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

    return (
        _stats(tr_b, eq_b, cash_b),
        _stats(tr_x, eq_x, cash_x),
        final_rf,
        np.array(signal_X),
        np.array(signal_y),
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


# ── main ─────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--coin', default='all')
    parser.add_argument('--save', action='store_true', help='models/ 에 모델 저장')
    parser.add_argument('--threshold', type=float, default=THRESHOLD)
    args = parser.parse_args()

    THRESHOLD = args.threshold
    coins = {args.coin: COIN_DATA[args.coin]} if args.coin != 'all' else COIN_DATA

    summary_rows = []

    for coin, (path, symbol) in coins.items():
        if not os.path.exists(path):
            print(f"  {coin}: 데이터 없음"); continue

        print(f"\n[{coin.upper()}] 피처 계산 + Walk-Forward 중...")
        df = load_ohlcv(path)
        print(f"  데이터: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df):,}봉)")

        base, xgb_r, final_rf, sig_X, sig_y = run_walkforward(df)

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
