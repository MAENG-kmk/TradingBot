import backtrader as bt
import numpy as np
from xgboost import XGBClassifier


class XGBoostStrategy(bt.Strategy):
    """
    XGBoost 기반 매매 전략

    기술적 지표(EMA, RSI, MACD, Bollinger, ATR)를 피처로 사용하여
    XGBoost가 롱/숏/관망을 예측한다.

    - 학습: 처음 train_period 봉 동안 지표 + 미래 수익률로 학습
    - 예측: 학습 후 매 봉마다 매매 신호 예측
    - 리스크 관리: ATR 기반 손절 + 익절 + Trailing Stop
    """
    params = dict(
        train_period=300,       # 학습에 사용할 봉 수
        retrain_interval=100,   # 재학습 주기 (봉 수)
        forward_period=5,       # 미래 N봉 후 수익률로 라벨링
        threshold=0.02,         # 라벨링 기준 수익률 (2%)
        atr_period=14,
        atr_multiplier=2.0,
        take_profit_pct=0.07,
        trailing_stop_pct=0.02,
        risk_percent=0.02,
        predict_proba_threshold=0.6,  # 예측 확률 임계값
    )

    def __init__(self):
        # 지표 설정
        self.ema10 = bt.ind.EMA(self.data.close, period=10)
        self.ema30 = bt.ind.EMA(self.data.close, period=30)
        self.rsi = bt.ind.RSI(self.data.close, period=14)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        self.macd = bt.ind.MACD(self.data.close)
        self.bb = bt.ind.BollingerBands(self.data.close, period=20, devfactor=2)
        self.sma50 = bt.ind.SMA(self.data.close, period=50)

        # 모델 및 상태
        self.model = None
        self.bar_count = 0
        self.is_trained = False

        # 포지션 관리
        self.entry_price = 0
        self.stop_loss = 0
        self.take_profit = 0
        self.highest_price = 0
        self.lowest_price = 0

    def _get_features(self, idx=0):
        """현재 봉의 피처 벡터 생성"""
        close = self.data.close[idx]
        if close == 0:
            return None

        features = [
            # EMA 관련
            (self.ema10[idx] - self.ema30[idx]) / close,           # EMA 차이 비율
            (close - self.ema10[idx]) / close,                      # 가격-EMA10 괴리율
            (close - self.ema30[idx]) / close,                      # 가격-EMA30 괴리율
            (close - self.sma50[idx]) / close,                      # 가격-SMA50 괴리율

            # RSI
            self.rsi[idx] / 100.0,                                  # RSI 정규화

            # MACD
            self.macd.lines.macd[idx],                              # MACD 값
            self.macd.lines.signal[idx],                            # Signal 값
            self.macd.lines.macd[idx] - self.macd.lines.signal[idx], # MACD 히스토그램

            # Bollinger Bands
            (close - self.bb.lines.mid[idx]) / (self.bb.lines.top[idx] - self.bb.lines.bot[idx] + 1e-10),  # BB 위치
            (self.bb.lines.top[idx] - self.bb.lines.bot[idx]) / close,  # BB 폭 비율

            # ATR
            self.atr[idx] / close,                                  # ATR 비율 (변동성)

            # 가격 변화율
            (close - self.data.close[idx - 1]) / self.data.close[idx - 1] if self.data.close[idx - 1] != 0 else 0,
            (close - self.data.close[idx - 3]) / self.data.close[idx - 3] if self.data.close[idx - 3] != 0 else 0,
            (close - self.data.close[idx - 5]) / self.data.close[idx - 5] if self.data.close[idx - 5] != 0 else 0,

            # 거래량 변화율
            (self.data.volume[idx] / (self.data.volume[idx - 1] + 1e-10)) - 1,
        ]
        return features

    def _collect_training_data(self):
        """학습 데이터 수집: 과거 지표 + 미래 수익률 기반 라벨"""
        X, y = [], []
        fp = self.p.forward_period

        for i in range(-self.p.train_period, -fp):
            features = self._get_features(idx=i)
            if features is None or any(np.isnan(features)):
                continue

            # 미래 수익률 기반 라벨링: 0=숏, 1=관망, 2=롱
            future_return = (self.data.close[i + fp] - self.data.close[i]) / self.data.close[i]
            if future_return > self.p.threshold:
                label = 2  # 롱
            elif future_return < -self.p.threshold:
                label = 0  # 숏
            else:
                label = 1  # 관망

            X.append(features)
            y.append(label)

        return np.array(X), np.array(y)

    def _train_model(self):
        """XGBoost 모델 학습"""
        X, y = self._collect_training_data()

        if len(X) < 50:
            return False

        # 클래스가 2개 이상이어야 학습 가능
        unique_classes = np.unique(y)
        if len(unique_classes) < 2:
            return False

        self.model = XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            use_label_encoder=False,
            eval_metric='mlogloss',
            verbosity=0,
        )
        self.model.fit(X, y)
        self.is_trained = True
        return True

    def next(self):
        self.bar_count += 1

        # 학습 단계
        if not self.is_trained and self.bar_count >= self.p.train_period + self.p.forward_period:
            if self._train_model():
                print(f'[XGBoost] 모델 학습 완료 (bar: {self.bar_count})')

        # 주기적 재학습
        if self.is_trained and self.bar_count % self.p.retrain_interval == 0:
            self._train_model()

        if not self.is_trained:
            return

        # 현재 피처로 예측
        features = self._get_features(idx=0)
        if features is None or any(np.isnan(features)):
            return

        X_pred = np.array([features])
        prediction = self.model.predict(X_pred)[0]
        proba = self.model.predict_proba(X_pred)[0]

        # 포지션이 없을 때 → 진입
        if not self.position:
            # 롱 진입: 예측=2(롱) & 확률 >= 임계값
            if prediction == 2 and proba[self.model.classes_.tolist().index(2)] >= self.p.predict_proba_threshold:
                atr_value = self.atr[0]
                self.stop_loss = self.data.close[0] - (atr_value * self.p.atr_multiplier)
                self.take_profit = self.data.close[0] * (1 + self.p.take_profit_pct)

                cash = self.broker.get_cash()
                risk_amount = cash * self.p.risk_percent
                risk_per_unit = self.data.close[0] - self.stop_loss
                size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0

                if size > 0:
                    self.buy(size=size)
                    self.entry_price = self.data.close[0]
                    self.highest_price = self.data.close[0]

            # 숏 진입: 예측=0(숏) & 확률 >= 임계값
            elif prediction == 0 and proba[self.model.classes_.tolist().index(0)] >= self.p.predict_proba_threshold:
                atr_value = self.atr[0]
                self.stop_loss = self.data.close[0] + (atr_value * self.p.atr_multiplier)
                self.take_profit = self.data.close[0] * (1 - self.p.take_profit_pct)

                cash = self.broker.get_cash()
                risk_amount = cash * self.p.risk_percent
                risk_per_unit = self.stop_loss - self.data.close[0]
                size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0

                if size > 0:
                    self.sell(size=size)
                    self.entry_price = self.data.close[0]
                    self.lowest_price = self.data.close[0]

        # 포지션이 있을 때 → 청산 관리
        else:
            if self.position.size > 0:  # 롱
                if self.data.close[0] > self.highest_price:
                    self.highest_price = self.data.close[0]
                    self.stop_loss = max(self.stop_loss,
                                         self.highest_price * (1 - self.p.trailing_stop_pct))

                if self.data.close[0] < self.stop_loss:
                    self.close()
                elif self.data.close[0] > self.take_profit:
                    self.close()

            elif self.position.size < 0:  # 숏
                if self.data.close[0] < self.lowest_price:
                    self.lowest_price = self.data.close[0]
                    self.stop_loss = min(self.stop_loss,
                                         self.lowest_price * (1 + self.p.trailing_stop_pct))

                if self.data.close[0] > self.stop_loss:
                    self.close()
                elif self.data.close[0] < self.take_profit:
                    self.close()
