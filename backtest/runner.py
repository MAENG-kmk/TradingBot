"""
코인별 백테스트 실행기

사용법:
  python -m backtest.runner --coin eth
  python -m backtest.runner --coin btc
  python -m backtest.runner --coin all
  python -m backtest.runner --coin eth --data backtestDatas/ethusdt_4h.csv
"""
import argparse
import sys
import os
sys.path.append(os.path.abspath("."))

import backtrader as bt
from backtest.base_strategy import CoinBacktestStrategy

# 코인별 설정: 백테스트 파라미터 + 데이터 파일
COIN_CONFIGS = {
    'eth': {
        'data_file': 'backtestDatas/ethusdt_4h.csv',
        'params': dict(
            ema_short=10, ema_long=30,
            rsi_overbuy=70, rsi_oversell=30,
            adx_threshold=15, atr_multiplier=2.0,
            target_ror_pct=15.0, trailing_ratio=0.6,
            tight_trailing_ratio=0.65,
        ),
    },
    'btc': {
        'data_file': 'backtestDatas/btcusdt_4h.csv',
        'params': dict(
            ema_short=5, ema_long=20,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=30, atr_multiplier=3.0,
            target_ror_pct=7.0, trailing_ratio=0.5,
            tight_trailing_ratio=0.75,
        ),
    },
    'sol': {
        'data_file': 'backtestDatas/solusdt_4h.csv',
        'params': dict(
            ema_short=20, ema_long=50,
            rsi_overbuy=70, rsi_oversell=20,
            adx_threshold=25, atr_multiplier=1.5,
            target_ror_pct=15.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.75,
        ),
    },
    'bnb': {
        'data_file': 'backtestDatas/bnbusdt_4h.csv',
        'params': dict(
            ema_short=5, ema_long=50,
            rsi_overbuy=70, rsi_oversell=30,
            adx_threshold=20, atr_multiplier=1.5,
            target_ror_pct=10.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.85,
        ),
    },
    'xrp': {
        'data_file': 'backtestDatas/xrpusdt_4h.csv',
        'params': dict(
            ema_short=10, ema_long=30,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=15, atr_multiplier=3.0,
            target_ror_pct=15.0, trailing_ratio=0.5,
            tight_trailing_ratio=0.85,
        ),
    },
    'link': {
        'data_file': 'backtestDatas/linkusdt_4h.csv',
        'params': dict(
            ema_short=5, ema_long=60,
            rsi_overbuy=70, rsi_oversell=20,
            adx_threshold=30, atr_multiplier=1.5,
            target_ror_pct=15.0, trailing_ratio=0.7,
            tight_trailing_ratio=0.65,
        ),
    },
    'doge': {
        'data_file': 'backtestDatas/dogeusdt_4h.csv',
        'params': dict(
            ema_short=10, ema_long=50,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=20, atr_multiplier=2.0,
            target_ror_pct=15.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.85,
        ),
    },
    'avax': {
        'data_file': 'backtestDatas/avaxusdt_4h.csv',
        'params': dict(
            ema_short=20, ema_long=60,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=15, atr_multiplier=1.5,
            target_ror_pct=15.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.85,
        ),
    },
    'arb': {
        'data_file': 'backtestDatas/arbusdt_4h.csv',
        'params': dict(
            ema_short=20, ema_long=50,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=15, atr_multiplier=1.5,
            target_ror_pct=10.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.65,
        ),
    },
    'aave': {
        'data_file': 'backtestDatas/aaveusdt_4h.csv',
        'params': dict(
            ema_short=15, ema_long=20,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=15, atr_multiplier=3.0,
            target_ror_pct=7.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.65,
        ),
    },
}


def run_backtest(coin_name, data_file=None, initial_cash=100000.0):
    """단일 코인 백테스트 실행"""
    config = COIN_CONFIGS.get(coin_name)
    if config is None:
        print(f"❌ 지원하지 않는 코인: {coin_name}")
        print(f"   지원 코인: {', '.join(COIN_CONFIGS.keys())}")
        return None

    data_path = data_file or config['data_file']
    if data_path is None or not os.path.exists(data_path):
        print(f"⏭️  {coin_name.upper()}: 백테스트 데이터 없음 ({data_path})")
        return None

    cerebro = bt.Cerebro()
    cerebro.addstrategy(CoinBacktestStrategy, **config['params'])

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
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    result = cerebro.run()
    strat = result[0]

    # 결과 파싱
    ta = strat.analyzers.trades.get_analysis()
    total = ta.total.total if hasattr(ta.total, 'total') else 0
    if total == 0:
        print(f"⏭️  {coin_name.upper()}: 거래 없음")
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
        'coin': coin_name.upper(),
        'data': os.path.basename(data_path),
        'trades': total,
        'won': won,
        'lost': lost,
        'win_rate': won / total * 100,
        'pl_ratio': pl_ratio,
        'ror': ror,
        'sharpe': sharpe,
        'mdd': mdd,
        'final_balance': final,
    }


def print_result(r):
    """결과 출력"""
    print(f"\n=== {r['coin']} 백테스트 결과 ({r['data']}) ===")
    print(f"총 거래: {r['trades']}회 (수익: {r['won']}, 손실: {r['lost']})")
    print(f"승률: {r['win_rate']:.1f}%")
    print(f"수익/손실 비율: {r['pl_ratio']:.2f}")
    print(f"ROR: {r['ror']:.2f}%")
    print(f"Sharpe Ratio: {r['sharpe']:.2f}")
    print(f"MDD: {r['mdd']:.2f}%")
    print(f"최종 자본: ${r['final_balance']:.2f}")


def print_summary(results):
    """전체 요약 출력"""
    print(f"\n{'='*65}")
    print(f"{'코인':<8} {'거래':>5} {'승률':>6} {'P/L비':>6} {'ROR':>8} {'샤프':>6} {'MDD':>6}")
    print(f"{'-'*65}")
    for r in results:
        print(f"{r['coin']:<8} {r['trades']:>5} {r['win_rate']:>5.1f}% "
              f"{r['pl_ratio']:>6.2f} {r['ror']:>7.1f}% {r['sharpe']:>6.2f} {r['mdd']:>5.1f}%")
    print(f"{'='*65}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='코인별 백테스트')
    parser.add_argument('--coin', required=True, help='코인 이름 (eth, btc, all)')
    parser.add_argument('--data', default=None, help='데이터 파일 경로 (선택)')
    parser.add_argument('--cash', type=float, default=100000.0, help='초기 자본')
    args = parser.parse_args()

    if args.coin == 'all':
        results = []
        for coin_name in COIN_CONFIGS:
            r = run_backtest(coin_name, initial_cash=args.cash)
            if r:
                results.append(r)
        if results:
            print_summary(results)
    else:
        r = run_backtest(args.coin, data_file=args.data, initial_cash=args.cash)
        if r:
            print_result(r)
