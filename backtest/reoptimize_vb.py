"""
VB_K=0.1 코인들 Stage 3 단독 재최적화
Stage 1+2 최적 파라미터를 고정하고 VB_K [0.2~0.6] 범위만 탐색
"""
import sys
import os
sys.path.append(os.path.abspath("."))

from backtest.optimizer import run_stage, generate_combinations, score_result, PARAM_GRIDS
from backtest.runner import COIN_CONFIGS, _load_intrabar

# Stage 1+2에서 확인된 최적 TR+청산 파라미터
BEST_PARAMS = {
    'bnb': dict(
        tr_bb_period=25, tr_bb_std=2.0,
        rsi_overbuy=80, rsi_oversell=30,
        adx_threshold=15, atr_multiplier=3.0,
        target_ror_pct=7.0, trailing_ratio=0.5, tight_trailing_ratio=0.85,
    ),
    'avax': dict(
        tr_bb_period=15, tr_bb_std=1.5,
        rsi_overbuy=80, rsi_oversell=20,
        adx_threshold=15, atr_multiplier=1.5,
        target_ror_pct=10.0, trailing_ratio=0.6, tight_trailing_ratio=0.85,
    ),
    'eth': dict(
        tr_bb_period=25, tr_bb_std=1.5,
        rsi_overbuy=80, rsi_oversell=20,
        adx_threshold=15, atr_multiplier=2.0,
        target_ror_pct=15.0, trailing_ratio=0.4, tight_trailing_ratio=0.65,
    ),
    'link': dict(
        tr_bb_period=20, tr_bb_std=2.5,
        rsi_overbuy=80, rsi_oversell=30,
        adx_threshold=15, atr_multiplier=1.5,
        target_ror_pct=15.0, trailing_ratio=0.4, tight_trailing_ratio=0.65,
    ),
}

VB_GRID = PARAM_GRIDS['default']['stage3']

INITIAL_CASH = 100_000.0

for coin, base_params in BEST_PARAMS.items():
    print(f"\n{'#'*60}")
    print(f"# {coin.upper()} — VB Stage 3 재최적화 (VB_K ≥ 0.2)")
    print(f"{'#'*60}")

    config = COIN_CONFIGS[coin]
    data_path = config['data_file']
    intrabar_df = _load_intrabar(coin)
    combos = generate_combinations(VB_GRID)

    print(f"   VB 조합: {len(combos)}개  |  1h 데이터: {'있음' if intrabar_df is not None else '없음'}\n")

    results = run_stage(data_path, combos, base_params, "S3", INITIAL_CASH,
                        intrabar_df=intrabar_df, slippage_pct=config['slippage_pct'])

    if not results:
        print(f"  ❌ {coin.upper()} 유효 결과 없음")
        continue

    for r in results:
        r['score'] = score_result(r, results)
    results.sort(key=lambda x: x['score'], reverse=True)

    print(f"\n{'='*100}")
    print(f"🏆 {coin.upper()} 상위 5개")
    print(f"{'순위':>4} {'ROR':>8} {'샤프':>6} {'MDD':>6} {'승률':>6} {'거래':>5} {'점수':>6} | VB 파라미터")
    print(f"{'-'*100}")
    for i, r in enumerate(results[:5]):
        p = r['params']
        print(f"  {i+1:>2}. {r['ror']:>7.1f}% {r['sharpe']:>6.2f} {r['mdd']:>5.1f}% "
              f"{r['win_rate']:>5.1f}% {r['trades']:>5} {r['score']:>5.3f} | "
              f"VB_k={p.get('vb_k')} VB_rng={p.get('vb_min_range_pct')}")

    best = results[0]
    bp = best['params']
    print(f"\n  🥇 최적: VB_K={bp['vb_k']}  VB_MIN_RANGE_PCT={bp['vb_min_range_pct']}")
    print(f"     ROR={best['ror']:.1f}%  Sharpe={best['sharpe']:.2f}  MDD={best['mdd']:.1f}%")
    print(f"\n  📋 coins/{coin}/strategy.py 적용:")
    print(f"     VB_K = {bp['vb_k']}")
    print(f"     VB_MIN_RANGE_PCT = {bp['vb_min_range_pct']}")
