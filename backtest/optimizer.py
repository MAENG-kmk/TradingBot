"""
코인별 파라미터 Grid Search 옵티마이저

사용법:
  python -m backtest.optimizer --coin xrp
  python -m backtest.optimizer --coin xrp --top 20
"""
import argparse
import sys
import os
import itertools
import time

sys.path.append(os.path.abspath("."))

import pandas as pd
import backtrader as bt
from backtest.base_strategy import CoinBacktestStrategy
from backtest.runner import COIN_CONFIGS, _load_intrabar

# 코인별 탐색 범위 정의
# 2단계 탐색: stage1(진입 파라미터) → stage2(청산 파라미터)
PARAM_GRIDS = {
    'default': {
        'stage1': {  # 추세추종 진입 파라미터 (432 조합)
            'tr_bb_period': [15, 20, 25],
            'tr_bb_std': [1.5, 2.0, 2.5],
            'rsi_overbuy': [70, 80],
            'rsi_oversell': [20, 30],
            'adx_threshold': [15, 20, 25, 30],
            'atr_multiplier': [1.5, 2.0, 3.0],
        },
        'stage2': {  # 청산 파라미터 (48 조합)
            'target_ror_pct': [5.0, 7.0, 10.0, 15.0],
            'trailing_ratio': [0.4, 0.5, 0.6, 0.7],
            'tight_trailing_ratio': [0.65, 0.75, 0.85],
        },
        'stage3': {  # VB 진입 파라미터 (20 조합) — VB_K 최솟값 0.2
            'vb_k': [0.2, 0.25, 0.3, 0.4, 0.5, 0.6],
            'vb_min_range_pct': [0.1, 0.2, 0.3, 0.5],
        },
    },
}


def run_single(data_path, params, initial_cash=100000.0, intrabar_df=None, slippage_pct=0.0003):
    """단일 파라미터 조합으로 백테스트 실행, 결과 dict 반환"""
    cerebro = bt.Cerebro()
    cerebro.addstrategy(CoinBacktestStrategy, intrabar_data=intrabar_df, **params)

    data = bt.feeds.GenericCSVData(
        dataname=data_path,
        dtformat='%Y-%m-%d %H:%M:%S',
        timeframe=bt.TimeFrame.Minutes,
        compression=240,
        openinterest=-1,
        headers=True,
    )
    cerebro.adddata(data)
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=0.0005)
    cerebro.broker.set_slippage_perc(
        perc=slippage_pct,
        slip_open=True, slip_limit=True, slip_match=True, slip_out=False,
    )
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    result = cerebro.run()
    strat = result[0]

    ta = strat.analyzers.trades.get_analysis()
    total = ta.total.total if hasattr(ta, 'total') and hasattr(ta.total, 'total') else 0
    if total == 0:
        return None

    won = ta.won.total
    lost = ta.lost.total
    avg_p = ta.won.pnl.average if won > 0 else 0
    avg_l = ta.lost.pnl.average if lost > 0 else 0
    final = cerebro.broker.getvalue()
    ror = (final - initial_cash) / initial_cash * 100
    sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio', 0) or 0
    mdd = strat.analyzers.drawdown.get_analysis().get('max', {'drawdown': 0})['drawdown']
    pl_ratio = abs(avg_p / avg_l) if avg_l != 0 else 0

    return {
        'trades': total,
        'won': won,
        'lost': lost,
        'win_rate': won / total * 100,
        'pl_ratio': pl_ratio,
        'ror': ror,
        'sharpe': sharpe,
        'mdd': mdd,
        'final': final,
        'params': params.copy(),
    }


def generate_combinations(grid):
    """파라미터 그리드에서 모든 조합 생성"""
    keys = list(grid.keys())
    values = list(grid.values())
    combos = [dict(zip(keys, combo)) for combo in itertools.product(*values)]
    return combos


def score_result(r, all_results):
    """종합 점수 계산: Sharpe 40% + ROR 30% + (100-MDD) 30%"""
    max_ror = max(x['ror'] for x in all_results)
    min_ror = min(x['ror'] for x in all_results)
    ror_range = max_ror - min_ror if max_ror != min_ror else 1

    ror_score = (r['ror'] - min_ror) / ror_range
    mdd_score = (100 - r['mdd']) / 100
    sharpe_norm = max(0, r['sharpe'])
    return sharpe_norm * 0.4 + ror_score * 0.3 + mdd_score * 0.3


def run_stage(data_path, combos, base_params, stage_name, initial_cash=100000.0, intrabar_df=None, slippage_pct=0.0003):
    """하나의 스테이지 Grid Search 실행"""
    total = len(combos)
    results = []
    start = time.time()

    for i, params in enumerate(combos):
        merged = {**base_params, **params}
        r = run_single(data_path, merged, initial_cash, intrabar_df=intrabar_df, slippage_pct=slippage_pct)
        if r and r['trades'] >= 30:
            results.append(r)

        if (i + 1) % 50 == 0 or (i + 1) == total:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 1
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(f"   [{stage_name}] {i+1}/{total} ({(i+1)/total*100:.1f}%) "
                  f"| 유효: {len(results)} | ETA: {eta:.0f}s", flush=True)

    elapsed = time.time() - start
    print(f"   [{stage_name}] 완료: {len(results)}개 유효 / {total}개 ({elapsed:.1f}초)\n")
    return results


def optimize(coin_name, top_n=10, initial_cash=100000.0):
    """3단계 Grid Search 최적화: Stage1(TR진입) → Stage2(청산) → Stage3(VB)"""
    config = COIN_CONFIGS.get(coin_name)
    if not config:
        print(f"❌ 지원하지 않는 코인: {coin_name}")
        return

    data_path = config['data_file']
    if not os.path.exists(data_path):
        print(f"❌ 데이터 파일 없음: {data_path}")
        return

    grid = PARAM_GRIDS.get(coin_name, PARAM_GRIDS['default'])
    stage1_combos = generate_combinations(grid['stage1'])
    stage2_combos = generate_combinations(grid['stage2'])
    stage3_combos = generate_combinations(grid['stage3'])

    intrabar_df = _load_intrabar(coin_name)

    print(f"🔍 {coin_name.upper()} 3단계 파라미터 최적화")
    print(f"   Stage 1 (TR진입): {len(stage1_combos)} 조합")
    print(f"   Stage 2 (청산):   {len(stage2_combos)} 조합")
    print(f"   Stage 3 (VB):     {len(stage3_combos)} 조합")
    print(f"   데이터: {data_path}")
    print(f"   1h 정밀 데이터: {'있음 (' + str(len(intrabar_df)) + '봉)' if intrabar_df is not None else '없음'}\n")

    # === Stage 1: TR 진입 파라미터 최적화 ===
    print("━━━ Stage 1: TR 진입 파라미터 탐색 ━━━")
    s1_results = run_stage(data_path, stage1_combos, {}, "S1", initial_cash, intrabar_df=intrabar_df)

    if not s1_results:
        print("❌ Stage 1 유효한 결과 없음")
        return

    for r in s1_results:
        r['score'] = score_result(r, s1_results)
    s1_results.sort(key=lambda x: x['score'], reverse=True)

    top_entry_params = []
    for r in s1_results[:3]:
        entry_p = {k: v for k, v in r['params'].items() if k in grid['stage1']}
        top_entry_params.append(entry_p)

    print(f"🏅 Stage 1 상위 3개 TR 진입 파라미터:")
    for i, ep in enumerate(top_entry_params):
        r = s1_results[i]
        print(f"   {i+1}. BB={ep.get('tr_bb_period','?')}×{ep.get('tr_bb_std','?')} "
              f"RSI={ep.get('rsi_oversell','?')}/{ep.get('rsi_overbuy','?')} "
              f"ADX≥{ep.get('adx_threshold','?')} ATR×{ep.get('atr_multiplier','?')} "
              f"→ ROR={r['ror']:.1f}% Sharpe={r['sharpe']:.2f}\n")

    # === Stage 2: 청산 파라미터 최적화 ===
    print("━━━ Stage 2: 청산 파라미터 탐색 ━━━")
    all_s2_results = []
    for i, entry_p in enumerate(top_entry_params):
        s2_results = run_stage(data_path, stage2_combos, entry_p, f"S2-{i+1}", initial_cash, intrabar_df=intrabar_df)
        all_s2_results.extend(s2_results)

    if not all_s2_results:
        print("❌ Stage 2 유효한 결과 없음")
        return

    for r in all_s2_results:
        r['score'] = score_result(r, all_s2_results)
    all_s2_results.sort(key=lambda x: x['score'], reverse=True)

    # Stage 2 최적 파라미터 (TR진입 + 청산)
    best_s2 = all_s2_results[0]
    best_tr_exit_params = {k: v for k, v in best_s2['params'].items()
                           if k in grid['stage1'] or k in grid['stage2']}

    print(f"🏅 Stage 2 최적 청산 파라미터:")
    bp2 = best_s2['params']
    print(f"   목표={bp2.get('target_ror_pct','?')}% "
          f"트레일={bp2.get('trailing_ratio','?')}/{bp2.get('tight_trailing_ratio','?')} "
          f"→ ROR={best_s2['ror']:.1f}% Sharpe={best_s2['sharpe']:.2f}\n")

    # === Stage 3: VB 파라미터 최적화 ===
    print("━━━ Stage 3: VB 파라미터 탐색 ━━━")
    s3_results = run_stage(data_path, stage3_combos, best_tr_exit_params, "S3", initial_cash, intrabar_df=intrabar_df)

    if not s3_results:
        print("⚠️  Stage 3 유효한 결과 없음 — VB 기본값(k=0.3, min_range=0.3) 사용")
        s3_results = [best_s2]
        for r in s3_results:
            r['params'].setdefault('vb_k', 0.3)
            r['params'].setdefault('vb_min_range_pct', 0.3)
    else:
        for r in s3_results:
            r['score'] = score_result(r, s3_results)
        s3_results.sort(key=lambda x: x['score'], reverse=True)

    results = s3_results

    # 상위 결과 출력
    print(f"\n{'='*110}")
    print(f"🏆 {coin_name.upper()} 상위 {min(top_n, len(results))}개 파라미터 조합 (TR+VB 통합)")
    print(f"{'='*110}")
    print(f"{'순위':>4} {'ROR':>8} {'샤프':>6} {'MDD':>6} {'승률':>6} {'거래':>5} {'점수':>6} | 파라미터")
    print(f"{'-'*110}")

    for i, r in enumerate(results[:top_n]):
        p = r['params']
        params_str = (
            f"BB={p.get('tr_bb_period','?')}×{p.get('tr_bb_std','?')} "
            f"RSI={p.get('rsi_oversell','?')}/{p.get('rsi_overbuy','?')} "
            f"ADX≥{p.get('adx_threshold','?')} ATR×{p.get('atr_multiplier','?')} "
            f"목표={p.get('target_ror_pct','?')}% TR={p.get('trailing_ratio','?')}/{p.get('tight_trailing_ratio','?')} "
            f"VB_k={p.get('vb_k','?')} VB_rng={p.get('vb_min_range_pct','?')}"
        )
        print(f"  {i+1:>2}. {r['ror']:>7.1f}% {r['sharpe']:>6.2f} {r['mdd']:>5.1f}% "
              f"{r['win_rate']:>5.1f}% {r['trades']:>5} {r['score']:>5.3f} | {params_str}")

    # 1등 상세 출력
    best = results[0]
    print(f"\n{'='*60}")
    print(f"🥇 최적 파라미터 상세")
    print(f"{'='*60}")
    bp = best['params']
    print(f"  TR 진입:")
    print(f"    BB 기간: {bp.get('tr_bb_period','?')} / std: {bp.get('tr_bb_std','?')}")
    print(f"    RSI: {bp.get('rsi_oversell','?')} ~ {bp.get('rsi_overbuy','?')}")
    print(f"    ADX ≥ {bp.get('adx_threshold','?')}")
    print(f"    ATR 배수: {bp.get('atr_multiplier','?')}")
    print(f"  청산:")
    print(f"    목표 ROR: {bp.get('target_ror_pct','?')}%")
    print(f"    트레일링: {bp.get('trailing_ratio','?')} / {bp.get('tight_trailing_ratio','?')}")
    print(f"  VB 진입:")
    print(f"    VB_K: {bp.get('vb_k','?')}")
    print(f"    VB_MIN_RANGE_PCT: {bp.get('vb_min_range_pct','?')}")
    print(f"  성과:")
    print(f"    ROR: {best['ror']:.2f}%")
    print(f"    Sharpe: {best['sharpe']:.2f}")
    print(f"    MDD: {best['mdd']:.1f}%")
    print(f"    거래: {best['trades']}회 (승률: {best['win_rate']:.1f}%)")
    print(f"    P/L 비: {best['pl_ratio']:.2f}")

    print(f"\n📋 coins/{coin_name}/strategy.py 에 적용할 파라미터:")
    print(f"    TR_BB_PERIOD = {bp.get('tr_bb_period','?')}")
    print(f"    TR_BB_STD = {bp.get('tr_bb_std','?')}")
    print(f"    RSI_OVERBUY = {bp.get('rsi_overbuy','?')}")
    print(f"    RSI_OVERSELL = {bp.get('rsi_oversell','?')}")
    print(f"    ADX_THRESHOLD = {bp.get('adx_threshold','?')}")
    print(f"    ATR_MULTIPLIER = {bp.get('atr_multiplier','?')}")
    print(f"    DEFAULT_TARGET_ROR = {bp.get('target_ror_pct','?')}")
    print(f"    TRAILING_RATIO = {bp.get('trailing_ratio','?')}")
    print(f"    TIGHT_TRAILING_RATIO = {bp.get('tight_trailing_ratio','?')}")
    print(f"    VB_K = {bp.get('vb_k','?')}")
    print(f"    VB_MIN_RANGE_PCT = {bp.get('vb_min_range_pct','?')}")

    return results


VB_TARGET_COINS = ['bnb', 'aave', 'avax', 'eth', 'link', 'sol', 'sui']

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='코인별 파라미터 최적화')
    parser.add_argument('--coin', required=True, help='코인 이름 또는 "vb_all" (VB 최적화 대상 전체)')
    parser.add_argument('--top', type=int, default=10, help='상위 N개 결과 출력')
    parser.add_argument('--cash', type=float, default=100000.0, help='초기 자본')
    args = parser.parse_args()

    if args.coin == 'vb_all':
        for coin in VB_TARGET_COINS:
            print(f"\n{'#'*60}")
            print(f"# {coin.upper()} 최적화 시작")
            print(f"{'#'*60}\n")
            optimize(coin, top_n=args.top, initial_cash=args.cash)
    else:
        optimize(args.coin, top_n=args.top, initial_cash=args.cash)
