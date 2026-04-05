"""
Robust 파라미터 옵티마이저

전체 기간 최고 ROR 대신, 여러 기간에서 안정적으로 수익을 내는
파라미터를 탐색합니다.

스코어링:
  - avg_ror    : 기간별 평균 ROR (높을수록 좋음)
  - min_ror    : 기간별 최솟값 (음수면 크게 감점)
  - std_ror    : 기간별 표준편차 (낮을수록 안정적)
  - loss_count : 손실 기간 수 (적을수록 좋음)

사용법:
  python -m backtest.robust_optimizer --coin doge
  python -m backtest.robust_optimizer --coin doge --periods 4 --top 10
"""

import argparse
import os
import sys
import csv
import tempfile
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta

sys.path.append(os.path.abspath("."))

from backtest.optimizer import (
    run_single, generate_combinations, PARAM_GRIDS
)
from backtest.runner import COIN_CONFIGS


def split_into_periods(csv_path, n_periods):
    """CSV를 n개의 균등 기간으로 분할, 각 기간 임시 파일 경로 반환"""
    rows = []
    header = None
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            try:
                datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                rows.append(row)
            except (ValueError, IndexError):
                continue

    if not rows:
        return []

    period_size = len(rows) // n_periods
    periods = []

    for i in range(n_periods):
        start_idx = i * period_size
        end_idx = start_idx + period_size if i < n_periods - 1 else len(rows)
        period_rows = rows[start_idx:end_idx]

        if len(period_rows) < 100:
            continue

        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.csv', delete=False, newline='')
        writer = csv.writer(tmp)
        writer.writerow(header)
        writer.writerows(period_rows)
        tmp.close()

        start_date = period_rows[0][0][:7]
        end_date = period_rows[-1][0][:7]
        periods.append({
            'path': tmp.name,
            'label': f"{start_date}~{end_date}",
            'rows': len(period_rows),
        })

    return periods


def robust_score(period_rors):
    """
    기간별 ROR 리스트로 robust 점수 계산.
    avg_ror * 0.4 + min_ror * 0.3 - std_penalty * 0.2 - loss_penalty * 0.1
    """
    if not period_rors:
        return -999

    n = len(period_rors)
    avg_ror = sum(period_rors) / n
    min_ror = min(period_rors)
    loss_count = sum(1 for r in period_rors if r < 0)

    # 표준편차
    variance = sum((r - avg_ror) ** 2 for r in period_rors) / n
    std_ror = variance ** 0.5

    # 각 항목 정규화는 배치 단위로 하므로 여기서는 raw값 반환
    return {
        'avg_ror': avg_ror,
        'min_ror': min_ror,
        'std_ror': std_ror,
        'loss_count': loss_count,
    }


def normalize_and_score(results_list):
    """전체 결과에서 정규화 후 최종 점수 계산"""
    if not results_list:
        return

    avg_rors = [r['stats']['avg_ror'] for r in results_list]
    min_rors = [r['stats']['min_ror'] for r in results_list]
    std_rors = [r['stats']['std_ror'] for r in results_list]

    def norm(val, vals):
        mn, mx = min(vals), max(vals)
        return (val - mn) / (mx - mn) if mx != mn else 0.5

    for r in results_list:
        s = r['stats']
        score = (
            norm(s['avg_ror'], avg_rors) * 0.4 +
            norm(s['min_ror'], min_rors) * 0.3 +
            (1 - norm(s['std_ror'], std_rors)) * 0.2 +
            ((4 - s['loss_count']) / 4) * 0.1
        )
        r['robust_score'] = score


def run_robust_stage(periods, combos, base_params, stage_name, initial_cash, min_trades=5):
    """모든 기간에 대해 Grid Search 실행, robust 점수로 결과 반환"""
    total = len(combos)
    results = []
    start = time.time()

    for i, params in enumerate(combos):
        merged = {**base_params, **params}
        period_rors = []
        period_trades = []
        valid = True

        for period in periods:
            r = run_single(period['path'], merged, initial_cash)
            if r is None or r['trades'] < min_trades:
                valid = False
                break
            period_rors.append(r['ror'])
            period_trades.append(r['trades'])

        if valid and len(period_rors) == len(periods):
            stats = robust_score(period_rors)
            results.append({
                'params': merged.copy(),
                'period_rors': period_rors,
                'period_trades': period_trades,
                'stats': stats,
            })

        if (i + 1) % 50 == 0 or (i + 1) == total:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 1
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(f"   [{stage_name}] {i+1}/{total} ({(i+1)/total*100:.1f}%) "
                  f"| 유효: {len(results)} | ETA: {eta:.0f}s", flush=True)

    elapsed = time.time() - start
    print(f"   [{stage_name}] 완료: {len(results)}개 유효 / {total}개 ({elapsed:.1f}초)\n")
    return results


def robust_optimize(coin_name, n_periods=5, top_n=10, initial_cash=100000.0):
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

    # 데이터 기간 분할
    periods = split_into_periods(data_path, n_periods)
    if len(periods) < 2:
        print("❌ 기간 분할 실패")
        return

    print(f"\n{'='*80}")
    print(f"🛡️  {coin_name.upper()} Robust 파라미터 최적화")
    print(f"   기간 분할: {n_periods}개")
    for i, p in enumerate(periods):
        print(f"   Period {i+1}: {p['label']} ({p['rows']} rows)")
    print(f"   Stage 1 조합: {len(stage1_combos)}")
    print(f"   Stage 2 조합: {len(stage2_combos)}")
    print(f"{'='*80}\n")

    try:
        # Stage 1: 진입 파라미터 Robust 탐색
        print("━━━ Stage 1: 진입 파라미터 Robust 탐색 ━━━")
        s1_results = run_robust_stage(
            periods, stage1_combos, {}, "S1", initial_cash)

        if not s1_results:
            print("❌ Stage 1 유효 결과 없음")
            return

        normalize_and_score(s1_results)
        s1_results.sort(key=lambda x: x['robust_score'], reverse=True)

        print(f"Stage 1 상위 3개 진입 파라미터 (Robust 기준):")
        for i, r in enumerate(s1_results[:3]):
            p = r['params']
            rors_str = " / ".join(f"{v:.1f}%" for v in r['period_rors'])
            print(f"   {i+1}. BB={p.get('tr_bb_period','?')}×{p.get('tr_bb_std','?')} "
                  f"RSI={p.get('rsi_oversell','?')}/{p.get('rsi_overbuy','?')} "
                  f"ADX≥{p.get('adx_threshold','?')} ATR×{p.get('atr_multiplier','?')}")
            print(f"      기간별 ROR: [{rors_str}]  "
                  f"avg={r['stats']['avg_ror']:.1f}%  "
                  f"min={r['stats']['min_ror']:.1f}%  "
                  f"std={r['stats']['std_ror']:.1f}\n")

        # Stage 2: 청산 파라미터 Robust 탐색
        print("━━━ Stage 2: 청산 파라미터 Robust 탐색 ━━━")
        top_entries = []
        for r in s1_results[:3]:
            ep = {k: v for k, v in r['params'].items() if k in grid['stage1']}
            top_entries.append(ep)

        all_s2 = []
        for i, ep in enumerate(top_entries):
            s2 = run_robust_stage(
                periods, stage2_combos, ep, f"S2-{i+1}", initial_cash)
            all_s2.extend(s2)

        if not all_s2:
            print("❌ Stage 2 유효 결과 없음")
            return

        normalize_and_score(all_s2)
        all_s2.sort(key=lambda x: x['robust_score'], reverse=True)

        # 결과 출력
        print(f"\n{'='*100}")
        print(f"🏆 {coin_name.upper()} Robust 최적화 결과 (상위 {min(top_n, len(all_s2))}개)")
        print(f"{'='*100}")

        period_headers = "  ".join(f"P{i+1}({p['label']})" for i, p in enumerate(periods))
        print(f"{'순위':>3} {'avg':>7} {'min':>7} {'std':>6} {'손실기간':>6} {'점수':>6} | 파라미터")
        print(f"     {period_headers}")
        print(f"{'-'*100}")

        for idx, r in enumerate(all_s2[:top_n]):
            p = r['params']
            s = r['stats']
            params_str = (
                f"BB={p.get('tr_bb_period','?')}x{p.get('tr_bb_std','?')} "
                f"RSI={p.get('rsi_oversell','?')}/{p.get('rsi_overbuy','?')} "
                f"ADX>={p.get('adx_threshold','?')} ATR*{p.get('atr_multiplier','?')} "
                f"목표={p.get('target_ror_pct','?')}% "
                f"Trail={p.get('trailing_ratio','?')}/{p.get('tight_trailing_ratio','?')}"
            )
            rors_str = "  ".join(f"{v:>+7.1f}%" for v in r['period_rors'])
            print(f"{idx+1:>3}. {s['avg_ror']:>6.1f}% {s['min_ror']:>6.1f}% "
                  f"{s['std_ror']:>5.1f} {s['loss_count']:>6} {r['robust_score']:>6.3f} | {params_str}")
            print(f"     {rors_str}")
            print()

        # 1등 상세
        best = all_s2[0]
        bp = best['params']
        bs = best['stats']
        print(f"\n{'='*60}")
        print(f"Robust 최적 파라미터")
        print(f"{'='*60}")
        print(f"  진입:")
        print(f"    BB: {bp.get('tr_bb_period','?')} / std: {bp.get('tr_bb_std','?')}")
        print(f"    RSI: {bp.get('rsi_oversell','?')} ~ {bp.get('rsi_overbuy','?')}")
        print(f"    ADX >= {bp.get('adx_threshold','?')}")
        print(f"    ATR 배수: {bp.get('atr_multiplier','?')}")
        print(f"  청산:")
        print(f"    목표 ROR: {bp['target_ror_pct']}%")
        print(f"    트레일링: {bp['trailing_ratio']} / {bp['tight_trailing_ratio']}")
        print(f"  Robust 성과:")
        print(f"    기간별 ROR: {' / '.join(f'{v:+.1f}%' for v in best['period_rors'])}")
        print(f"    평균 ROR:   {bs['avg_ror']:+.2f}%")
        print(f"    최소 ROR:   {bs['min_ror']:+.2f}%")
        print(f"    표준편차:   {bs['std_ror']:.2f}")
        print(f"    손실 기간:  {bs['loss_count']}/{n_periods}")

        # 기존 최적화(전체 기간)와 비교
        print(f"\n{'─'*60}")
        print(f"📊 기존 전체기간 파라미터와 비교:")
        old_params = config['params'].copy()
        old_rors = []
        for period in periods:
            r = run_single(period['path'], old_params, initial_cash)
            old_rors.append(r['ror'] if r else 0)
        print(f"  기존 파라미터 기간별 ROR: {' / '.join(f'{v:+.1f}%' for v in old_rors)}")
        old_avg = sum(old_rors) / len(old_rors)
        old_min = min(old_rors)
        print(f"  평균: {old_avg:+.2f}%  최소: {old_min:+.2f}%")
        print(f"\n  Robust 파라미터 평균: {bs['avg_ror']:+.2f}%  최소: {bs['min_ror']:+.2f}%")

        print(f"\ncoins/{coin_name}/strategy.py 에 적용할 파라미터:")
        print(f"    TR_BB_PERIOD = {bp.get('tr_bb_period','?')}")
        print(f"    TR_BB_STD = {bp.get('tr_bb_std','?')}")
        print(f"    RSI_OVERBUY = {bp.get('rsi_overbuy','?')}")
        print(f"    RSI_OVERSELL = {bp.get('rsi_oversell','?')}")
        print(f"    ADX_THRESHOLD = {bp.get('adx_threshold','?')}")
        print(f"    ATR_MULTIPLIER = {bp.get('atr_multiplier','?')}")
        print(f"    DEFAULT_TARGET_ROR = {bp.get('target_ror_pct','?')}")
        print(f"    TRAILING_RATIO = {bp.get('trailing_ratio','?')}")
        print(f"    TIGHT_TRAILING_RATIO = {bp.get('tight_trailing_ratio','?')}")

        return all_s2

    finally:
        for p in periods:
            try:
                os.unlink(p['path'])
            except Exception:
                pass


if __name__ == '__main__':
    try:
        from dateutil.relativedelta import relativedelta
    except ImportError:
        print("python-dateutil 설치 필요: pip install python-dateutil")
        sys.exit(1)

    parser = argparse.ArgumentParser(description='Robust 파라미터 최적화')
    parser.add_argument('--coin', required=True, help='코인 이름')
    parser.add_argument('--periods', type=int, default=5, help='기간 분할 수 (기본 5)')
    parser.add_argument('--top', type=int, default=10, help='상위 N개 출력')
    parser.add_argument('--cash', type=float, default=100000.0, help='초기 자본')
    args = parser.parse_args()

    robust_optimize(args.coin, n_periods=args.periods, top_n=args.top, initial_cash=args.cash)
