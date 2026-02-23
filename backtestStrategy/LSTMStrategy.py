import backtrader as bt
import numpy as np
import os

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import tensorflow as tf
from tensorflow import keras


class LSTMStrategy(bt.Strategy):
    """
    LSTM 기반 매매 전략

    과거 lookback 봉의 피처(가격변화율, 거래량변화율, 기술적 지표)를
    LSTM에 입력하여 미래 가격 방향을 예측한다.

    - 학습: 처음 train_period 봉 동안 시퀀스 데이터로 학습
    - 예측: 학습/재학습 시 남은 구간을 배치로 한 번에 예측 (성능 최적화)
    - 리스크 관리: ATR 기반 손절 + 익절 + Trailing Stop
    """
    params = dict(
        train_period=400,       # 학습에 사용할 봉 수
        retrain_interval=200,   # 재학습 주기
        lookback=20,            # LSTM 입력 시퀀스 길이
        forward_period=5,       # 미래 N봉 후 수익률로 라벨링
        threshold=0.02,         # 라벨링 기준 수익률 (2%)
        lstm_units=64,
        epochs=30,
        batch_size=32,
        atr_period=14,
        atr_multiplier=2.0,
        take_profit_pct=0.07,
        trailing_stop_pct=0.02,
        risk_percent=0.02,
        predict_threshold=0.6,  # 예측 확률 임계값
    )

    def __init__(self):
        # 지표 설정
        self.ema10 = bt.ind.EMA(self.data.close, period=10)
        self.ema30 = bt.ind.EMA(self.data.close, period=30)
        self.rsi = bt.ind.RSI(self.data.close, period=14)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        self.macd = bt.ind.MACD(self.data.close)
        self.bb = bt.ind.BollingerBands(self.data.close, period=20, devfactor=2)

        # 모델 및 상태
        self.model = None
        self.bar_count = 0
        self.is_trained = False
        self.feature_mean = None
        self.feature_std = None

        # 배치 예측 캐시: {bar_count: (prediction, proba)}
        self.prediction_cache = {}

        # 포지션 관리
        self.entry_price = 0
        self.stop_loss = 0
        self.take_profit = 0
        self.highest_price = 0
        self.lowest_price = 0

    def _get_features(self, idx=0):
        """단일 봉의 피처 벡터 생성 (10개 피처)"""
        close = self.data.close[idx]
        prev_close = self.data.close[idx - 1]
        if close == 0 or prev_close == 0:
            return None

        bb_width = self.bb.lines.top[idx] - self.bb.lines.bot[idx]

        features = [
            (close - prev_close) / prev_close,
            (self.data.volume[idx] / (self.data.volume[idx - 1] + 1e-10)) - 1,
            (self.ema10[idx] - self.ema30[idx]) / close,
            (close - self.ema10[idx]) / close,
            self.rsi[idx] / 100.0,
            self.macd.lines.macd[idx] - self.macd.lines.signal[idx],
            (close - self.bb.lines.mid[idx]) / (bb_width + 1e-10),
            bb_width / close,
            self.atr[idx] / close,
            (self.data.high[idx] - self.data.low[idx]) / close,
        ]
        return features

    def _build_sequences(self, start_idx, end_idx):
        """학습용 시퀀스 데이터 생성"""
        all_features = []
        for i in range(start_idx, end_idx):
            f = self._get_features(idx=i)
            if f is None:
                return None, None
            all_features.append(f)

        all_features = np.array(all_features)

        self.feature_mean = np.mean(all_features, axis=0)
        self.feature_std = np.std(all_features, axis=0) + 1e-10
        all_features = (all_features - self.feature_mean) / self.feature_std

        X, y = [], []
        lb = self.p.lookback
        fp = self.p.forward_period

        for i in range(lb, len(all_features) - fp):
            seq = all_features[i - lb:i]
            X.append(seq)

            actual_idx = start_idx + i
            future_return = (self.data.close[actual_idx + fp] - self.data.close[actual_idx]) / self.data.close[actual_idx]

            if future_return > self.p.threshold:
                y.append(2)
            elif future_return < -self.p.threshold:
                y.append(0)
            else:
                y.append(1)

        if len(X) == 0:
            return None, None

        return np.array(X), np.array(y)

    def _build_model(self, n_features):
        """LSTM 모델 구축"""
        model = keras.Sequential([
            keras.layers.LSTM(
                self.p.lstm_units,
                input_shape=(self.p.lookback, n_features),
                return_sequences=True,
            ),
            keras.layers.Dropout(0.3),
            keras.layers.LSTM(32),
            keras.layers.Dropout(0.3),
            keras.layers.Dense(16, activation='relu'),
            keras.layers.Dense(3, activation='softmax'),
        ])
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=0.001),
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy'],
        )
        return model

    def _train_model(self):
        """LSTM 모델 학습"""
        tp = self.p.train_period
        fp = self.p.forward_period

        X, y = self._build_sequences(-tp - fp, -fp)
        if X is None or len(X) < 50:
            return False

        unique_classes = np.unique(y)
        if len(unique_classes) < 2:
            return False

        n_features = X.shape[2]
        self.model = self._build_model(n_features)

        self.model.fit(
            X, y,
            epochs=self.p.epochs,
            batch_size=self.p.batch_size,
            verbose=0,
            validation_split=0.1,
        )
        self.is_trained = True
        return True

    def _batch_predict_remaining(self):
        """현재 봉부터 데이터 끝까지 배치 예측하여 캐시에 저장"""
        lb = self.p.lookback
        total_bars = len(self.data.close)
        current_pos = len(self.data) - 1  # 현재 봉의 절대 인덱스

        # 현재~끝까지 남은 봉 수 계산 (backtrader의 buflen 활용)
        remaining = self.data.buflen() - len(self.data)

        # 남은 구간 + 현재 봉의 피처를 모두 수집
        all_features = []
        bar_indices = []

        for offset in range(0, remaining + 1):
            idx = offset  # 현재=0, 다음=1, ...
            f = self._get_features(idx=idx)
            if f is not None:
                all_features.append(f)
                bar_indices.append(self.bar_count + offset)
            else:
                # None이면 이후 시퀀스 구성 불가 → 여기까지만
                break

        if len(all_features) < lb:
            return

        all_features = np.array(all_features)
        all_features = (all_features - self.feature_mean) / self.feature_std

        # 시퀀스 구성: 과거 lookback 봉의 피처가 필요하므로 과거 데이터도 포함
        past_features = []
        for i in range(-lb + 1, 0):
            f = self._get_features(idx=i)
            if f is None:
                return
            past_features.append(f)

        past_features = np.array(past_features)
        past_features = (past_features - self.feature_mean) / self.feature_std

        combined = np.concatenate([past_features, all_features], axis=0)

        # 시퀀스 생성
        X_batch = []
        valid_bar_indices = []
        for i in range(lb - 1, lb - 1 + len(all_features)):
            seq = combined[i - lb + 1:i + 1]
            if len(seq) == lb:
                X_batch.append(seq)
                valid_bar_indices.append(bar_indices[i - (lb - 1)])

        if len(X_batch) == 0:
            return

        X_batch = np.array(X_batch)

        # 배치 예측 (한 번의 호출로 전체 예측)
        probas = self.model.predict(X_batch, verbose=0, batch_size=256)

        # 캐시에 저장
        self.prediction_cache = {}
        for idx, proba in zip(valid_bar_indices, probas):
            pred = np.argmax(proba)
            self.prediction_cache[idx] = (pred, proba)

    def _train_and_predict(self):
        """학습 후 배치 예측"""
        if self._train_model():
            print(f'[LSTM] 모델 학습 완료 (bar: {self.bar_count})')
            self._batch_predict_remaining()
            return True
        return False

    def next(self):
        self.bar_count += 1

        # 학습 단계
        min_bars = self.p.train_period + self.p.forward_period + self.p.lookback
        if not self.is_trained and self.bar_count >= min_bars:
            self._train_and_predict()

        # 주기적 재학습
        if self.is_trained and self.bar_count % self.p.retrain_interval == 0:
            self._train_and_predict()

        if not self.is_trained:
            return

        # 캐시에서 예측 결과 조회
        cached = self.prediction_cache.get(self.bar_count)
        if cached is None:
            return
        prediction, proba = cached

        # 포지션이 없을 때 → 진입
        if not self.position:
            # 롱 진입
            if prediction == 2 and proba[2] >= self.p.predict_threshold:
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

            # 숏 진입
            elif prediction == 0 and proba[0] >= self.p.predict_threshold:
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
