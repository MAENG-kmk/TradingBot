"""
래리 윌리엄스 변동성 돌파 전략 백테스트 (4시간봉)

전략 핵심:
  - Range = 직전 캔들의 (High - Low)
  - 진입: 현재 캔들 Open + Range * k 돌파 시 롱
  - 청산: 다음 캔들 시가 (1캔들 홀드)

사용법:
  python -m backtestStrategy.larry_breakout
  python -m backtestStrategy.larry_breakout --coin btc
  python -m backtestStrategy.larry_breakout --coin all --k 0.5
  python -m backtestStrategy.larry_breakout --coin eth --optimize
"""
import argparse
import sys
import os
sys.path.append(os.path.abspath("."))

import backtrader as bt
from backtrader.analyzers import SharpeRatio, DrawDown, TradeAnalyzer


class LarryBreakout(bt.Strategy):
    """래리 윌리엄스 변동성 돌파 전략"""
    params = (
        ('k', 0.5),            # 돌파 계수 (0.3~0.7)
        ('stake_pct', 0.95),   # 자본 대비 투입 비율
    )

    def __init__(self):
        self.order = None
        self.entry_bar = -1

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order = None

    def next(self):
        if self.order:
            return

        if not self.position:
            if len(self) < 2:
                return
            prev_range = self.data.high[-1] - self.data.low[-1]
            target_price = self.data.open[0] + prev_range * self.p.k

            if self.data.high[0] >= target_price and prev_range > 0:
                size = (self.broker.getvalue() * self.p.stake_pct) / target_price
                self.order = self.buy(size=size, exectype=bt.Order.Limit, price=target_price)
                self.entry_bar = len(self)
        else:
            # 다음 캔들에서 시가 청산 (1캔들 홀드)
            if len(self) > self.entry_bar:
                self.order = self.close()


COINS = {
    'eth':  'backtestDatas/ethusdt_4h.csv',
    'btc':  'backtestDatas/btcusdt_4h.csv',
    'sol':  'backtestDatas/solusdt_4h.csv',
    'bnb':  'backtestDatas/bnbusdt_4h.csv',
    'xrp':  'backtestDatas/xrpusdt_4h.csv',
    'link': 'backtestDatas/linkusdt_4h.csv',
    'doge': 'backtestDatas/dogeusdt_4h.csv',
    'avax': 'backtestDatas/avaxusdt_4h.csv',
    'arb':  'backtestDatas/arbusdt_4h.csv',
    'aave': 'backtestDatas/aaveusdt_4h.csv',
}


def run_backtest(coin, k=0.5, initial_cash=10000, verbose=True):
    data_file = COINS[coin]
    cerebro = bt.Cerebro()
    cerebro.addstrategy(LarryBreakout, k=k)

    data = bt.feeds.GenericCSVData(
        dataname=data_file,
        dtformat='%Y-%m-%d %H:%M:%S',
        datetime=0, open=1, high=2, low=3, close=4, volume=5,
        openinterest=-1, headers=True,
    )
    cerebro.adddata(data)
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=0.0004)  # 바이낸스 선물 수수료

    cerebro.addanalyzer(SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Days, annualize=True)
    cerebro.addanalyzer(DrawDown, _name='drawdown')
    cerebro.addanalyzer(TradeAnalyzer, _name='trades')

    results = cerebro.run()
    strat = results[0]

    final = cerebro.broker.getvalue()
    ror = (final - initial_cash) / initial_cash * 100

    ta = strat.analyzers.trades.get_analysis()
    total_trades = ta.get('total', {}).get('total', 0)
    won = ta.get('won', {}).get('total', 0)
    lost = ta.get('lost', {}).get('total', 0)
    win_rate = (won / total_trades * 100) if total_trades > 0 else 0

    sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
    sharpe = round(sharpe, 2) if sharpe else 'N/A'

    mdd = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)

    avg_win = ta.get('won', {}).get('pnl', {}).get('average', 0)
    avg_loss = abs(ta.get('lost', {}).get('pnl', {}).get('average', 1))
    pl_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 'N/A'

    if verbose:
        print(f"\n{'='*50}")
        print(f"  {coin.upper()}  |  Larry Breakout (k={k})")
        print(f"{'='*50}")
        print(f"  ROR        : {ror:+.2f}%")
        print(f"  Trades     : {total_trades} (W:{won} / L:{lost})")
        print(f"  Win Rate   : {win_rate:.1f}%")
        print(f"  P/L Ratio  : {pl_ratio}")
        print(f"  Sharpe     : {sharpe}")
        print(f"  MDD        : {mdd:.2f}%")
        print(f"  Final      : ${final:,.2f}")

    return {
        'coin': coin.upper(), 'k': k, 'ror': ror, 'trades': total_trades,
        'win_rate': win_rate, 'sharpe': sharpe, 'mdd': mdd, 'pl_ratio': pl_ratio,
        'final': final,
    }


def optimize_k(coin, verbose=True):
    """k값 0.3~0.8 스캔"""
    if verbose:
        print(f"\n{'='*50}")
        print(f"  {coin.upper()} — k 최적화 (0.3 ~ 0.8)")
        print(f"{'='*50}")

    best = None
    results = []
    for k_val in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        r = run_backtest(coin, k=k_val, verbose=False)
        results.append(r)
        if verbose:
            print(f"  k={k_val}  →  ROR={r['ror']:+.1f}%  WR={r['win_rate']:.1f}%  MDD={r['mdd']:.1f}%  Sharpe={r['sharpe']}")
        if best is None or r['ror'] > best['ror']:
            best = r

    if verbose:
        print(f"\n  ★ Best k={best['k']} → ROR={best['ror']:+.1f}%")
    return best, results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='래리 변동성 돌파 백테스트')
    parser.add_argument('--coin', default='btc', help='코인 (btc, eth, all)')
    parser.add_argument('--k', type=float, default=0.5, help='돌파 계수 (default: 0.5)')
    parser.add_argument('--optimize', action='store_true', help='k값 최적화')
    args = parser.parse_args()

    coins = list(COINS.keys()) if args.coin == 'all' else [args.coin.lower()]

    if args.optimize:
        summary = []
        for c in coins:
            best, _ = optimize_k(c)
            summary.append(best)
    else:
        summary = []
        for c in coins:
            r = run_backtest(c, k=args.k)
            summary.append(r)

    if len(summary) > 1:
        print(f"\n{'='*70}")
        print(f"  {'COIN':<6} {'k':>4} {'ROR':>10} {'Trades':>7} {'WR':>7} {'P/L':>6} {'Sharpe':>7} {'MDD':>7}")
        print(f"  {'-'*60}")
        for r in sorted(summary, key=lambda x: x['ror'], reverse=True):
            print(f"  {r['coin']:<6} {r['k']:>4} {r['ror']:>+9.1f}% {r['trades']:>7} {r['win_rate']:>6.1f}% {str(r['pl_ratio']):>6} {str(r['sharpe']):>7} {r['mdd']:>6.1f}%")
