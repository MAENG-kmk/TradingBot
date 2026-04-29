# overseas_futures/scanner.py
from tools.trendFilter import checkMarketRegime

# CME 주요 선물 화이트리스트 (KIS 종목코드 형식 확인 필요)
# ⚠️ 정확한 형식은 KIS API 포털 → 해외선물 종목 마스터 확인
OVERSEAS_WHITELIST = [
    "ES",   # S&P500 E-mini (CME)
    "NQ",   # NASDAQ E-mini (CME)
    "CL",   # WTI 원유 (NYMEX)
    "GC",   # 금 (COMEX)
    "SI",   # 은 (COMEX)
    "6E",   # 유로FX (CME)
    "6J",   # 엔FX (CME)
    "RTY",  # Russell 2000 E-mini (CME)
]

_TR_MASTER = "HHDFS76200000"  # 해외선물 종목 마스터 (확인 필요)


class OverseasFuturesScanner:
    def __init__(self, kis, strategy):
        self.kis      = kis
        self.strategy = strategy

    def get_active_symbols(self) -> list[str]:
        """
        KIS 해외선물 활성 종목 조회 → 화이트리스트 기준 필터링.
        API 오류 시 화이트리스트 직접 반환 (폴백).
        """
        try:
            data = self.kis.get(
                "/uapi/overseas-futureoption/v1/quotations/inquire-futureoption-list",
                _TR_MASTER,
                {"FID_COND_MRKT_DIV_CODE": "Q", "FID_COND_SCR_DIV_CODE": "20",
                 "FID_OVRS_EXCG_CD": "CME"},
            )
            symbols = []
            for item in data.get("output", []):
                code = item.get("shtn_pdno", "")
                for ticker in OVERSEAS_WHITELIST:
                    if code.startswith(ticker):
                        symbols.append(code)
                        break
            return symbols if symbols else OVERSEAS_WHITELIST
        except Exception as e:
            print(f"  [해외선물] 종목 목록 조회 오류: {e} — 화이트리스트 직접 사용")
            return OVERSEAS_WHITELIST

    def scan(self, current_symbols: list[str], limit: int) -> list[str]:
        if limit <= 0:
            return []
        active     = self.get_active_symbols()
        candidates = []
        for symbol in active:
            if symbol in current_symbols:
                continue
            df = self.strategy.get_candles(symbol, limit=100)
            if df is None or len(df) < 50:
                continue
            try:
                _, adx, _ = checkMarketRegime(df, adx_threshold=self.strategy.ADX_THRESHOLD)
                sig, _, _, _ = self.strategy.check_entry_signal(symbol)
                if sig is not None:
                    candidates.append((symbol, adx))
            except Exception:
                continue
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [sym for sym, _ in candidates[:limit]]
