# backtest_compare_btc.py
"""
BTC 4H 추세추종 전략 비교 백테스트
실행: python backtest_compare_btc.py
      python backtest_compare_btc.py --plot
      python backtest_compare_btc.py --save
"""
import argparse
import os
import sys
sys.path.append(os.path.abspath('.'))

import numpy as np
import pandas as pd
import backtrader as bt

from backtestStrategy.DonchianStrategy   import DonchianStrategy
from backtestStrategy.SupertrendStrategy import SupertrendStrategy
from backtestStrategy.EMACrossStrategy   import EMACrossStrategy

DATA_PATH    = 'backtestDatas/btcusdt_4h_compare.csv'
INITIAL_CASH = 10_000.0
COMMISSION   = 0.0004   # 0.04% taker fee
SLIPPAGE     = 0.0002   # 0.02%

STRATEGIES = [
    ('Donchian',    DonchianStrategy,   {}),
    ('Supertrend',  SupertrendStrategy, {}),
    ('EMA Cross',   EMACrossStrategy,   {}),
]


class _EquityCurve(bt.Analyzer):
    def start(self):
        self._dates  = []
        self._values = []

    def next(self):
        self._dates.append(self.strategy.data.datetime.date(0))
        self._values.append(self.strategy.broker.getvalue())

    def get_analysis(self):
        return {'dates': self._dates, 'values': self._values}


def _load_feed():
    return bt.feeds.GenericCSVData(
        dataname=DATA_PATH,
        dtformat='%Y-%m-%d %H:%M:%S',
        timeframe=bt.TimeFrame.Minutes,
        compression=240,
        openinterest=-1,
        headers=True,
    )


def run_one(name, strategy_cls, params):
    cerebro = bt.Cerebro()
    cerebro.addstrategy(strategy_cls, **params)
    cerebro.adddata(_load_feed())
    cerebro.broker.setcash(INITIAL_CASH)
    cerebro.broker.setcommission(commission=COMMISSION)
    cerebro.broker.set_slippage_perc(
        perc=SLIPPAGE, slip_open=True, slip_limit=True,
        slip_match=True, slip_out=False,
    )
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,  _name='sharpe',
                        riskfreerate=0.0, annualize=True)
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(_EquityCurve,               _name='equity')

    result = cerebro.run()
    strat  = result[0]

    ta      = strat.analyzers.trades.get_analysis()
    total   = ta.total.total if hasattr(ta.total, 'total') else 0
    won     = ta.won.total   if (total > 0 and hasattr(ta, 'won'))  else 0
    lost    = ta.lost.total  if (total > 0 and hasattr(ta, 'lost')) else 0
    avg_p   = ta.won.pnl.average  if won  > 0 else 0.0
    avg_l   = ta.lost.pnl.average if lost > 0 else 0.0

    final   = cerebro.broker.getvalue()
    ror     = (final - INITIAL_CASH) / INITIAL_CASH * 100
    sharpe  = strat.analyzers.sharpe.get_analysis().get('sharperatio') or 0.0
    mdd     = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0.0)
    pl      = abs(avg_p / avg_l) if avg_l != 0 else 0.0
    eq      = strat.analyzers.equity.get_analysis()

    return {
        'name':      name,
        'trades':    total,
        'win_rate':  won / total * 100 if total > 0 else 0.0,
        'pl_ratio':  pl,
        'ror':       ror,
        'sharpe':    sharpe,
        'mdd':       mdd,
        'final':     final,
        'equity':    eq,
    }


def print_table(results):
    header = f"{'전략':<14} {'총수익률':>9} {'Sharpe':>7} {'MDD':>7} {'승률':>7} {'손익비':>7} {'거래':>6}"
    print('\n' + '=' * len(header))
    print(header)
    print('-' * len(header))
    for r in results:
        print(
            f"{r['name']:<14} "
            f"{r['ror']:>8.1f}%  "
            f"{r['sharpe']:>6.2f}  "
            f"{r['mdd']:>6.1f}%  "
            f"{r['win_rate']:>6.1f}%  "
            f"{r['pl_ratio']:>6.2f}  "
            f"{r['trades']:>5}"
        )
    print('=' * len(header))


def plot_equity(results, save_path=None):
    import matplotlib
    if save_path:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    colors = ['#00b4d8', '#26a69a', '#ffa726']
    fig, ax = plt.subplots(figsize=(14, 6), facecolor='#1e1e1e')
    ax.set_facecolor('#2b2b2b')

    for r, color in zip(results, colors):
        eq     = r['equity']
        dates  = pd.to_datetime(eq['dates'])
        values = np.array(eq['values'])
        ax.plot(dates, values / INITIAL_CASH * 100, color=color,
                linewidth=1.5, label=f"{r['name']} ({r['ror']:+.1f}%)")

    ax.axhline(y=100, color='#555', linestyle=':', linewidth=0.8)
    ax.set_ylabel('Portfolio Value (%)', color='#ccc')
    ax.set_title('BTC 4H Trend-Following Strategy Comparison', color='white', fontsize=13)
    ax.tick_params(colors='#ccc')
    for sp in ax.spines.values():
        sp.set_color('#444')
    ax.legend(facecolor='#333', labelcolor='white', fontsize=10)

    if save_path:
        os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='#1e1e1e')
        print(f"차트 저장: {save_path}")
    else:
        plt.tight_layout()
        plt.show()
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BTC 4H 추세추종 전략 비교')
    parser.add_argument('--plot', action='store_true', help='에쿼티 커브 화면 출력')
    parser.add_argument('--save', action='store_true', help='에쿼티 커브 PNG 저장')
    args = parser.parse_args()

    if not os.path.exists(DATA_PATH):
        print(f"데이터 없음: {DATA_PATH}\npython fetch_btc_data.py 를 먼저 실행하세요.")
        sys.exit(1)

    results = []
    for name, cls, params in STRATEGIES:
        print(f"[{name}] 실행 중...")
        r = run_one(name, cls, params)
        results.append(r)
        print(f"  완료 — ROR: {r['ror']:+.1f}%  Sharpe: {r['sharpe']:.2f}  MDD: {r['mdd']:.1f}%")

    print_table(results)

    if args.plot:
        plot_equity(results)
    elif args.save:
        plot_equity(results, save_path='charts/btc_compare.png')
