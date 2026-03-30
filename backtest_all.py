"""
전체 코인 백테스트 — 10개 코인 일괄 실행 후 결과 비교
2020-12-31 ~ 2026-02-28 (2022 하락장 포함)
"""
import backtrader as bt
import pandas as pd
import os

from backtestStrategy.OptimizedStrategy import OptimizedStrategy
from backtestStrategy.LiveStrategy import LiveStrategy

# ===== 설정 =====
STRATEGY     = LiveStrategy   # OptimizedStrategy | LiveStrategy
INITIAL_CASH = 10_000.0       # 코인당 자본 ($10,000)
COMMISSION   = 0.0004         # Binance 선물 수수료 0.04%
DATA_DIR     = 'backtestDatas'

# 코인별 파라미터 (coins/*/strategy.py 설정과 동일하게 반영)
COIN_CONFIGS = {
    'btcusdt_4h':  dict(mr_enabled=False),
    'ethusdt_4h':  dict(mr_enabled=True,  mr_ou_entry_z=2.0, mr_max_halflife=12, mr_time_halflife_mult=2.5),
    'solusdt_4h':  dict(mr_enabled=True,  mr_ou_entry_z=2.0, mr_max_halflife=10, mr_time_halflife_mult=2.5),
    'bnbusdt_4h':  dict(mr_enabled=True,  mr_ou_entry_z=2.0, mr_max_halflife=12, mr_time_halflife_mult=2.5),
    'xrpusdt_4h':  dict(mr_enabled=False),
    'linkusdt_4h': dict(mr_enabled=False),
    'dogeusdt_4h': dict(mr_enabled=False),
    'avaxusdt_4h': dict(mr_enabled=True,  mr_ou_entry_z=1.8, mr_max_halflife=12, mr_time_halflife_mult=2.5),
    'arbusdt_4h':  dict(mr_enabled=True,  mr_ou_entry_z=2.0, mr_max_halflife=12, mr_time_halflife_mult=2.5),
    'aaveusdt_4h': dict(mr_enabled=True,  mr_ou_entry_z=2.0, mr_max_halflife=10, mr_time_halflife_mult=2.0),
}

COINS = list(COIN_CONFIGS.keys())

# 하락장 구간 분리 분석
BEAR_START = '2022-01-01'
BEAR_END   = '2022-12-31'


def run_backtest(coin_name, from_date=None, to_date=None):
    cerebro = bt.Cerebro()
    cfg = COIN_CONFIGS.get(coin_name, {})
    cerebro.addstrategy(STRATEGY, **cfg)
    cerebro.broker.setcash(INITIAL_CASH)
    cerebro.broker.setcommission(commission=COMMISSION)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown,    _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    csv_path = os.path.join(DATA_DIR, coin_name + '.csv')
    data = bt.feeds.GenericCSVData(
        dataname=csv_path,
        dtformat='%Y-%m-%d %H:%M:%S',
        timeframe=bt.TimeFrame.Minutes,
        compression=240,
        openinterest=-1,
        headers=True,
        fromdate=pd.Timestamp(from_date) if from_date else None,
        todate=pd.Timestamp(to_date)     if to_date   else None,
    )
    cerebro.adddata(data)

    result = cerebro.run()
    strat  = result[0]

    final  = cerebro.broker.getvalue()
    ror    = (final - INITIAL_CASH) / INITIAL_CASH * 100

    ta = strat.analyzers.trades.get_analysis()
    total = ta.get('total', {}).get('total', 0)
    won   = ta.get('won',   {}).get('total', 0)
    lost  = ta.get('lost',  {}).get('total', 0)

    avg_profit = ta.get('won',  {}).get('pnl', {}).get('average', 0) or 0
    avg_loss   = ta.get('lost', {}).get('pnl', {}).get('average', 0) or 0

    winrate = (won / total * 100) if total > 0 else 0
    rr      = abs(avg_profit / avg_loss) if avg_loss != 0 else 0

    sharpe_raw = strat.analyzers.sharpe.get_analysis().get('sharperatio')
    sharpe = round(sharpe_raw, 2) if sharpe_raw else 0.0

    dd_raw = strat.analyzers.drawdown.get_analysis()
    mdd    = dd_raw.get('max', {}).get('drawdown', 0)

    return {
        'coin':       coin_name.replace('usdt_4h', '').upper(),
        'ror':        round(ror, 1),
        'final':      round(final, 0),
        'total':      total,
        'won':        won,
        'lost':       lost,
        'winrate':    round(winrate, 1),
        'rr':         round(rr, 2),
        'sharpe':     sharpe,
        'mdd':        round(mdd, 1),
    }


def print_table(title, rows):
    print(f'\n{"="*80}')
    print(f'  {title}')
    print(f'{"="*80}')
    header = f"{'코인':<6} {'수익률':>8} {'최종잔고':>10} {'거래수':>6} {'승':>5} {'패':>5} {'승률':>7} {'손익비':>7} {'샤프':>7} {'MDD':>7}"
    print(header)
    print('-' * 80)

    total_ror = 0
    for r in rows:
        ror_str = f"{r['ror']:+.1f}%"
        row = (
            f"{r['coin']:<6} {ror_str:>8} {r['final']:>10,.0f} "
            f"{r['total']:>6} {r['won']:>5} {r['lost']:>5} "
            f"{r['winrate']:>6.1f}% {r['rr']:>7.2f} {r['sharpe']:>7.2f} {r['mdd']:>6.1f}%"
        )
        print(row)
        total_ror += r['ror']

    print('-' * 80)

    valid = [r for r in rows if r['total'] > 0]
    if valid:
        avg_ror     = sum(r['ror']     for r in valid) / len(valid)
        avg_wr      = sum(r['winrate'] for r in valid) / len(valid)
        avg_rr      = sum(r['rr']      for r in valid) / len(valid)
        avg_sharpe  = sum(r['sharpe']  for r in valid) / len(valid)
        avg_mdd     = sum(r['mdd']     for r in valid) / len(valid)
        print(
            f"{'평균':<6} {avg_ror:>+7.1f}% {'':>10} {'':>6} {'':>5} {'':>5} "
            f"{avg_wr:>6.1f}% {avg_rr:>7.2f} {avg_sharpe:>7.2f} {avg_mdd:>6.1f}%"
        )

    pos = sum(1 for r in rows if r['ror'] > 0)
    neg = sum(1 for r in rows if r['ror'] <= 0)
    print(f'\n  수익 코인: {pos}개  |  손실 코인: {neg}개  |  전체: {len(rows)}개')


def main():
    strategy_name = STRATEGY.__name__
    print(f'\n백테스트 시작 — {strategy_name}')
    print(f'초기 자본: ${INITIAL_CASH:,.0f} / 코인  |  수수료: {COMMISSION*100:.2f}%\n')

    # ── 전체 기간 (2021~2026) ──
    print('[전체 기간 실행 중...]')
    all_results = []
    for coin in COINS:
        try:
            r = run_backtest(coin)
            all_results.append(r)
            print(f'  {r["coin"]:<6} 완료  →  {r["ror"]:+.1f}%  (거래:{r["total"]}회, MDD:{r["mdd"]:.1f}%)')
        except Exception as e:
            print(f'  {coin} 오류: {e}')

    print_table('전체 기간 (2021-01 ~ 2026-02)', all_results)

    # ── 하락장 (2022) ──
    print('\n[하락장 구간 (2022) 실행 중...]')
    bear_results = []
    for coin in COINS:
        try:
            r = run_backtest(coin, from_date=BEAR_START, to_date=BEAR_END)
            bear_results.append(r)
            print(f'  {r["coin"]:<6} 완료  →  {r["ror"]:+.1f}%  (거래:{r["total"]}회)')
        except Exception as e:
            print(f'  {coin} 오류: {e}')

    print_table('하락장 (2022-01 ~ 2022-12)', bear_results)

    # ── 강세장 (2024~2025) ──
    print('\n[강세장 구간 (2024~2025) 실행 중...]')
    bull_results = []
    for coin in COINS:
        try:
            r = run_backtest(coin, from_date='2024-01-01', to_date='2025-12-31')
            bull_results.append(r)
            print(f'  {r["coin"]:<6} 완료  →  {r["ror"]:+.1f}%  (거래:{r["total"]}회)')
        except Exception as e:
            print(f'  {coin} 오류: {e}')

    print_table('강세장 (2024-01 ~ 2025-12)', bull_results)

    print('\n백테스트 완료\n')


if __name__ == '__main__':
    main()
