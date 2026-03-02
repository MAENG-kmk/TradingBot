"""
Walk-Forward 검증기

과적합 여부를 확인하기 위해 Train 기간으로 파라미터를 최적화하고,
이후 Test 기간(미래 데이터)에서 실제 성과를 측정합니다.

사용법:
  python -m backtest.walk_forward --coin eth
  python -m backtest.walk_forward --coin btc --mode rolling
  python -m backtest.walk_forward --coin all
  python -m backtest.walk_forward --coin eth --train_years 2 --test_months 12

윈도우 구조 (anchored 기본값):
  Window 1: Train [2021-01 ~ 2022-12]  →  Test [2023-01 ~ 2023-12]
  Window 2: Train [2021-01 ~ 2023-12]  →  Test [2024-01 ~ 2024-12]
  Window 3: Train [2021-01 ~ 2024-12]  →  Test [2025-01 ~ 2025-12]

윈도우 구조 (rolling):
  Window 1: Train [2021-01 ~ 2022-12]  →  Test [2023-01 ~ 2023-12]
  Window 2: Train [2022-01 ~ 2023-12]  →  Test [2024-01 ~ 2024-12]
  Window 3: Train [2023-01 ~ 2024-12]  →  Test [2025-01 ~ 2025-12]
"""

import argparse
import os
import sys
import csv
import tempfile
import time
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

sys.path.append(os.path.abspath("."))

from backtest.optimizer import (
    run_single, generate_combinations, run_stage, score_result, PARAM_GRIDS
)
from backtest.runner import COIN_CONFIGS


def split_csv_by_date(src_path, start_date, end_date):
    """CSV에서 날짜 범위에 해당하는 행만 추출해 임시 파일로 반환"""
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='')
    writer = None
    count = 0

    with open(src_path, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        writer = csv.writer(tmp)
        writer.writerow(header)

        for row in reader:
            try:
                row_date = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                if start_date <= row_date < end_date:
                    writer.writerow(row)
                    count += 1
            except (ValueError, IndexError):
                continue

    tmp.close()
    return tmp.name, count


def get_date_range(csv_path):
    """CSV에서 첫/마지막 날짜 반환"""
    first = last = None
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        next(reader)  # 헤더
        for row in reader:
            try:
                d = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                if first is None:
                    first = d
                last = d
            except (ValueError, IndexError):
                continue
    return first, last


def build_windows(data_start, data_end, train_years, test_months, mode='anchored'):
    """
    윈도우 목록 생성
    mode: 'anchored' = 훈련 시작 고정, 'rolling' = 고정 크기 슬라이딩
    """
    windows = []
    test_delta = relativedelta(months=test_months)
    train_delta = relativedelta(years=train_years)

    if mode == 'anchored':
        anchor = data_start
        train_end = anchor + train_delta
        while train_end + test_delta <= data_end + relativedelta(days=1):
            test_end = train_end + test_delta
            windows.append({
                'train_start': anchor,
                'train_end': train_end,
                'test_start': train_end,
                'test_end': min(test_end, data_end + relativedelta(days=1)),
            })
            train_end = train_end + test_delta
    else:  # rolling
        train_start = data_start
        while True:
            train_end = train_start + train_delta
            test_end = train_end + test_delta
            if train_end >= data_end:
                break
            windows.append({
                'train_start': train_start,
                'train_end': train_end,
                'test_start': train_end,
                'test_end': min(test_end, data_end + relativedelta(days=1)),
            })
            train_start = train_start + test_delta

    return windows


def run_window(coin_name, data_path, window, initial_cash=100000.0, top_n=3, robust=True, robust_periods=4):
    """단일 윈도우: Train 최적화(robust or classic) → Test 검증"""
    grid = PARAM_GRIDS.get(coin_name, PARAM_GRIDS['default'])
    stage1_combos = generate_combinations(grid['stage1'])
    stage2_combos = generate_combinations(grid['stage2'])

    train_file, train_rows = split_csv_by_date(
        data_path, window['train_start'], window['train_end'])
    test_file, test_rows = split_csv_by_date(
        data_path, window['test_start'], window['test_end'])

    try:
        if train_rows < 200 or test_rows < 50:
            return None

        if robust:
            # Robust: Train 기간을 n등분 후 모든 구간에서 안정적인 파라미터 선택
            from backtest.robust_optimizer import split_into_periods, run_robust_stage, normalize_and_score

            # train_file을 n_periods로 분할
            train_periods = split_into_periods(train_file, robust_periods)
            if len(train_periods) < 2:
                # 기간이 부족하면 classic으로 폴백
                robust = False
            else:
                s1_results = run_robust_stage(
                    train_periods, stage1_combos, {}, "S1-train", initial_cash, min_trades=3)
                if not s1_results:
                    return None
                normalize_and_score(s1_results)
                s1_results.sort(key=lambda x: x['robust_score'], reverse=True)

                top_entries = []
                for r in s1_results[:top_n]:
                    ep = {k: v for k, v in r['params'].items() if k in grid['stage1']}
                    top_entries.append(ep)

                all_s2 = []
                for i, ep in enumerate(top_entries):
                    s2 = run_robust_stage(
                        train_periods, stage2_combos, ep, f"S2-train-{i+1}", initial_cash, min_trades=3)
                    all_s2.extend(s2)

                for p in train_periods:
                    try:
                        os.unlink(p['path'])
                    except Exception:
                        pass

                if not all_s2:
                    return None
                normalize_and_score(all_s2)
                all_s2.sort(key=lambda x: x['robust_score'], reverse=True)

                best_params = all_s2[0]['params']
                train_avg_ror = all_s2[0]['stats']['avg_ror']
                train_min_ror = all_s2[0]['stats']['min_ror']

                test_result = run_single(test_file, best_params, initial_cash)
                test_ror = test_result['ror'] if test_result else None
                test_sharpe = test_result['sharpe'] if test_result else None
                test_mdd = test_result['mdd'] if test_result else None
                test_trades = test_result['trades'] if test_result else 0
                test_winrate = test_result['win_rate'] if test_result else None

                return {
                    'train_start': window['train_start'].strftime('%Y-%m'),
                    'train_end': window['train_end'].strftime('%Y-%m'),
                    'test_start': window['test_start'].strftime('%Y-%m'),
                    'test_end': window['test_end'].strftime('%Y-%m'),
                    'best_params': best_params,
                    'train': {
                        'ror': train_avg_ror,
                        'sharpe': None,
                        'mdd': None,
                        'trades': all_s2[0]['period_trades'][0] if all_s2[0]['period_trades'] else 0,
                        'win_rate': None,
                        'min_ror': train_min_ror,
                    },
                    'test': {
                        'ror': test_ror, 'sharpe': test_sharpe, 'mdd': test_mdd,
                        'trades': test_trades, 'win_rate': test_winrate,
                    },
                    'efficiency': (test_ror / train_avg_ror)
                        if (train_avg_ror and train_avg_ror > 0 and test_ror is not None) else None,
                }

        # Classic 방식
        s1_results = run_stage(train_file, stage1_combos, {}, "S1-train", initial_cash)
        if not s1_results:
            return None

        for r in s1_results:
            r['score'] = score_result(r, s1_results)
        s1_results.sort(key=lambda x: x['score'], reverse=True)

        top_entries = []
        for r in s1_results[:top_n]:
            ep = {k: v for k, v in r['params'].items() if k in grid['stage1']}
            top_entries.append(ep)

        all_s2 = []
        for i, ep in enumerate(top_entries):
            s2 = run_stage(train_file, stage2_combos, ep, f"S2-train-{i+1}", initial_cash)
            all_s2.extend(s2)

        if not all_s2:
            return None

        for r in all_s2:
            r['score'] = score_result(r, all_s2)
        all_s2.sort(key=lambda x: x['score'], reverse=True)

        best_params = all_s2[0]['params']
        train_ror = all_s2[0]['ror']
        train_sharpe = all_s2[0]['sharpe']
        train_mdd = all_s2[0]['mdd']
        train_trades = all_s2[0]['trades']
        train_winrate = all_s2[0]['win_rate']

        # Test: 최적 파라미터로 검증
        test_result = run_single(test_file, best_params, initial_cash)

        test_ror = test_result['ror'] if test_result else None
        test_sharpe = test_result['sharpe'] if test_result else None
        test_mdd = test_result['mdd'] if test_result else None
        test_trades = test_result['trades'] if test_result else 0
        test_winrate = test_result['win_rate'] if test_result else None

        return {
            'train_start': window['train_start'].strftime('%Y-%m'),
            'train_end': window['train_end'].strftime('%Y-%m'),
            'test_start': window['test_start'].strftime('%Y-%m'),
            'test_end': window['test_end'].strftime('%Y-%m'),
            'best_params': best_params,
            'train': {
                'ror': train_ror, 'sharpe': train_sharpe, 'mdd': train_mdd,
                'trades': train_trades, 'win_rate': train_winrate,
            },
            'test': {
                'ror': test_ror, 'sharpe': test_sharpe, 'mdd': test_mdd,
                'trades': test_trades, 'win_rate': test_winrate,
            },
            # 효율 비율: Test ROR / Train ROR (1에 가까울수록 과적합 없음)
            'efficiency': (test_ror / train_ror) if (train_ror and train_ror > 0 and test_ror is not None) else None,
        }
    finally:
        os.unlink(train_file)
        os.unlink(test_file)


def walk_forward(coin_name, mode='anchored', train_years=2, test_months=12,
                 initial_cash=100000.0, robust=True, robust_periods=4):
    config = COIN_CONFIGS.get(coin_name)
    if not config:
        print(f"❌ 지원하지 않는 코인: {coin_name}")
        return

    data_path = config['data_file']
    if not os.path.exists(data_path):
        print(f"❌ 데이터 파일 없음: {data_path}")
        return

    data_start, data_end = get_date_range(data_path)
    windows = build_windows(data_start, data_end, train_years, test_months, mode)

    if not windows:
        print(f"❌ 윈도우 생성 실패 (데이터 기간: {data_start.strftime('%Y-%m')} ~ {data_end.strftime('%Y-%m')})")
        return

    opt_mode = "Robust" if robust else "Classic"
    print(f"\n{'='*80}")
    print(f"🔄 Walk-Forward 검증: {coin_name.upper()} ({mode} mode, {opt_mode} 최적화)")
    print(f"   데이터 기간: {data_start.strftime('%Y-%m')} ~ {data_end.strftime('%Y-%m')}")
    print(f"   Train: {train_years}년 | Test: {test_months}개월 | 윈도우: {len(windows)}개")
    if robust:
        print(f"   Train 내부 분할: {robust_periods}개 구간 (안정성 기반 최적화)")
    print(f"{'='*80}\n")

    window_results = []
    for i, window in enumerate(windows):
        print(f"━━━ Window {i+1}/{len(windows)}: "
              f"Train [{window['train_start'].strftime('%Y-%m')} ~ {window['train_end'].strftime('%Y-%m')}] "
              f"→ Test [{window['test_start'].strftime('%Y-%m')} ~ {window['test_end'].strftime('%Y-%m')}] ━━━")
        t_start = time.time()

        result = run_window(coin_name, data_path, window, initial_cash,
                            robust=robust, robust_periods=robust_periods)
        elapsed = time.time() - t_start

        if result:
            window_results.append(result)
            eff = f"{result['efficiency']*100:.1f}%" if result['efficiency'] is not None else "N/A"
            test_ror = f"{result['test']['ror']:.1f}%" if result['test']['ror'] is not None else "No trade"
            train_label = f"{result['train']['ror']:.1f}% (avg)" if robust else f"{result['train']['ror']:.1f}%"
            print(f"   ✅ Train ROR: {train_label}  |  "
                  f"Test ROR: {test_ror}  |  "
                  f"효율: {eff}  ({elapsed:.0f}s)\n")
        else:
            print(f"   ⚠️  결과 없음 (데이터 부족 또는 거래 없음)\n")

    if not window_results:
        print("❌ 유효한 윈도우 결과 없음")
        return

    _print_summary(coin_name, window_results)
    return window_results


def _print_summary(coin_name, results):
    """Walk-Forward 요약 출력"""
    print(f"\n{'='*90}")
    print(f"📊 {coin_name.upper()} Walk-Forward 요약")
    print(f"{'='*90}")
    print(f"{'윈도우':<28} {'Train ROR':>10} {'Test ROR':>10} {'Test Sharpe':>11} "
          f"{'Test MDD':>9} {'Test 거래':>9} {'효율':>7}")
    print(f"{'-'*90}")

    efficiencies = []
    test_rors = []

    for r in results:
        w_label = f"Train~{r['train_end']} / Test {r['test_start']}~{r['test_end']}"
        train_ror_s = f"{r['train']['ror']:.1f}%"
        test_ror_v = r['test']['ror']
        test_ror_s = f"{test_ror_v:.1f}%" if test_ror_v is not None else "N/A"
        test_sharpe_s = f"{r['test']['sharpe']:.2f}" if r['test']['sharpe'] is not None else "N/A"
        test_mdd_s = f"{r['test']['mdd']:.1f}%" if r['test']['mdd'] is not None else "N/A"
        test_trades_s = str(r['test']['trades'])
        eff_s = f"{r['efficiency']*100:.1f}%" if r['efficiency'] is not None else "N/A"

        if r['efficiency'] is not None:
            efficiencies.append(r['efficiency'])
        if test_ror_v is not None:
            test_rors.append(test_ror_v)

        print(f"{w_label:<28} {train_ror_s:>10} {test_ror_s:>10} {test_sharpe_s:>11} "
              f"{test_mdd_s:>9} {test_trades_s:>9} {eff_s:>7}")

    print(f"{'-'*90}")

    avg_eff = sum(efficiencies) / len(efficiencies) if efficiencies else None
    avg_test_ror = sum(test_rors) / len(test_rors) if test_rors else None
    pos_windows = sum(1 for r in test_rors if r > 0)

    print(f"\n{'─'*50}")
    print(f"📈 평균 Test ROR    : {avg_test_ror:.1f}%" if avg_test_ror is not None else "평균 Test ROR: N/A")
    print(f"⚖️  평균 효율 비율  : {avg_eff*100:.1f}%" if avg_eff is not None else "평균 효율 비율: N/A")
    print(f"✅ 수익 윈도우     : {pos_windows}/{len(test_rors)}개")

    if avg_eff is not None:
        if avg_eff >= 0.5:
            verdict = "🟢 양호 (과적합 낮음) — Test 성과가 Train의 50% 이상 유지"
        elif avg_eff >= 0.2:
            verdict = "🟡 주의 (과적합 가능성) — Test 성과가 Train보다 크게 낮음"
        else:
            verdict = "🔴 위험 (과적합 높음) — Test에서 전략이 거의 작동 안 함"
        print(f"\n{verdict}")

    # 파라미터 안정성 분석
    print(f"\n{'─'*50}")
    print(f"🔩 파라미터 안정성 (윈도우별 최적 파라미터)")
    ema_shorts = [r['best_params']['ema_short'] for r in results]
    ema_longs  = [r['best_params']['ema_long']  for r in results]
    adx_thrs   = [r['best_params']['adx_threshold'] for r in results]
    atrs       = [r['best_params']['atr_multiplier'] for r in results]
    for i, r in enumerate(results):
        p = r['best_params']
        print(f"  Window {i+1}: EMA={p['ema_short']}/{p['ema_long']} "
              f"ADX≥{p['adx_threshold']} ATR×{p['atr_multiplier']} "
              f"Target={p['target_ror_pct']}% Trail={p['trailing_ratio']}/{p['tight_trailing_ratio']}")

    if len(set(ema_shorts)) == 1 and len(set(ema_longs)) == 1:
        print(f"\n  → EMA 파라미터 일관됨 ({ema_shorts[0]}/{ema_longs[0]}) ✅")
    else:
        print(f"\n  → EMA 파라미터 불일치 ⚠️  (윈도우마다 달라짐 = 불안정)")


if __name__ == '__main__':
    try:
        from dateutil.relativedelta import relativedelta
    except ImportError:
        print("python-dateutil 설치 필요: pip install python-dateutil")
        sys.exit(1)

    parser = argparse.ArgumentParser(description='Walk-Forward 검증')
    parser.add_argument('--coin', required=True, help='코인 이름 또는 all')
    parser.add_argument('--mode', default='anchored', choices=['anchored', 'rolling'],
                        help='anchored: 훈련 시작 고정 | rolling: 슬라이딩 윈도우')
    parser.add_argument('--train_years', type=int, default=2, help='훈련 기간 (년)')
    parser.add_argument('--test_months', type=int, default=12, help='테스트 기간 (개월)')
    parser.add_argument('--cash', type=float, default=100000.0, help='초기 자본')
    parser.add_argument('--no-robust', action='store_true', help='Robust 최적화 비활성화 (classic 방식)')
    parser.add_argument('--robust_periods', type=int, default=4, help='Train 내부 분할 구간 수 (기본 4)')
    args = parser.parse_args()

    coins = list(COIN_CONFIGS.keys()) if args.coin == 'all' else [args.coin]
    for coin in coins:
        walk_forward(coin, args.mode, args.train_years, args.test_months,
                     args.cash, robust=not args.no_robust, robust_periods=args.robust_periods)
