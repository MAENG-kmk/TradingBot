from tools.trendFilter import checkMarketRegime

# 유동성 상위 국내선물 상품 prefix (만기월 무관)
# KIS 종목코드는 앞 3자리가 상품 구분
DOMESTIC_WHITELIST_PREFIX = {
    "101": "코스피200선물",
    "105": "미니코스피200선물",
    "106": "코스닥150선물",
    "167": "3년국채선물",
    "175": "10년국채선물",
    "196": "달러선물",
    "197": "엔선물",
    "198": "유로선물",
}

# ⚠️ 활성 종목 조회 TR_ID: KIS API 포털 → 국내선물옵션 → 기본정보 → 종목 마스터 확인 필요
_TR_MASTER = "FHMIF10000000"


class DomesticFuturesScanner:
    def __init__(self, kis, strategy):
        self.kis      = kis
        self.strategy = strategy

    def get_active_symbols(self) -> list[str]:
        """KIS에서 현재 활성 국내선물 종목코드 목록 조회 (화이트리스트 prefix만 반환)"""
        try:
            data = self.kis.get(
                "/uapi/domestic-futureoption/v1/quotations/inquire-futureoption-list",
                _TR_MASTER,
                {"FID_COND_MRKT_DIV_CODE": "F", "FID_COND_SCR_DIV_CODE": "20"},
            )
            symbols = []
            for item in data.get("output", []):
                code = item.get("shtn_pdno", "")
                if code[:3] in DOMESTIC_WHITELIST_PREFIX:
                    symbols.append(code)
            return symbols
        except Exception as e:
            print(f"  [국내선물] 종목 목록 조회 오류: {e}")
            return []

    def scan(self, current_symbols: list[str], limit: int) -> list[str]:
        """
        ADX 상위 limit개 종목 반환.
        Args:
            current_symbols: 이미 보유 중인 종목코드 목록 (제외 대상)
            limit: 반환할 최대 종목 수
        Returns:
            진입 후보 종목코드 리스트 (ADX 내림차순)
        """
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
