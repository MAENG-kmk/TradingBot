"""
변동성 돌파 종가 청산 전략 — 공통 베이스

DOGE 전략과 동일한 VB close 로직.
서브클래스에서 SYMBOL, LEVERAGE, QUANTITY_PRECISION 만 설정하면 됨.

진입: 현재 4H 캔들의 고가/저가가 open ± VB_K × prev_range 돌파 시 시장가 진입
청산: 동일 캔들 종료 시점에 시장가 청산 (종가 청산)
"""
import calendar
import time
import asyncio
from datetime import datetime

from coins.base_strategy import BaseCoinStrategy
from tools.createOrder import createOrder
from tools.setLeverage import setLeverage
from tools.telegram import send_message
from MongoDB_python.client import saveEntryDetails, deleteEntryDetails


class BaseVBCloseStrategy(BaseCoinStrategy):
    """
    래리 윌리엄즈 변동성 돌파 (4H 캔들 종가 청산) 베이스 클래스

    진입 로직:
      롱 트리거 = 현재 캔들 시가 + VB_K × 직전 캔들 변동폭(High-Low)
      숏 트리거 = 현재 캔들 시가 - VB_K × 직전 캔들 변동폭
      → 현재 캔들의 고가/저가가 트리거 터치 시 시장가 진입

    청산 로직:
      현재 4H 캔들 종료 시점에 무조건 시장가 청산 (종가 청산)
      → 손절/트레일링 없이 캔들 마감 = 청산
    """

    VB_K             = 0.3
    VB_MIN_RANGE_PCT = 0.3

    # ================================================================
    #  진입 시그널 — 변동성 돌파
    # ================================================================

    def check_entry_signal(self):
        """
        4H 캔들 변동성 돌파 진입 신호 확인

        Returns:
            ('long'|'short', 0, 'vb_close', meta) | (None, 0, None, None)
            meta: {'candle_close_ts': float}
        """
        df = self.get_data(limit=300)
        if df is None or len(df) < self.VB_MA_PERIOD + 2 if hasattr(self, 'VB_MA_PERIOD') else len(df) < 3:
            return None, 0, None, None

        # XGBoost 레짐 필터 (모델 있을 때만 적용)
        if self._rf is not None:
            prob = self._rf.predict(df)
            if prob < 0.55:
                return None, 0, None, None

        # 직전 완료 캔들
        prev_high  = float(df.iloc[-2]['High'])
        prev_low   = float(df.iloc[-2]['Low'])
        prev_close = float(df.iloc[-2]['Close'])
        prev_range = prev_high - prev_low

        # 최소 변동폭 필터
        if prev_close <= 0 or prev_range <= 0:
            return None, 0, None, None
        if prev_range / prev_close * 100 < self.VB_MIN_RANGE_PCT:
            return None, 0, None, None

        # 현재 캔들
        cur_open  = float(df.iloc[-1]['Open'])
        cur_high  = float(df.iloc[-1]['High'])
        cur_low   = float(df.iloc[-1]['Low'])

        long_trig  = cur_open + self.VB_K * prev_range
        short_trig = cur_open - self.VB_K * prev_range

        long_ok  = cur_high >= long_trig  and long_trig  > cur_open
        short_ok = cur_low  <= short_trig and short_trig < cur_open

        # 양방향 동시 트리거 → 방향성 불명확, 스킵
        if long_ok and short_ok:
            return None, 0, None, None

        if not long_ok and not short_ok:
            return None, 0, None, None

        # 현재 캔들 종료 시각 계산 (UTC 기준)
        candle_open_ts  = calendar.timegm(df.index[-1].timetuple())
        candle_close_ts = candle_open_ts + 4 * 3600

        meta = {
            'candle_close_ts': candle_close_ts,
            'long_trigger'   : long_trig,
            'short_trigger'  : short_trig,
            'prev_range'     : prev_range,
        }

        if long_ok:
            return 'long',  0, 'vb_close', meta
        else:
            return 'short', 0, 'vb_close', meta

    # ================================================================
    #  청산 로직 — 캔들 종가에 무조건 청산
    # ================================================================

    def _manage_exit(self, position):
        """
        VB 종가 청산: candle_close_ts 도달 시 즉시 청산
        재시작 복구: _state 없으면 현재 캔들 종료 시각으로 초기화
        """
        if self._state is None:
            candle_close_ts = self._estimate_candle_close_ts()
            self._state = {
                'mode'           : 'vb_close',
                'candle_close_ts': candle_close_ts,
                'entry_time'     : time.time(),
            }

        mode = self._state.get('mode', 'vb_close')

        if mode == 'vb_close':
            candle_close_ts = self._state.get('candle_close_ts', 0)
            now = time.time()
            if now >= candle_close_ts:
                ror = position['ror']
                self._close_position(position, f"VB종가청산(ROR:{ror:.1f}%)")
            else:
                remaining_min = (candle_close_ts - now) / 60
                print(f"  유지: {self.SYMBOL} | VB | ROR:{position['ror']:.1f}%"
                      f" | 청산까지: {remaining_min:.0f}분")
            return

        # 예상치 못한 모드 → 베이스 클래스 위임
        super()._manage_exit(position)

    # ================================================================
    #  진입 관리 오버라이드 — vb_close 메타 전달 처리
    # ================================================================

    def _manage_entry(self, total_balance, available_balance):
        bullet = float(total_balance) / 10 * 0.99
        if float(available_balance) < bullet:
            return

        signal, target_ror, mode, meta = self.check_entry_signal()
        if signal is None:
            return

        price = self._get_price()
        if price <= 0:
            return
        qty = self._calc_quantity(bullet, price)
        if qty <= 0:
            return

        side = 'BUY' if signal == 'long' else 'SELL'
        setLeverage(self.client, self.SYMBOL, self.LEVERAGE)
        response = createOrder(self.client, self.SYMBOL, side, 'MARKET', qty)

        if response:
            self._init_state(target_ror, mode=mode, ou=meta)
            saveEntryDetails(self.SYMBOL, mode, signal, price)
            candle_close_ts = meta.get('candle_close_ts', 0) if meta else 0
            close_dt = datetime.utcfromtimestamp(candle_close_ts).strftime('%H:%M UTC')
            msg = (f"✅VB {self.SYMBOL} {signal.upper()} 진입 | qty:{qty}"
                   f" | k={self.VB_K} | 청산예정:{close_dt}")
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass
        else:
            print(f"  ❌ {self.SYMBOL} 주문 실패")

    # ================================================================
    #  상태 초기화 오버라이드 — vb_close 모드 처리
    # ================================================================

    def _init_state(self, target_ror, mode='trend_following', ou=None, vb_meta=None):
        if mode == 'vb_close':
            meta = ou  # _manage_entry에서 meta 전체를 ou 인자로 전달
            candle_close_ts = meta.get('candle_close_ts', 0) if meta else 0
            self._state = {
                'mode'           : 'vb_close',
                'candle_close_ts': candle_close_ts,
                'entry_time'     : time.time(),
                # 베이스 클래스 호환용 필드
                'target_ror'     : 9999,
                'stop_loss'      : -9999,
                'highest_ror'    : 0,
                'trailing_active': False,
                'phase'          : 1,
                'atr_ratio'      : 0.03,
            }
            return
        super()._init_state(target_ror, mode=mode, ou=ou)

    # ================================================================
    #  유틸리티
    # ================================================================

    def _estimate_candle_close_ts(self):
        """재시작 복구용: 현재 4H 캔들 종료 시각 추정 (UTC 기준)"""
        now           = time.time()
        candle_seconds = 4 * 3600
        candle_start  = (now // candle_seconds) * candle_seconds
        return candle_start + candle_seconds

    def _should_hold(self, current_side):
        """VB 종가 청산은 재진입 보류 없이 무조건 청산"""
        return False
