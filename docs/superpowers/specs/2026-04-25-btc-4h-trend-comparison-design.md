# BTC 4H 추세추종 전략 비교 백테스트 설계

**날짜:** 2026-04-25  
**목적:** "손실을 짧게, 수익은 길게" 원칙 기반의 3가지 추세추종 전략을 BTC 4H 캔들로 비교 백테스트

---

## 1. 목표

- 3가지 추세추종 전략(Donchian, Supertrend, EMA Cross)을 동일 조건으로 백테스트
- 우선순위: 총수익률 > Sharpe Ratio > MDD > 손익비(RR)
- 롱/숏 양방향 운영
- 결과를 표와 에쿼티 커브로 비교

---

## 2. 데이터

- **심볼:** BTC/USDT (Binance Futures)
- **타임프레임:** 4H
- **기간:** 2020-01-01 ~ 현재
- **수집 방법:** ccxt로 fetch 후 CSV 캐싱
- **초기 자본:** $10,000 (비율 비교용)

---

## 3. 공통 조건

- **레버리지:** 1x
- **포지션 사이징:** 가용 현금 전액 / 현재가 (풀포지션)
- **수수료:** 0.04% (Binance Futures taker fee)
- **슬리피지:** 미적용 (보수적 비교를 위해 수수료만 적용)

---

## 4. 전략 상세

### 전략 A — Donchian Channel Breakout

| 항목 | 값 |
|------|-----|
| 진입 기간 | 20봉 |
| 청산 기간 | 10봉 |
| 손절 | ATR(14) × 2.0 |

- **롱 진입:** 종가 > 20봉 최고가
- **숏 진입:** 종가 < 20봉 최저가
- **롱 청산:** 종가 < 10봉 최저가 OR ATR 손절 터치
- **숏 청산:** 종가 > 10봉 최고가 OR ATR 손절 터치
- **반전 진입:** 반대 신호 발생 시 기존 포지션 청산 후 즉시 반대 진입

### 전략 B — Supertrend

| 항목 | 값 |
|------|-----|
| ATR 기간 | 10봉 |
| 배수 | 3.0 |

- **Supertrend 계산:**
  - Basic Upper = (High + Low) / 2 + multiplier × ATR
  - Basic Lower = (High + Low) / 2 - multiplier × ATR
  - Final Band: 전봉 방향 유지 조건으로 갱신
- **롱 진입:** 종가가 Supertrend 선 위로 전환
- **숏 진입:** 종가가 Supertrend 선 아래로 전환
- **청산:** 반전 신호 발생 시 (즉시 반대 진입)

### 전략 C — EMA Cross + ATR Trailing Stop

| 항목 | 값 |
|------|-----|
| 단기 EMA | 9봉 |
| 장기 EMA | 21봉 |
| ATR 기간 | 14봉 |
| 트레일링 배수 | 3.0 |

- **롱 진입:** EMA9 > EMA21 골든크로스
- **숏 진입:** EMA9 < EMA21 데드크로스
- **롱 청산:** 포지션 중 최고가 - ATR × 3 이하로 종가 하락
- **숏 청산:** 포지션 중 최저가 + ATR × 3 이상으로 종가 상승
- **반전:** 크로스 신호 발생 시 기존 포지션 청산 후 반대 진입

---

## 5. 평가 지표

| 지표 | 설명 |
|------|------|
| 총수익률 (%) | 전체 기간 수익률 |
| Sharpe Ratio | 연환산 (rf=0) |
| MDD (%) | 최대 낙폭 |
| 승률 (%) | 수익 거래 / 전체 거래 |
| 손익비 (RR) | 평균 수익 / 평균 손실 |
| 거래 횟수 | 전체 체결 횟수 |

---

## 6. 파일 구조

```
backtestStrategy/
  DonchianStrategy.py    # 전략 A
  SupertrendStrategy.py  # 전략 B
  EMACrossStrategy.py    # 전략 C

backtest_compare_btc.py  # 비교 실행 스크립트 (루트)
```

---

## 7. 실행 스크립트 (`backtest_compare_btc.py`)

1. ccxt로 BTC/USDT 4H 데이터 fetch → DataFrame 변환
2. 세 전략을 동일 데이터로 순차 실행 (backtrader Cerebro)
3. Analyzer: `SharpeRatio`, `DrawDown`, `TradeAnalyzer` 공통 부착
4. 결과 pandas DataFrame으로 집계 후 표 출력
5. matplotlib로 에쿼티 커브 3개 겹쳐서 출력

---

## 8. 출력 예시

```
전략            총수익률   Sharpe   MDD      승률    손익비   거래횟수
DonchianBreakout  +245%    1.23    -32%    38%     3.2x     87
Supertrend        +310%    1.45    -28%    42%     2.8x     64
EMACrossTrailing  +198%    1.10    -35%    45%     2.1x     112
```

에쿼티 커브 그래프 (`equity_comparison.png`) 저장
