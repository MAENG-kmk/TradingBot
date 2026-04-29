# KIS 선물 자동매매 통합 구현 설계

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 한국투자증권(KIS) API를 통해 국내선물·해외선물 자동매매를 기존 암호화폐 봇 위에 추가한다.

**Architecture:** 공유 KIS 클라이언트(`kis/client.py`) + 독립 시장 모듈(`domestic_futures/`, `overseas_futures/`). 기존 코인봇 코드는 변경하지 않고, `main.py` 루프에 두 runner를 추가하는 것으로 통합한다.

**Tech Stack:** Python, KIS OpenAPI REST, pandas, numpy, 기존 tools/trendFilter.py 레짐 필터

---

## 1. 파일 구조

```
TradingBot/
├── kis/
│   ├── __init__.py
│   └── client.py                  # KIS REST 클라이언트 + 토큰 관리
│
├── domestic_futures/
│   ├── __init__.py
│   ├── base_strategy.py           # BaseDomesticFuturesStrategy
│   ├── scanner.py                 # 국내선물 종목 스캔 + ADX 랭킹
│   └── runner.py                  # 장 시간 체크 + 포지션 5개 관리
│
├── overseas_futures/
│   ├── __init__.py
│   ├── base_strategy.py           # BaseOverseasFuturesStrategy
│   ├── scanner.py                 # 해외선물 종목 스캔 + ADX 랭킹
│   └── runner.py                  # 장 시간 체크 + 포지션 5개 관리
│
├── SecretVariables.py             # KIS_APP_KEY, KIS_APP_SECRET 추가
└── main.py                        # domestic_runner, overseas_runner 추가
```

---

## 2. KIS 클라이언트 (`kis/client.py`)

### 책임
- OAuth2 토큰 발급 및 메모리 캐싱
- 만료 5분 전 자동 갱신
- GET / POST 요청 래핑 (헤더 자동 주입)

### 인터페이스
```python
class KISClient:
    BASE_URL = "https://openapi.koreainvestment.com:9443"

    def __init__(self, app_key: str, app_secret: str): ...
    def get(self, path: str, tr_id: str, params: dict) -> dict: ...
    def post(self, path: str, tr_id: str, body: dict) -> dict: ...
```

### 자동 주입 헤더
```
Authorization: Bearer {access_token}
appkey: {app_key}
appsecret: {app_secret}
tr_id: {tr_id}
Content-Type: application/json
```

### 토큰 발급
- `POST /oauth2/tokenP`
- body: `{ grant_type, appkey, appsecret }`
- 응답: `access_token`, `expires_in` (86400초)

---

## 3. SecretVariables.py 추가

```python
KIS_APP_KEY    = "PSzhYRWCD3gA2RiPEA6meJQuqZYLb3OD5C7d"
KIS_APP_SECRET = "a+UTB0ZU..."   # 전체 시크릿
```

---

## 4. 스캐너

### 공통 동작
```
scan(limit) 흐름:
  1. KIS API → 화이트리스트 종목 목록
  2. 각 종목 4H 캔들 조회 (limit=300)
  3. checkMarketRegime() → regime + ADX 계산
  4. 현재 보유 포지션 종목 제외
  5. ADX 내림차순 정렬 → 상위 limit개 반환
```

### 국내선물 화이트리스트 (유동성 상위)
코스피200 선물, 미니코스피200 선물, 코스닥150 선물, 3년국채선물, 10년국채선물, 달러선물, 엔선물, 유로선물 (약 8~10종목)

### 해외선물 화이트리스트 (CME 주요)
ES (S&P500 E-mini), NQ (NASDAQ E-mini), CL (WTI 원유), GC (금), SI (은), 6E (유로FX), 6J (엔), RTY (Russell 2000) (약 10~15종목)

### 인터페이스
```python
class DomesticFuturesScanner:
    def __init__(self, kis: KISClient, strategy: BaseDomesticFuturesStrategy): ...
    def scan(self, current_symbols: list[str], limit: int) -> list[str]: ...
        # ADX 상위 limit개 종목코드 반환

class OverseasFuturesScanner:
    def __init__(self, kis: KISClient, strategy: BaseOverseasFuturesStrategy): ...
    def scan(self, current_symbols: list[str], limit: int) -> list[str]: ...
```

---

## 5. 전략 (`base_strategy.py`)

### 기존 코인봇과 동일한 파라미터
```python
TR_BB_PERIOD = 20
TR_BB_STD    = 2.0
RSI_OVERBUY  = 80
RSI_OVERSELL = 20
ADX_THRESHOLD = 20
VB_K          = 0.3
VB_MIN_RANGE_PCT = 0.3
TRAILING_RATIO      = 0.6
TIGHT_TRAILING_RATIO = 0.75
DEFAULT_TARGET_ROR   = 10.0
```

### 레짐 분기 (기존과 동일)
```
checkMarketRegime() → uptrend/downtrend → _trend_following_signal()
                    → ranging           → _vb_signal()
```

### 서브클래스가 구현하는 메서드
```python
def get_candles(self, symbol: str, limit: int = 300) -> pd.DataFrame: ...
    # KIS API 호출 → Open/High/Low/Close/Volume DataFrame

def place_order(self, symbol: str, side: str, qty: int) -> bool: ...
    # side: 'BUY' | 'SELL'

def get_balance(self) -> tuple[float, float]: ...
    # (total, available) 원화

def get_positions(self) -> list[dict]: ...
    # [{'symbol': ..., 'side': ..., 'qty': ..., 'entry_price': ...}]

def calc_quantity(self, budget: float, price: float) -> int: ...
    # 계약 수 (정수) = floor(budget / (price × 계약승수))
    # 계약승수: 코스피200선물=250,000원, ES=50USD 등 종목별 고정값
    # 종목별 승수는 각 base_strategy에 상수로 정의
```

### 포지션 상태 관리
코인봇과 동일하게 MongoDB에 저장:
- `saveEntryDetails(symbol, mode, side, price)`
- `getEntryDetails(symbol)`
- `deleteEntryDetails(symbol)`

---

## 6. Runner

### 공통 구조
```python
class DomesticFuturesRunner:
    MAX_POSITIONS = 5
    POSITION_FRAC = 0.1   # 총잔고의 10%

    def run(self):
        positions = self.strategy.get_positions()
        self._manage_exits(positions)          # 청산은 항상

        if not self._is_market_open():
            return                             # 장 마감 시 진입 없음

        empty = self.MAX_POSITIONS - len(positions)
        if empty <= 0:
            return

        held = [p['symbol'] for p in positions]
        candidates = self.scanner.scan(held, limit=empty)
        total, available = self.strategy.get_balance()

        for symbol in candidates:
            self._try_enter(symbol, total, available)
```

### 장 시간 (KST 기준)
**국내선물:**
- 주간: 09:00 ~ 15:45
- 야간: 18:00 ~ 익일 05:00
- 주말 야간 없음 (금요일 15:45 ~ 월요일 09:00 진입 차단)

**해외선물 (CME):**
- 월~금: 07:00 ~ 익일 06:00 (약 23시간)
- 주말: 일요일 07:00 개장 / 토요일 06:00 마감

### 청산 로직 (`_manage_exits`)
코인봇의 4단계 트레일링 스탑과 동일:
1. Phase 1: 고정 손절 (ATR 기반)
2. Phase 2: 본전 확보 (+3% 이상 시 손절 → +0.5%)
3. Phase 3: 트레일링 시작 (+6% 이상, 최고점의 60%)
4. Phase 4: 타이트 트레일링 (목표 ROR 이상, 최고점의 75%)

---

## 7. main.py 변경

```python
# 추가 import
from kis.client import KISClient
from domestic_futures.runner import DomesticFuturesRunner
from overseas_futures.runner import OverseasFuturesRunner
from SecretVariables import KIS_APP_KEY, KIS_APP_SECRET

# 초기화 추가
kis_client       = KISClient(KIS_APP_KEY, KIS_APP_SECRET)
domestic_runner  = DomesticFuturesRunner(kis_client)
overseas_runner  = OverseasFuturesRunner(kis_client)

# run_trading_bot() 루프 내 추가 (기존 코인 루프 이후)
domestic_runner.run()
overseas_runner.run()
```

기존 코인봇 코드는 변경 없음.

---

## 8. 오류 처리

- KIS API 오류(토큰 만료, 네트워크) → `KISClient`에서 예외 raise → runner에서 catch → 텔레그램 알림 후 skip
- 종목 데이터 부족(캔들 < 50개) → 해당 종목 skip
- 주문 실패 → 텔레그램 알림, 상태 저장 안 함

---

## 9. 범위 외 (이번 구현 제외)

- 웹소켓 실시간 시세
- 옵션(option) 거래
- 백테스트 연동
- 종목별 파라미터 최적화 (4H 기준 추후 백테스트로 조정)
