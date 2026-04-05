"""
VB 전략 차트 백테스트 — backtrader 기반

차트 구성:
  - 상단: 캔들스틱 + 볼린저밴드 + 진입/청산 마커
  - 중단: XGB 레짐 확률 (--xgb 사용 시)
  - 하단: 포트폴리오 가치 곡선

사용법:
  python backtest_chart.py --coin doge
  python backtest_chart.py --coin btc --xgb
  python backtest_chart.py --coin eth --from 2024-01-01 --to 2025-01-01
  python backtest_chart.py --coin sol --xgb --save
"""

import argparse, os, sys
sys.path.append(os.path.abspath("."))

import numpy as np
import pandas as pd
import backtrader as bt
import backtrader.indicators as btind
import matplotlib
import matplotlib.pyplot as plt


COMMISSION   = 0.0005
INITIAL      = 100_000.0
POSITION_PCT = 0.10
VB_K         = 0.3
MIN_RANGE_PCT = 0.3

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


# ── XGB 확률 사전 계산 ───────────────────────────────────────────
def add_xgb_probs(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    from tools.regime_filter import RegimeFilter, build_features, FEATURE_NAMES
    try:
        rf   = RegimeFilter.load(f'models/regime_{symbol}.pkl')
        feat = build_features(df)
        X    = feat[list(FEATURE_NAMES[:-1])].values.astype(float)

        # recent_wr: 과거 시그널 히스토리 없으므로 0.5로 고정
        wr     = np.full((len(X), 1), 0.5)
        X_full = np.hstack([X, wr])

        probs = np.full(len(df), 0.5)
        valid = ~np.isnan(X_full).any(axis=1)
        if valid.any():
            probs[valid] = rf.model.predict_proba(X_full[valid])[:, 1]

        df = df.copy()
        df['xgb_prob'] = probs
        print(f"  XGB 확률 계산 완료 (평균: {probs[valid].mean():.3f})")
    except Exception as e:
        print(f"  XGB 로드 실패 → 필터 없이 실행 ({e})")
        df = df.copy()
        df['xgb_prob'] = 0.5
    return df


# ── 커스텀 데이터 피드 (xgb_prob 컬럼 포함) ─────────────────────
class PandasDataXGB(bt.feeds.PandasData):
    lines  = ('xgb_prob',)
    params = (('xgb_prob', 'xgb_prob'),)


# ── XGB 확률 지표 (차트 패널용) ──────────────────────────────────
class XGBThresholdLine(bt.Indicator):
    """0.55 기준선"""
    lines    = ('threshold',)
    plotinfo  = dict(subplot=False, plotmaster=None, plotname='')
    plotlines = dict(threshold=dict(color='orange', linestyle='--', linewidth=1.0))

    def __init__(self):
        self.lines.threshold = 0.55 + self.data.xgb_prob * 0.0  # 0.55 상수선


class XGBProbIndicator(bt.Indicator):
    lines    = ('prob',)
    plotinfo  = dict(subplot=True, plotname='XGB Regime Prob', plotymargin=0.1)
    plotlines = dict(prob=dict(color='purple', linewidth=1.2))

    def __init__(self):
        self.lines.prob = self.data.xgb_prob


# ── VB 전략 ─────────────────────────────────────────────────────
class VBChartStrategy(bt.Strategy):
    """
    VB close 전략 (차트용)

    백테스트 근사:
      - 진입: VB 시그널 발생 봉의 종가 (COC)
      - 청산: 다음 봉 종가 (COC, 1봉 보유)
      실제 전략(트리거가 진입가)과 약간 다르지만 시각화 목적으로 충분
    """
    params = dict(
        k            = VB_K,
        min_range_pct= MIN_RANGE_PCT,
        use_xgb      = False,
        xgb_threshold= 0.55,
        position_pct = POSITION_PCT,
        bb_period    = 20,
        bb_std       = 2.0,
    )

    def __init__(self):
        # 볼린저밴드 (차트 오버레이용)
        self.bb     = btind.BollingerBands(self.data.close,
                                           period=self.p.bb_period,
                                           devfactor=self.p.bb_std)

        # XGB 확률 지표 (subplot)
        if self.p.use_xgb:
            self.xgb_ind       = XGBProbIndicator(self.data)
            self.xgb_threshold = XGBThresholdLine(self.data)

        self.order        = None
        self.bars_in_pos  = 0
        self.entry_dir    = None

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            pnl_pct = trade.pnlcomm / INITIAL * 100
            color   = '\033[92m' if trade.pnlcomm > 0 else '\033[91m'
            print(f"  {color}거래 종료: PnL ${trade.pnlcomm:>+8.2f} "
                  f"({pnl_pct:>+5.2f}%)\033[0m")

    def next(self):
        if self.order:
            return

        # 청산: 1봉 보유 후 종가 청산
        if self.position:
            self.bars_in_pos += 1
            if self.bars_in_pos >= 1:
                self.order = self.close()
                self.bars_in_pos = 0
                self.entry_dir   = None
            return

        # 직전봉 데이터
        prev_range = self.data.high[-1] - self.data.low[-1]
        prev_close = self.data.close[-1]
        if prev_close <= 0 or prev_range <= 0:
            return
        if prev_range / prev_close * 100 < self.p.min_range_pct:
            return

        # 트리거 계산
        cur_open = self.data.open[0]
        cur_high = self.data.high[0]
        cur_low  = self.data.low[0]

        long_trig  = cur_open + self.p.k * prev_range
        short_trig = cur_open - self.p.k * prev_range

        long_ok  = cur_high >= long_trig  and long_trig  > cur_open
        short_ok = cur_low  <= short_trig and short_trig < cur_open

        if long_ok and short_ok:
            return

        dir_now = 'long' if long_ok else ('short' if short_ok else None)
        if dir_now is None:
            return

        # XGB 필터
        if self.p.use_xgb:
            if self.data.xgb_prob[0] < self.p.xgb_threshold:
                return

        # 진입 (COC: 현재 봉 종가 체결)
        size = (self.broker.getcash() * self.p.position_pct) / self.data.close[0]
        if size <= 0:
            return

        if dir_now == 'long':
            self.order = self.buy(size=size)
        else:
            self.order = self.sell(size=size)

        self.bars_in_pos = 0
        self.entry_dir   = dir_now


# ── 백테스트 실행 ─────────────────────────────────────────────────
def run_chart(coin: str, symbol: str, path: str,
              use_xgb: bool = False,
              date_from: str = None, date_to: str = None,
              save: bool = False):

    df = load_ohlcv(path)

    # 날짜 필터
    if date_from:
        df = df[df.index >= date_from]
    if date_to:
        df = df[df.index <= date_to]

    if len(df) < 300:
        print(f"  데이터 부족 ({len(df)}봉), 날짜 범위를 넓혀주세요.")
        return

    print(f"  데이터: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df):,}봉)")

    # XGB 확률 추가
    df = add_xgb_probs(df, symbol) if use_xgb else df.assign(xgb_prob=0.5)

    # Cerebro 설정
    cerebro = bt.Cerebro()
    cerebro.broker.set_coc(True)                     # Cheat-on-Close
    cerebro.broker.setcash(INITIAL)
    cerebro.broker.setcommission(commission=COMMISSION)

    cerebro.addstrategy(VBChartStrategy,
                        use_xgb=use_xgb,
                        position_pct=POSITION_PCT)

    data_feed = PandasDataXGB(dataname=df)
    cerebro.adddata(data_feed)

    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.DrawDown,      _name='dd')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,   _name='sharpe',
                        riskfreerate=0.0, annualize=True,
                        timeframe=bt.TimeFrame.Minutes)

    print(f"\n  백테스트 실행 중...")
    results = cerebro.run()
    strat   = results[0]

    # 결과 출력
    final = cerebro.broker.getvalue()
    ror   = (final - INITIAL) / INITIAL * 100
    ta    = strat.analyzers.trades.get_analysis()
    total = ta.total.total if hasattr(ta.total, 'total') else 0
    won   = ta.won.total   if total > 0 else 0
    mdd   = strat.analyzers.dd.get_analysis().get('max', {}).get('drawdown', 0)
    sh    = strat.analyzers.sharpe.get_analysis().get('sharperatio') or 0

    filter_tag = ' + XGB' if use_xgb else ''
    print(f"\n{'='*55}")
    print(f"  {coin.upper()} VB(k={VB_K}){filter_tag}")
    print(f"{'='*55}")
    print(f"  ROR    : {ror:>+10.2f}%")
    print(f"  Sharpe : {sh:>10.2f}")
    print(f"  MDD    : {mdd:>10.2f}%")
    print(f"  Trades : {total}  WinRate {won/total*100:.1f}%" if total > 0 else "  No trades")
    print(f"{'='*55}")

    # 차트
    os.makedirs('charts', exist_ok=True)
    title = f"{coin.upper()} VB(k={VB_K}){filter_tag}  |  ROR:{ror:+.1f}%  Sharpe:{sh:.2f}  MDD:{mdd:.1f}%"

    if save:
        matplotlib.use('Agg')
        figs = cerebro.plot(
            style='candlestick',
            barup='#26a69a', bardown='#ef5350',
            volup='#26a69a', voldown='#ef5350',
            grid=True,
            iplot=False,
        )
        fig = figs[0][0]
        fig.suptitle(title, fontsize=10)
        save_path = f"charts/{coin}_vb{'_xgb' if use_xgb else ''}.png"
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"\n  차트 저장: {save_path}")
    else:
        cerebro.plot(
            style='candlestick',
            barup='#26a69a', bardown='#ef5350',
            volup='#26a69a', voldown='#ef5350',
            grid=True,
        )


# ── main ─────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--coin',   default='doge',       help='코인 선택')
    parser.add_argument('--xgb',    action='store_true',  help='XGB 레짐 필터 적용')
    parser.add_argument('--from',   dest='date_from',     help='시작일 (YYYY-MM-DD)')
    parser.add_argument('--to',     dest='date_to',       help='종료일 (YYYY-MM-DD)')
    parser.add_argument('--save',   action='store_true',  help='차트를 PNG로 저장')
    args = parser.parse_args()

    coin = args.coin.lower()
    if coin not in COIN_DATA:
        print(f"지원 코인: {', '.join(COIN_DATA.keys())}")
        sys.exit(1)

    path, symbol = COIN_DATA[coin]
    if not os.path.exists(path):
        print(f"데이터 없음: {path}")
        sys.exit(1)

    print(f"\n[{coin.upper()}] 차트 백테스트")
    run_chart(coin, symbol, path,
              use_xgb=args.xgb,
              date_from=args.date_from,
              date_to=args.date_to,
              save=args.save)
