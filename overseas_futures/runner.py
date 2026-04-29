# overseas_futures/runner.py
import asyncio
from datetime import datetime

from tools.telegram import send_message
from MongoDB_python.client import saveEntryDetails
from overseas_futures.base_strategy import BaseOverseasFuturesStrategy, OVERSEAS_CONTRACT_MULT
from overseas_futures.scanner import OverseasFuturesScanner


class OverseasFuturesRunner:
    MAX_POSITIONS = 5
    POSITION_FRAC = 0.1

    def __init__(self, kis):
        self.strategy = BaseOverseasFuturesStrategy(kis)
        self.scanner  = OverseasFuturesScanner(kis, self.strategy)

    def run(self):
        try:
            positions = self.strategy.get_positions()
            self._manage_exits(positions)

            if not self._is_market_open():
                return

            empty = self.MAX_POSITIONS - len(positions)
            if empty <= 0:
                return

            held             = [p["symbol"] for p in positions]
            candidates       = self.scanner.scan(held, limit=empty)
            total, available = self.strategy.get_balance()

            for symbol in candidates:
                spent     = self._try_enter(symbol, total, available)
                available -= spent

        except Exception as e:
            msg = f"[해외선물] runner 오류: {e}"
            print(f"  ❌ {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass

    def _manage_exits(self, positions: list[dict]):
        for pos in positions:
            try:
                self.strategy.manage_exit(pos)
            except Exception as e:
                print(f"  ❌ [해외선물] 청산 오류 {pos.get('symbol')}: {e}")

    def _try_enter(self, symbol: str, total: float, available: float) -> float:
        """Returns budget spent (0 if skipped or failed)."""
        budget = total * self.POSITION_FRAC
        if available < budget:
            return 0

        sig, target_ror, mode, meta = self.strategy.check_entry_signal(symbol)
        if sig is None:
            return 0

        price = self.strategy._get_current_price(symbol)
        if price <= 0:
            return 0

        # 티커 앞부분으로 계약 승수 결정
        ticker = symbol[:2]
        mult   = OVERSEAS_CONTRACT_MULT.get(ticker, OVERSEAS_CONTRACT_MULT.get(symbol[:3], 50))
        qty    = self.strategy.calc_quantity(budget, price, mult)

        if qty <= 0:
            print(f"  [해외선물] {symbol} 예산 부족 (budget=${budget:,.0f}, price={price:.2f})")
            return 0

        order_side = "BUY" if sig == "long" else "SELL"
        success    = self.strategy.place_order(symbol, order_side, qty)

        if success:
            vb_meta = meta if mode == "vb" else None
            self.strategy._init_state(target_ror, mode=mode, vb_meta=vb_meta)
            candle_close_ts = self.strategy._state.get("candle_close_ts") if mode == "vb" else None
            saveEntryDetails(symbol, mode, sig, price, candle_close_ts)
            tag = "📈VB" if mode == "vb" else "✅TR"
            msg = f"{tag} [해외선물] {symbol} {sig.upper()} 진입 | qty:{qty} | target:{target_ror:.1f}%"
            print(f"  {msg}")
            try:
                asyncio.run(send_message(msg))
            except Exception:
                pass
            return budget
        else:
            print(f"  ❌ [해외선물] {symbol} 주문 실패")
            return 0

    def _is_market_open(self, now: datetime | None = None) -> bool:
        """
        CME 선물 장 시간 (KST 기준).
        월~금: 07:00 ~ 익일 06:00 (거의 24시간)
        주말: 일요일 07:00 개장 / 토요일 06:00 마감
        """
        if now is None:
            now = datetime.now()

        weekday = now.weekday()  # 0=월 ... 6=일
        h, m    = now.hour, now.minute
        hm      = h * 100 + m

        if weekday == 5:    # 토요일: 00:00~06:00만 (금요일 야간 이월)
            return hm < 600

        if weekday == 6:    # 일요일: 07:00 이후 개장
            return hm >= 700

        # 평일: 06:00~07:00 만 마감 (일일 유지보수)
        return not (600 <= hm < 700)
