# 쌍 거래(Pair Trading) 헷징 전략

## 개요
두 코인을 각각 롱/숏 진입하여 상관관계 오차를 이용한 헷징 전략. 시장 방향성 제거로 변동성을 줄이고 일정한 수익을 추구하는 중립 전략(Market Neutral Strategy).

---

## 1️⃣ 전략의 원리

### 상관관계 기반 쌍 거래
높은 상관관계를 가진 2개 코인을 이용하여 상관관계 오차에서 수익 창출:

**예시:**
- **BTC 롱 + ETH 숏** (상관관계 0.85~0.95)
  - BTC가 오르면 → BTC 수익 + ETH 손실 (상쇄)
  - 상관관계 오차 → 순이익 발생

### 통계적 중재 (Statistical Arbitrage)
두 코인 가격 차이의 평균회귀(Mean Reversion) 활용:

```
스프레드 = BTC 가격 - (ETH 가격 × 가중치)

- 스프레드가 평균 + 2σ → 롱 스프레드 (BTC 롱 + ETH 숏)
- 스프레드가 평균 - 2σ → 숏 스프레드 (BTC 숏 + ETH 롱)
```

---

## 2️⃣ 장점

| 항목 | 설명 |
|------|------|
| **시장 방향성 제거** | 장/단 시장 구분 없이 수익 가능 |
| **변동성 감소** | 두 자산의 변동성 상쇄 |
| **승률 향상** | 방향성 거래보다 높은 승률 기대 |
| **리스크 감소** | 시스템 리스크 헷지 |
| **분산 투자** | 두 개 자산 모니터링 |

---

## 3️⃣ 단점 및 리스크

| 리스크 | 설명 | 영향 |
|-------|------|------|
| **상관관계 붕괴** | 위기 시 모든 자산이 함께 떨어짐 | 높음 |
| **수수료 × 2** | 두 개 거래의 수수료 지불 | 중간 |
| **롤링 리스크** | 선물 계약 만기 (quarterly futures) | 낮음 |
| **양방향 손실** | 쌍이 모두 반대로 움직임 | 높음 |
| **레버리지 위험** | 양쪽 모두 증거금 필요 | 높음 |

---

## 4️⃣ 코인 쌍의 선택 기준

### 선택 조건

| 기준 | 최적 범위 | 피해야 할 것 |
|------|----------|-----------|
| **상관관계** | 0.80 이상 | 0.50 이하 |
| **유동성** | 상위 10위 내 | 소형 코인 |
| **일일 변동성** | 20~50% 연 변동성 | 매우 높거나 낮음 |
| **거래량** | 시간당 수억 $이상 | 거래량 적음 |
| **시가총액** | $10B 이상 | $1B 이하 |

### 추천 쌍

| 쌍 | 상관관계 | 추천도 | 설명 |
|----|---------|--------|------|
| BTC + ETH | 0.90~0.95 | ⭐⭐⭐⭐⭐ | 가장 안정적, 유동성 최고 |
| SOL + MATIC | 0.75~0.85 | ⭐⭐⭐⭐ | 좋은 유동성, 중간 상관관계 |
| BNB + ADA | 0.70~0.80 | ⭐⭐⭐ | 상관관계 약함 |
| XRP + DOGE | 0.60~0.70 | ⭐⭐ | 낮은 상관관계, 비추천 |

---

## 5️⃣ 수익 메커니즘

### 시나리오별 분석

**가정:**
- BTC: $44,000, ETH: $2,200
- 각각 1단위씩 거래 (BTC 롱 + ETH 숏)

#### 시나리오 1: 정상 (같은 비율로 움직임)
```
BTC: +10% → +$4,400 수익
ETH: +10% → -$220 손실
순 수익: +$4,180 ✅
```

#### 시나리오 2: 상관관계 오차 (상이한 움직임)
```
BTC: +10% → +$4,400 수익
ETH: -5% → +$110 수익 (숏이므로)
순 수익: +$4,510 ✅ (상관관계 오차 활용)
```

#### 시나리오 3: 상관관계 붕괴 (반대 움직임)
```
BTC: +10% → +$4,400 수익
ETH: +15% → -$330 손실 (숏이므로)
순 손실: +$4,070 (여전히 수익이지만 기대보다 낮음)
```

#### 시나리오 4: 위기 (양쪽 모두 하락)
```
BTC: -15% → -$6,600 손실
ETH: -15% → +$330 수익 (숏이므로)
순 손실: -$6,270 ❌ (헷징 실패)
```

---

## 6️⃣ 구현 방향

### 의사코드

```python
def pair_trading_logic():
    coin1, coin2 = "BTCUSDT", "ETHUSDT"
    
    # 1. 상관관계 계산 (60일 기준)
    correlation = calculate_correlation(coin1, coin2, lookback=60)
    
    if correlation < 0.75:
        print("상관관계 낮음 - 거래 스킵")
        return
    
    # 2. 스프레드 계산
    spread = calculate_spread(coin1, coin2)
    spread_mean = moving_average(spread, 20)
    spread_std = standard_deviation(spread, 20)
    
    # Z-Score 계산
    spread_zscore = (spread - spread_mean) / spread_std
    
    # 3. 진입 신호
    if spread_zscore > 2.0:  # 스프레드 과다
        long_position(coin1)
        short_position(coin2)
        position_info = {"side": "long_spread", "entry_zscore": spread_zscore}
        
    elif spread_zscore < -2.0:  # 스프레드 과소
        short_position(coin1)
        long_position(coin2)
        position_info = {"side": "short_spread", "entry_zscore": spread_zscore}
    
    # 4. 청산: 스프레드가 평균으로 복귀
    if abs(spread_zscore) < 0.5:
        close_both_positions()
        return True  # 청산 완료
    
    # 5. 손절매: 상관관계 붕괴 또는 손실 한계 도달
    if correlation < 0.70 or loss_pct < -5%:
        close_both_positions()
        return False  # 손절매
    
    return None  # 유지
```

### 구현 체크리스트

- [ ] 상관관계 계산 함수 작성
- [ ] 스프레드 계산 함수 작성
- [ ] Z-Score 기반 진입 로직
- [ ] 동시 청산 메커니즘 (한 개 실패 시 다른 하나도 즉시 청산)
- [ ] 상관관계 모니터링 및 위험 경고
- [ ] 포지션 크기 동적 조정
- [ ] 백테스트 환경 구성

---

## 7️⃣ 실제 구현 플랫폼

### Binance Futures
- 높은 유동성
- 영구 선물 (Perpetual Futures)
- 레버리지 거래 가능
- **추천:** Binance Margin + Futures 조합

### Bybit
- 빠른 거래 실행
- 좋은 API
- 24/7 지원

### OKX
- 다양한 선물 옵션
- 깊은 오더북

---

## 8️⃣ 리스크 관리 전략

### 포지션 크기 결정

```
각 포지션 크기 = 계정 잔액 × 2% / 2 = 계정 잔액 × 1%

예) 계정 잔액 $10,000
- BTC 롱: $100 (계정의 1%)
- ETH 숏: $100 (계정의 1%)
- 총 마진 사용: $200 (계정의 2%)
```

### Stop Loss 설정

| 조건 | Stop Loss | 설명 |
|------|-----------|------|
| **상관관계 < 0.70** | 즉시 청산 | 전략 기초 붕괴 |
| **스프레드 반대 2σ 이상** | 즉시 청산 | 전략 역방향 |
| **누적 손실 > -3%** | 자동 청산 | 위험 한계 |
| **개별 포지션 손실 > -5%** | 양쪽 청산 | 한쪽 실패 시 다른 한쪽도 청산 |

### 상관관계 모니터링

```python
def monitor_correlation(coin1, coin2):
    current_correlation = calculate_correlation(coin1, coin2, lookback=30)
    
    if current_correlation < 0.70:
        send_alert("상관관계 급락 - 포지션 정리 권장")
        close_all_positions()
    elif current_correlation < 0.75:
        send_warning("상관관계 저하 중")
    
    log_correlation(current_correlation)
```

---

## 9️⃣ 성과 측정

### 핵심 지표

| 지표 | 설명 | 목표 |
|------|------|------|
| **Sharpe Ratio** | 위험 대비 수익률 | > 1.5 |
| **Maximum Drawdown** | 최대 낙폭 | < 10% |
| **Win Rate** | 거래 승률 | > 55% |
| **Profit Factor** | 총수익 / 총손실 | > 1.5 |
| **Correlation Stability** | 상관관계 변동성 | < 0.10 |

### 성과 추적

```python
def calculate_performance():
    trades = get_closed_trades()
    
    # 승률
    win_rate = len([t for t in trades if t['profit'] > 0]) / len(trades)
    
    # Profit Factor
    total_profit = sum([t['profit'] for t in trades if t['profit'] > 0])
    total_loss = abs(sum([t['profit'] for t in trades if t['profit'] < 0]))
    profit_factor = total_profit / total_loss
    
    # Sharpe Ratio
    returns = [t['ror'] for t in trades]
    sharpe_ratio = mean(returns) / std(returns) * sqrt(252)  # 연율화
    
    return {
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe_ratio,
        "total_trades": len(trades)
    }
```

---

## 🔟 실행 로드맵

### Phase 1: 준비 (1주)
- [ ] Binance Futures 계정 개설
- [ ] 상관관계 계산 함수 구현
- [ ] 스프레드 분석 도구 개발

### Phase 2: 백테스트 (2주)
- [ ] 1년 이상의 히스토리 데이터 수집
- [ ] 코인 쌍 최적화 (상관관계 높은 순서)
- [ ] 파라미터 최적화 (Z-Score 임계값, 포지션 크기)
- [ ] 다양한 시장 조건 테스트

### Phase 3: 종이 거래 (1주)
- [ ] 실제 시장에서 신호 검증
- [ ] 실행 속도 및 슬리피지 측정
- [ ] 시스템 안정성 확인

### Phase 4: 실전 (진행 중)
- [ ] 작은 규모로 시작 (계정의 1%)
- [ ] 일일 모니터링
- [ ] 월간 성과 분석
- [ ] 지속적 최적화

---

## 🔑 핵심 성공 요소

✅ **반드시 하기:**
1. **상관관계를 정기적으로 모니터링** (매주 1회)
2. **수익률 차이**가 아닌 **상관관계 오차**에서 수익 추구
3. **포지션 크기를 신중하게 설정** (각 포지션 1-2%)
4. **평균회귀 원리** 깊이 있게 이해
5. **동시 청산 메커니즘** 구현 필수

⚠️ **주의할 점:**
- 상관관계가 1.0에 수렴하면 순수 마켓 리스크 노출
- 시장 위기 시 상관관계 붕괴 (2008년, 2020년 3월, 2022년 등)
- 수수료가 수익을 잠식할 수 있음
- 양쪽 거래소/플랫폼 동시 장애 가능성

---

## 📚 참고 자료

### 개념 학습
- "Statistical Arbitrage" - Andrew Pole
- "The Handbook of Pairs Trading" - Mark Whistler
- Mean Reversion Trading Strategies

### 구현 참고
- Binance Futures API Documentation
- Backtrader 쌍 거래 예제
- Quantlib 통계 함수

---

## 📝 작성일
2025-12-22

## 🔄 최근 수정
초안 작성
