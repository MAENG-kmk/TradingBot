"""
코인별 백테스트 실행기

사용법:
  python -m backtest.runner --coin eth
  python -m backtest.runner --coin btc
  python -m backtest.runner --coin all
  python -m backtest.runner --coin eth --plot
  python -m backtest.runner --coin eth --chart-save

출력 차트 (--plot / --chart-save):
  - 자산 곡선 vs Buy & Hold
  - 드로우다운
  - 연도별 수익률 바 차트
  - 핵심 지표 요약

━━━ 파라미터 수정 가이드 ━━━
전략 파라미터를 바꾸려면 아래 COIN_CONFIGS 딕셔너리의 해당 코인 'params' 섹션을 수정하세요.
각 파라미터의 의미는 주석을 참고하세요.

슬리피지를 바꾸려면 'slippage_pct' 값을 수정하세요 (0.0003 = 0.03%).
"""
import argparse
import sys
import os
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd
import backtrader as bt
from backtest.base_strategy import CoinBacktestStrategy


def _load_intrabar(coin_name):
    """코인의 1h CSV를 로드해 datetime 인덱스 DataFrame으로 반환 (없으면 None)"""
    path = f'backtestDatas/{coin_name.lower()}usdt_1h.csv'
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, index_col='Date', parse_dates=True)
    df.index = df.index.tz_localize(None)
    return df


# ─────────────────────────────────────────────────────────────
# 코인별 설정
#
# [슬리피지 slippage_pct]
#   실제 체결 시 발생하는 bid-ask 스프레드 비용.
#   commission 0.05%와 별도로 매 진입/청산 시 적용됨.
#   BTC/ETH(매우 유동적): 0.02%
#   SOL/BNB/XRP/LINK:    0.03%
#   DOGE/AVAX/ARB/AAVE:  0.05%
#
# [전략 params]
#   tr_bb_period       : 볼린저밴드 기간 (봉 수). 클수록 큰 추세만 진입
#   tr_bb_std          : 볼린저밴드 표준편차 배수. 클수록 강한 돌파만 진입
#   rsi_overbuy        : RSI 과매수 기준. 이 값 이상이면 롱 진입 차단
#   rsi_oversell       : RSI 과매도 기준. 이 값 이하면 숏 진입 차단
#   adx_threshold      : ADX 최소값. 추세장 필터 (낮을수록 더 많은 진입)
#   atr_multiplier     : 변동성 급변 감지 배수. 클수록 변동성 청산 늦게 발동
#   target_ror_pct     : 목표 수익률 (%). 이 값에 도달하면 타이트 트레일링으로 전환
#   trailing_ratio     : 1~3구간 트레일링 비율 (ex. 0.4 = 최고가의 40% 하락 시 청산)
#   tight_trailing_ratio: 4구간(목표 달성 후) 타이트 트레일링 비율
# ─────────────────────────────────────────────────────────────
COIN_CONFIGS = {
    'eth': {
        'data_file': 'backtestDatas/ethusdt_4h.csv',
        'slippage_pct': 0.0002,   # 0.02% — 유동성 매우 높음
        'params': dict(
            tr_bb_period=20, tr_bb_std=2.0,
            rsi_overbuy=80, rsi_oversell=20,
            adx_threshold=20, atr_multiplier=3.0,
            target_ror_pct=15.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.65,
        ),
    },
    'btc': {
        'data_file': 'backtestDatas/btcusdt_4h.csv',
        'slippage_pct': 0.0002,   # 0.02% — 유동성 매우 높음
        'params': dict(
            tr_bb_period=20, tr_bb_std=2.0,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=30, atr_multiplier=3.0,
            target_ror_pct=7.0, trailing_ratio=0.5,
            tight_trailing_ratio=0.75,
        ),
    },
    'sol': {
        'data_file': 'backtestDatas/solusdt_4h.csv',
        'slippage_pct': 0.0003,   # 0.03%
        'params': dict(
            tr_bb_period=15, tr_bb_std=2.5,
            rsi_overbuy=80, rsi_oversell=20,
            adx_threshold=15, atr_multiplier=1.5,
            target_ror_pct=7.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.85,
        ),
    },
    'bnb': {
        'data_file': 'backtestDatas/bnbusdt_4h.csv',
        'slippage_pct': 0.0003,   # 0.03%
        'params': dict(
            tr_bb_period=20, tr_bb_std=2.0,
            rsi_overbuy=70, rsi_oversell=30,
            adx_threshold=20, atr_multiplier=1.5,
            target_ror_pct=10.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.85,
        ),
    },
    'xrp': {
        'data_file': 'backtestDatas/xrpusdt_4h.csv',
        'slippage_pct': 0.0003,   # 0.03%
        'params': dict(
            tr_bb_period=20, tr_bb_std=2.0,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=15, atr_multiplier=3.0,
            target_ror_pct=15.0, trailing_ratio=0.5,
            tight_trailing_ratio=0.85,
        ),
    },
    'link': {
        'data_file': 'backtestDatas/linkusdt_4h.csv',
        'slippage_pct': 0.0003,   # 0.03%
        'params': dict(
            tr_bb_period=20, tr_bb_std=2.5,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=20, atr_multiplier=1.5,
            target_ror_pct=7.0, trailing_ratio=0.5,
            tight_trailing_ratio=0.85,
        ),
    },
    'doge': {
        'data_file': 'backtestDatas/dogeusdt_4h.csv',
        'slippage_pct': 0.0005,   # 0.05% — 변동성 높음
        'params': dict(
            tr_bb_period=20, tr_bb_std=2.0,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=20, atr_multiplier=2.0,
            target_ror_pct=15.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.85,
        ),
    },
    'avax': {
        'data_file': 'backtestDatas/avaxusdt_4h.csv',
        'slippage_pct': 0.0005,   # 0.05%
        'params': dict(
            tr_bb_period=20, tr_bb_std=2.0,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=15, atr_multiplier=1.5,
            target_ror_pct=15.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.85,
        ),
    },
    'arb': {
        'data_file': 'backtestDatas/arbusdt_4h.csv',
        'slippage_pct': 0.0005,   # 0.05%
        'params': dict(
            tr_bb_period=20, tr_bb_std=2.0,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=15, atr_multiplier=1.5,
            target_ror_pct=10.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.65,
        ),
    },
    'aave': {
        'data_file': 'backtestDatas/aaveusdt_4h.csv',
        'slippage_pct': 0.0005,   # 0.05%
        'params': dict(
            tr_bb_period=20, tr_bb_std=2.0,
            rsi_overbuy=80, rsi_oversell=30,
            adx_threshold=15, atr_multiplier=3.0,
            target_ror_pct=7.0, trailing_ratio=0.4,
            tight_trailing_ratio=0.65,
        ),
    },
}


# ─────────────────────────────────────────────────────────────
# EquityCurveAnalyzer: 봉마다 포트폴리오 가치 수집
# ─────────────────────────────────────────────────────────────
class EquityCurveAnalyzer(bt.Analyzer):
    """봉마다 포트폴리오 가치와 기준 가격을 기록해 차트용 데이터 제공"""

    def start(self):
        self._dates = []
        self._values = []
        self._prices = []

    def next(self):
        self._dates.append(self.strategy.data.datetime.date(0))
        self._values.append(self.strategy.broker.getvalue())
        self._prices.append(float(self.strategy.data.close[0]))

    def get_analysis(self):
        return {
            'dates': self._dates,
            'values': self._values,
            'prices': self._prices,
        }


def run_backtest(coin_name, data_file=None, initial_cash=100000.0, slippage_pct=None):
    """단일 코인 백테스트 실행"""
    config = COIN_CONFIGS.get(coin_name)
    if config is None:
        print(f"  지원하지 않는 코인: {coin_name}")
        print(f"  지원 코인: {', '.join(COIN_CONFIGS.keys())}")
        return None

    data_path = data_file or config['data_file']
    if data_path is None or not os.path.exists(data_path):
        print(f"  {coin_name.upper()}: 백테스트 데이터 없음 ({data_path})")
        return None

    slip = slippage_pct if slippage_pct is not None else config.get('slippage_pct', 0.0003)

    intrabar_df = _load_intrabar(coin_name)
    if intrabar_df is not None:
        print(f"  1h 정밀 데이터 로드: {len(intrabar_df)}봉")

    cerebro = bt.Cerebro()
    cerebro.addstrategy(CoinBacktestStrategy, intrabar_data=intrabar_df, **config['params'])

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
    cerebro.broker.setcommission(commission=0.0005)   # 0.05% 수수료 (편도)
    # 슬리피지: bid-ask 스프레드 시뮬레이션 (진입/청산 모두 적용)
    cerebro.broker.set_slippage_perc(
        perc=slip,
        slip_open=True,
        slip_limit=True,
        slip_match=True,
        slip_out=False,
    )

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown,    _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(EquityCurveAnalyzer,      _name='equity')

    result = cerebro.run()
    strat = result[0]

    # 결과 파싱
    ta = strat.analyzers.trades.get_analysis()
    total = ta.total.total if hasattr(ta.total, 'total') else 0
    if total == 0:
        print(f"  {coin_name.upper()}: 거래 없음")
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
    eq_data = strat.analyzers.equity.get_analysis()

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
        'initial_cash': initial_cash,
        'slippage_pct': slip,
        'equity_curve': eq_data,
    }


def print_result(r):
    """결과 출력"""
    slip_pct = r.get('slippage_pct', 0) * 100
    print(f"\n=== {r['coin']} 백테스트 결과 ({r['data']}) ===")
    print(f"수수료: 0.05% / 슬리피지: {slip_pct:.2f}% (편도)")
    print(f"총 거래: {r['trades']}회  (수익: {r['won']}, 손실: {r['lost']})")
    print(f"승률: {r['win_rate']:.1f}%")
    print(f"수익/손실 비율: {r['pl_ratio']:.2f}")
    print(f"ROR: {r['ror']:.2f}%")
    print(f"Sharpe Ratio: {r['sharpe']:.2f}")
    print(f"MDD: {r['mdd']:.2f}%")
    print(f"최종 자본: ${r['final_balance']:.2f}")


def print_summary(results):
    """전체 요약 출력"""
    print(f"\n{'='*70}")
    print(f"{'코인':<8} {'거래':>5} {'승률':>6} {'P/L비':>6} {'ROR':>8} {'샤프':>6} {'MDD':>6} {'슬리피지':>8}")
    print(f"{'-'*70}")
    for r in results:
        slip_pct = r.get('slippage_pct', 0) * 100
        print(f"{r['coin']:<8} {r['trades']:>5} {r['win_rate']:>5.1f}% "
              f"{r['pl_ratio']:>6.2f} {r['ror']:>7.1f}% {r['sharpe']:>6.2f} "
              f"{r['mdd']:>5.1f}% {slip_pct:>7.2f}%")
    print(f"{'='*70}")


# ─────────────────────────────────────────────────────────────
# 차트 출력
# ─────────────────────────────────────────────────────────────
def plot_result(r, save_path=None):
    """
    백테스트 결과 3-패널 차트.
    save_path 지정 시 PNG 저장, 없으면 화면 표시.
    """
    import matplotlib
    if save_path:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec

    eq = r.get('equity_curve', {})
    dates_raw = eq.get('dates', [])
    values_raw = eq.get('values', [])
    prices_raw = eq.get('prices', [])

    if not dates_raw:
        print("  차트 데이터 없음")
        return

    dates = pd.to_datetime(dates_raw)
    values = np.array(values_raw, dtype=float)
    prices = np.array(prices_raw, dtype=float)
    initial = r['initial_cash']

    # Buy & Hold 비교선
    bh_values = initial * (prices / prices[0])

    # 드로우다운
    running_max = np.maximum.accumulate(values)
    drawdown = (values - running_max) / running_max * 100

    # 연도별 수익률
    df_eq = pd.DataFrame({'value': values}, index=dates)
    year_end = df_eq['value'].resample('YE').last().dropna()
    annual_years = []
    annual_rors = []
    prev = initial
    for dt, val in year_end.items():
        annual_years.append(dt.year)
        annual_rors.append((val - prev) / prev * 100)
        prev = val

    # ── 레이아웃
    fig = plt.figure(figsize=(14, 10), facecolor='#1e1e1e')
    gs = gridspec.GridSpec(3, 1, figure=fig, height_ratios=[3, 1.5, 1.5], hspace=0.35)

    coin = r['coin']
    slip_pct = r.get('slippage_pct', 0) * 100
    fig.suptitle(
        f"{coin} Backtest  |  ROR: {r['ror']:+.1f}%  Sharpe: {r['sharpe']:.2f}  "
        f"MDD: {r['mdd']:.1f}%  (수수료 0.05% + 슬리피지 {slip_pct:.2f}%)",
        color='white', fontsize=12, y=0.98,
    )

    # ── 패널 1: 자산 곡선
    ax1 = fig.add_subplot(gs[0])
    ax1.set_facecolor('#2b2b2b')
    ax1.plot(dates, values / initial * 100, color='#00b4d8', linewidth=1.5, label='Strategy')
    ax1.plot(dates, bh_values / initial * 100, color='#adb5bd',
             linewidth=1.0, linestyle='--', alpha=0.7, label='Buy & Hold')
    ax1.axhline(y=100, color='#555', linestyle=':', linewidth=0.8)
    ax1.set_ylabel('Portfolio Value (%)', color='#ccc')
    ax1.tick_params(colors='#ccc', labelsize=8)
    for sp in ax1.spines.values():
        sp.set_color('#444')
    ax1.legend(loc='upper left', facecolor='#333', labelcolor='white', fontsize=9, framealpha=0.8)

    # 지표 텍스트 박스
    metrics_txt = (
        f"Trades: {r['trades']}   WinRate: {r['win_rate']:.1f}%   P/L: {r['pl_ratio']:.2f}\n"
        f"Final: ${r['final_balance']:,.0f}   Init: ${initial:,.0f}"
    )
    ax1.text(0.01, 0.97, metrics_txt, transform=ax1.transAxes, fontsize=8.5,
             verticalalignment='top', color='#ddd',
             bbox=dict(boxstyle='round,pad=0.4', facecolor='#2b2b2b', edgecolor='#555', alpha=0.9))

    # ── 패널 2: 드로우다운
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.set_facecolor('#2b2b2b')
    ax2.fill_between(dates, drawdown, 0, color='#ef5350', alpha=0.75, label='Drawdown')
    ax2.set_ylabel('Drawdown (%)', color='#ccc')
    ax2.tick_params(colors='#ccc', labelsize=8)
    for sp in ax2.spines.values():
        sp.set_color('#444')
    ax2.text(0.01, 0.05, f"Max DD: {r['mdd']:.1f}%", transform=ax2.transAxes,
             fontsize=8.5, color='#ef9a9a',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='#2b2b2b', edgecolor='#555', alpha=0.8))

    # ── 패널 3: 연도별 수익률
    ax3 = fig.add_subplot(gs[2])
    ax3.set_facecolor('#2b2b2b')
    if annual_years:
        bar_colors = ['#26a69a' if v >= 0 else '#ef5350' for v in annual_rors]
        bars = ax3.bar([str(y) for y in annual_years], annual_rors, color=bar_colors, width=0.6)
        ax3.axhline(y=0, color='#888', linewidth=0.8)
        # 값 레이블
        for bar, val in zip(bars, annual_rors):
            y_pos = bar.get_height() + 0.5 if val >= 0 else bar.get_height() - 1.5
            ax3.text(bar.get_x() + bar.get_width() / 2, y_pos,
                     f"{val:+.1f}%", ha='center', va='bottom' if val >= 0 else 'top',
                     fontsize=7.5, color='white')
    ax3.set_ylabel('Annual ROR (%)', color='#ccc')
    ax3.tick_params(colors='#ccc', labelsize=8)
    for sp in ax3.spines.values():
        sp.set_color('#444')

    plt.setp(ax1.get_xticklabels(), visible=False)
    plt.setp(ax2.get_xticklabels(), visible=False)

    if save_path:
        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else '.', exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='#1e1e1e')
        print(f"  차트 저장: {save_path}")
    else:
        plt.tight_layout()
        plt.show()
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='코인별 백테스트')
    parser.add_argument('--coin', required=True, help='코인 이름 (eth, btc, all)')
    parser.add_argument('--data', default=None, help='데이터 파일 경로 (선택)')
    parser.add_argument('--cash', type=float, default=100000.0, help='초기 자본')
    parser.add_argument('--slippage', type=float, default=None,
                        help='슬리피지 (소수, ex. 0.0003). 미지정 시 코인별 기본값 사용')
    parser.add_argument('--plot', action='store_true', help='백테스트 결과 차트 표시')
    parser.add_argument('--chart-save', action='store_true', help='차트를 charts/ 폴더에 PNG 저장')
    args = parser.parse_args()

    if args.coin == 'all':
        results = []
        for coin_name in COIN_CONFIGS:
            print(f"\n[{coin_name.upper()}] 백테스트 중...")
            r = run_backtest(coin_name, initial_cash=args.cash, slippage_pct=args.slippage)
            if r:
                results.append(r)
                if args.chart_save:
                    os.makedirs('charts', exist_ok=True)
                    plot_result(r, save_path=f"charts/{coin_name.lower()}_backtest.png")
        if results:
            print_summary(results)
    else:
        coin_name = args.coin.lower()
        print(f"\n[{coin_name.upper()}] 백테스트 중...")
        r = run_backtest(coin_name, data_file=args.data, initial_cash=args.cash,
                         slippage_pct=args.slippage)
        if r:
            print_result(r)
            if args.plot:
                plot_result(r)
            elif args.chart_save:
                os.makedirs('charts', exist_ok=True)
                plot_result(r, save_path=f"charts/{coin_name.lower()}_backtest.png")
