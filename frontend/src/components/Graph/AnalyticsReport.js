import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, PieChart, Pie, Legend, ComposedChart, Line,
} from 'recharts';

const tooltipStyle = {
  backgroundColor: '#1a1a2e',
  padding: '10px 14px',
  border: '1px solid rgba(0,255,255,0.3)',
  borderRadius: '8px',
  color: '#e2e2e2',
  fontFamily: 'Orbitron, sans-serif',
  fontSize: '11px',
};

// 월별 실적 툴팁
const MonthlyTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const d = payload[0].payload;
    return (
      <div style={tooltipStyle}>
        <p style={{ color: 'cyan', fontWeight: 'bold', margin: '0 0 6px' }}>{d.month}</p>
        <p style={{ margin: '2px 0' }}>Trades: {d.trades}</p>
        <p style={{ margin: '2px 0' }}>Win Rate: {d.winRate}%</p>
        <p style={{ color: d.profit >= 0 ? '#4CAF50' : '#F44336', margin: '2px 0' }}>
          Profit: {d.profit.toFixed(2)}$
        </p>
      </div>
    );
  }
  return null;
};

// ROR 분포 툴팁
const RorTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const d = payload[0].payload;
    return (
      <div style={tooltipStyle}>
        <p style={{ color: 'cyan', fontWeight: 'bold', margin: '0 0 4px' }}>{d.range}</p>
        <p style={{ margin: '2px 0' }}>Trades: {d.count}</p>
      </div>
    );
  }
  return null;
};

const AnalyticsReport = ({ trades, selectedCoin, startBalance }) => {
  // trades = balanceDatas from History (processed trade objects)
  const stats = useMemo(() => {
    if (!trades || trades.length === 0) return null;

    const profits = trades.map(t => parseFloat(t.Profit));
    const rors = trades.map(t => parseFloat(t.ror)).filter(r => !isNaN(r));
    const wins = profits.filter(p => p > 0);
    const losses = profits.filter(p => p <= 0);

    // 평균 보유 시간
    const holdTimes = trades
      .filter(t => t.enterTime && t.closeTime)
      .map(t => {
        const enter = typeof t.rawEnterTime === 'number' ? t.rawEnterTime : 0;
        const close = typeof t.rawCloseTime === 'number' ? t.rawCloseTime : 0;
        if (enter > 0 && close > 0) {
          // enterTime은 ms, closeTime은 s일 수 있음
          const enterMs = enter > 1e12 ? enter : enter * 1000;
          const closeMs = close > 1e12 ? close : close * 1000;
          return (closeMs - enterMs) / (1000 * 60 * 60); // hours
        }
        return null;
      })
      .filter(h => h !== null && h > 0);

    const avgHoldHours = holdTimes.length > 0
      ? holdTimes.reduce((a, b) => a + b, 0) / holdTimes.length
      : null;

    // 최대 연승/연패
    let maxWinStreak = 0, maxLoseStreak = 0, curWin = 0, curLose = 0;
    profits.forEach(p => {
      if (p > 0) { curWin++; curLose = 0; maxWinStreak = Math.max(maxWinStreak, curWin); }
      else { curLose++; curWin = 0; maxLoseStreak = Math.max(maxLoseStreak, curLose); }
    });

    // Risk/Reward
    const avgWin = wins.length > 0 ? wins.reduce((a, b) => a + b, 0) / wins.length : 0;
    const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((a, b) => a + b, 0) / losses.length) : 0;
    const riskReward = avgLoss > 0 ? (avgWin / avgLoss).toFixed(2) : '∞';

    return {
      totalTrades: trades.length,
      totalProfit: profits.reduce((a, b) => a + b, 0),
      avgProfit: profits.reduce((a, b) => a + b, 0) / profits.length,
      bestTrade: Math.max(...profits),
      worstTrade: Math.min(...profits),
      avgRor: rors.length > 0 ? (rors.reduce((a, b) => a + b, 0) / rors.length) : 0,
      winRate: (wins.length / trades.length * 100),
      avgWin,
      avgLoss,
      riskReward,
      maxWinStreak,
      maxLoseStreak,
      avgHoldHours,
    };
  }, [trades]);

  // 월별 실적
  const monthlyData = useMemo(() => {
    if (!trades || trades.length === 0) return [];
    const map = {};
    trades.forEach(t => {
      // name은 "YYYY-MM-DD HH:mm" 형태
      const month = t.name ? t.name.substring(0, 7) : 'Unknown';
      if (!map[month]) map[month] = { month, profit: 0, trades: 0, wins: 0 };
      map[month].profit += parseFloat(t.Profit);
      map[month].trades += 1;
      if (parseFloat(t.Profit) > 0) map[month].wins += 1;
    });
    return Object.values(map)
      .sort((a, b) => a.month.localeCompare(b.month))
      .map(m => ({
        ...m,
        winRate: (m.wins / m.trades * 100).toFixed(1),
      }));
  }, [trades]);

  // ROR 분포
  const rorDistribution = useMemo(() => {
    if (!trades || trades.length === 0) return [];
    const bins = [
      { range: '< -5%', min: -Infinity, max: -5, count: 0 },
      { range: '-5~-3%', min: -5, max: -3, count: 0 },
      { range: '-3~-1%', min: -3, max: -1, count: 0 },
      { range: '-1~0%', min: -1, max: 0, count: 0 },
      { range: '0~1%', min: 0, max: 1, count: 0 },
      { range: '1~3%', min: 1, max: 3, count: 0 },
      { range: '3~5%', min: 3, max: 5, count: 0 },
      { range: '5~10%', min: 5, max: 10, count: 0 },
      { range: '> 10%', min: 10, max: Infinity, count: 0 },
    ];
    trades.forEach(t => {
      const ror = parseFloat(t.ror);
      if (isNaN(ror)) return;
      for (const bin of bins) {
        if (ror >= bin.min && ror < bin.max) { bin.count++; break; }
      }
    });
    return bins.map(({ range, count }) => ({ range, count }));
  }, [trades]);

  // Long vs Short
  const sideData = useMemo(() => {
    if (!trades || trades.length === 0) return [];
    const sides = { long: { side: 'LONG', profit: 0, trades: 0, wins: 0 }, short: { side: 'SHORT', profit: 0, trades: 0, wins: 0 } };
    trades.forEach(t => {
      const s = t.side === 'long' ? 'long' : 'short';
      sides[s].profit += parseFloat(t.Profit);
      sides[s].trades += 1;
      if (parseFloat(t.Profit) > 0) sides[s].wins += 1;
    });
    return Object.values(sides).map(s => ({
      ...s,
      profit: parseFloat(s.profit.toFixed(2)),
      winRate: s.trades > 0 ? (s.wins / s.trades * 100).toFixed(1) : '0.0',
      avgProfit: s.trades > 0 ? parseFloat((s.profit / s.trades).toFixed(2)) : 0,
    }));
  }, [trades]);

  // KST 시간 추출 헬퍼
  const getKSTHour = (rawEnterTime) => {
    if (!rawEnterTime) return null;
    const ms = rawEnterTime > 1e12 ? rawEnterTime : rawEnterTime * 1000;
    return (new Date(ms).getUTCHours() + 9) % 24;
  };

  const getKSTWeekday = (rawEnterTime) => {
    if (!rawEnterTime) return null;
    const ms = rawEnterTime > 1e12 ? rawEnterTime : rawEnterTime * 1000;
    return new Date(ms + 9 * 3600 * 1000).getUTCDay(); // 0=일, 1=월 ... 6=토
  };

  // 시간대별 패턴 데이터
  const hourlyData = useMemo(() => {
    if (!trades || trades.length === 0) return [];
    const map = {};
    for (let h = 0; h < 24; h++) map[h] = { hour: `${String(h).padStart(2, '0')}시`, profit: 0, trades: 0, wins: 0 };
    trades.forEach(t => {
      const h = getKSTHour(t.rawEnterTime);
      if (h === null) return;
      map[h].profit += parseFloat(t.Profit);
      map[h].trades += 1;
      if (parseFloat(t.Profit) > 0) map[h].wins += 1;
    });
    return Object.values(map)
      .filter(d => d.trades > 0)
      .map(d => ({ ...d, profit: parseFloat(d.profit.toFixed(2)), winRate: parseFloat((d.wins / d.trades * 100).toFixed(1)) }));
  }, [trades]);

  // 요일별 패턴 데이터
  const weekdayData = useMemo(() => {
    if (!trades || trades.length === 0) return [];
    const labels = ['일', '월', '화', '수', '목', '금', '토'];
    const map = {};
    labels.forEach((l, i) => { map[i] = { day: l, profit: 0, trades: 0, wins: 0 }; });
    trades.forEach(t => {
      const d = getKSTWeekday(t.rawEnterTime);
      if (d === null) return;
      map[d].profit += parseFloat(t.Profit);
      map[d].trades += 1;
      if (parseFloat(t.Profit) > 0) map[d].wins += 1;
    });
    const order = [1, 2, 3, 4, 5, 6, 0]; // 월~일 순서
    return order
      .filter(i => map[i].trades > 0)
      .map(i => ({ ...map[i], profit: parseFloat(map[i].profit.toFixed(2)), winRate: parseFloat((map[i].wins / map[i].trades * 100).toFixed(1)) }));
  }, [trades]);

  // 보유 시간별 패턴 데이터
  const holdBinData = useMemo(() => {
    if (!trades || trades.length === 0) return [];
    const bins = [
      { label: '~4h', min: 0, max: 4, profit: 0, trades: 0, wins: 0 },
      { label: '4~8h', min: 4, max: 8, profit: 0, trades: 0, wins: 0 },
      { label: '8~24h', min: 8, max: 24, profit: 0, trades: 0, wins: 0 },
      { label: '24~48h', min: 24, max: 48, profit: 0, trades: 0, wins: 0 },
      { label: '48h+', min: 48, max: Infinity, profit: 0, trades: 0, wins: 0 },
    ];
    trades.forEach(t => {
      const enter = t.rawEnterTime > 1e12 ? t.rawEnterTime : t.rawEnterTime * 1000;
      const close = t.rawCloseTime > 1e12 ? t.rawCloseTime : t.rawCloseTime * 1000;
      if (!enter || !close) return;
      const hours = (close - enter) / (1000 * 3600);
      const bin = bins.find(b => hours >= b.min && hours < b.max);
      if (!bin) return;
      bin.profit += parseFloat(t.Profit);
      bin.trades += 1;
      if (parseFloat(t.Profit) > 0) bin.wins += 1;
    });
    return bins
      .filter(b => b.trades > 0)
      .map(b => ({ label: b.label, profit: parseFloat(b.profit.toFixed(2)), trades: b.trades, wins: b.wins, winRate: parseFloat((b.wins / b.trades * 100).toFixed(1)) }));
  }, [trades]);

  // 핵심 인사이트 계산
  const insights = useMemo(() => {
    if (!trades || trades.length === 0) return null;
    const winTrades = trades.filter(t => parseFloat(t.Profit) > 0);
    const loseTrades = trades.filter(t => parseFloat(t.Profit) <= 0);

    const avgHold = (arr) => {
      const times = arr.map(t => {
        const enter = t.rawEnterTime > 1e12 ? t.rawEnterTime : t.rawEnterTime * 1000;
        const close = t.rawCloseTime > 1e12 ? t.rawCloseTime : t.rawCloseTime * 1000;
        return enter && close ? (close - enter) / (1000 * 3600) : null;
      }).filter(h => h !== null && h >= 0);
      return times.length > 0 ? times.reduce((a, b) => a + b, 0) / times.length : null;
    };

    const avgHour = (arr) => {
      const hours = arr.map(t => getKSTHour(t.rawEnterTime)).filter(h => h !== null);
      return hours.length > 0 ? (hours.reduce((a, b) => a + b, 0) / hours.length).toFixed(1) : null;
    };

    const bestHour = hourlyData.length > 0 ? hourlyData.reduce((a, b) => a.profit > b.profit ? a : b) : null;
    const worstHour = hourlyData.length > 0 ? hourlyData.reduce((a, b) => a.profit < b.profit ? a : b) : null;
    const bestDay = weekdayData.length > 0 ? weekdayData.reduce((a, b) => a.profit > b.profit ? a : b) : null;
    const worstDay = weekdayData.length > 0 ? weekdayData.reduce((a, b) => a.profit < b.profit ? a : b) : null;

    return {
      winAvgHold: avgHold(winTrades),
      loseAvgHold: avgHold(loseTrades),
      winAvgHour: avgHour(winTrades),
      loseAvgHour: avgHour(loseTrades),
      bestHour, worstHour, bestDay, worstDay,
    };
  }, [trades, hourlyData, weekdayData]);

  if (!stats) return null;

  const formatHoldTime = (hours) => {
    if (hours === null) return 'N/A';
    if (hours < 1) return `${(hours * 60).toFixed(0)}m`;
    if (hours < 24) return `${hours.toFixed(1)}h`;
    return `${(hours / 24).toFixed(1)}d`;
  };

  const cardStyle = {
    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    padding: '12px 16px', borderRadius: '10px', minWidth: '120px', flex: 1,
    border: '1px solid rgba(0,255,255,0.15)', backgroundColor: 'rgba(0,255,255,0.03)',
  };
  const cardLabel = { fontSize: '10px', color: '#a8a8a8', marginBottom: '6px', fontFamily: 'Orbitron, sans-serif', textAlign: 'center' };
  const cardValue = { fontSize: '16px', fontWeight: 'bold', fontFamily: 'Orbitron, sans-serif' };

  const SIDE_COLORS = ['#00bcd4', '#ff9800'];

  return (
    <div style={{ width: '100%' }}>
      {/* Stats Cards */}
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', margin: '0 2.5%' }}>
        <div style={cardStyle}>
          <div style={cardLabel}>AVG PROFIT</div>
          <div style={{ ...cardValue, color: stats.avgProfit >= 0 ? '#4CAF50' : '#F44336' }}>
            {stats.avgProfit.toFixed(2)}$
          </div>
        </div>
        <div style={cardStyle}>
          <div style={cardLabel}>AVG ROR</div>
          <div style={{ ...cardValue, color: stats.avgRor >= 0 ? '#4CAF50' : '#F44336' }}>
            {stats.avgRor.toFixed(2)}%
          </div>
        </div>
        <div style={cardStyle}>
          <div style={cardLabel}>BEST TRADE</div>
          <div style={{ ...cardValue, color: '#4CAF50' }}>{stats.bestTrade.toFixed(2)}$</div>
        </div>
        <div style={cardStyle}>
          <div style={cardLabel}>WORST TRADE</div>
          <div style={{ ...cardValue, color: '#F44336' }}>{stats.worstTrade.toFixed(2)}$</div>
        </div>
        <div style={cardStyle}>
          <div style={cardLabel}>RISK / REWARD</div>
          <div style={{ ...cardValue, color: 'cyan' }}>{stats.riskReward}</div>
        </div>
        <div style={cardStyle}>
          <div style={cardLabel}>WIN STREAK</div>
          <div style={{ ...cardValue, color: '#4CAF50' }}>{stats.maxWinStreak}</div>
        </div>
        <div style={cardStyle}>
          <div style={cardLabel}>LOSE STREAK</div>
          <div style={{ ...cardValue, color: '#F44336' }}>{stats.maxLoseStreak}</div>
        </div>
        <div style={cardStyle}>
          <div style={cardLabel}>AVG HOLD TIME</div>
          <div style={{ ...cardValue, color: '#e2e2e2' }}>{formatHoldTime(stats.avgHoldHours)}</div>
        </div>
      </div>

      {/* Monthly Performance */}
      {monthlyData.length > 1 && (
        <div style={{ width: '95%', margin: '3vh auto 0' }}>
          <div style={{ textShadow: '0 0 5px rgba(0,255,255,0.7)', fontSize: 'large', marginBottom: '1.5vh', fontFamily: 'Orbitron, sans-serif' }}>
            Monthly Performance
          </div>
          <div style={{ width: '100%', height: '28vh' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData}>
                <XAxis dataKey="month" tick={{ fill: '#a8a8a8', fontSize: 10 }} />
                <YAxis tick={{ fill: '#a8a8a8', fontSize: 11 }} />
                <Tooltip cursor={false} content={<MonthlyTooltip />} />
                <Bar dataKey="profit">
                  {monthlyData.map((entry, i) => (
                    <Cell key={i} fill={entry.profit >= 0 ? '#4CAF50' : '#F44336'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ── Pattern Analysis ─────────────────────────────────── */}
      {insights && (
        <>
          {/* 구분선 */}
          <div style={{ width: '95%', margin: '4vh auto 0', borderTop: '1px solid rgba(0,255,255,0.15)' }} />
          <div style={{ width: '95%', margin: '2.5vh auto 0' }}>
            <div style={{ textShadow: '0 0 5px rgba(0,255,255,0.7)', fontSize: 'large', marginBottom: '2vh', fontFamily: 'Orbitron, sans-serif' }}>
              Pattern Analysis
            </div>

            {/* 핵심 인사이트 카드 */}
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '3vh' }}>
              {insights.bestHour && (
                <div style={{ ...cardStyle, flex: 1, minWidth: '140px' }}>
                  <div style={cardLabel}>BEST HOUR (KST)</div>
                  <div style={{ ...cardValue, color: '#4CAF50' }}>{insights.bestHour.hour}</div>
                  <div style={{ fontSize: '10px', color: '#a8a8a8', marginTop: '4px', fontFamily: 'Orbitron, sans-serif' }}>
                    {insights.bestHour.winRate}% WR · {insights.bestHour.profit > 0 ? '+' : ''}{insights.bestHour.profit}$
                  </div>
                </div>
              )}
              {insights.worstHour && (
                <div style={{ ...cardStyle, flex: 1, minWidth: '140px' }}>
                  <div style={cardLabel}>WORST HOUR (KST)</div>
                  <div style={{ ...cardValue, color: '#F44336' }}>{insights.worstHour.hour}</div>
                  <div style={{ fontSize: '10px', color: '#a8a8a8', marginTop: '4px', fontFamily: 'Orbitron, sans-serif' }}>
                    {insights.worstHour.winRate}% WR · {insights.worstHour.profit}$
                  </div>
                </div>
              )}
              {insights.bestDay && (
                <div style={{ ...cardStyle, flex: 1, minWidth: '140px' }}>
                  <div style={cardLabel}>BEST DAY</div>
                  <div style={{ ...cardValue, color: '#4CAF50' }}>{insights.bestDay.day}요일</div>
                  <div style={{ fontSize: '10px', color: '#a8a8a8', marginTop: '4px', fontFamily: 'Orbitron, sans-serif' }}>
                    {insights.bestDay.winRate}% WR · +{insights.bestDay.profit}$
                  </div>
                </div>
              )}
              {insights.worstDay && (
                <div style={{ ...cardStyle, flex: 1, minWidth: '140px' }}>
                  <div style={cardLabel}>WORST DAY</div>
                  <div style={{ ...cardValue, color: '#F44336' }}>{insights.worstDay.day}요일</div>
                  <div style={{ fontSize: '10px', color: '#a8a8a8', marginTop: '4px', fontFamily: 'Orbitron, sans-serif' }}>
                    {insights.worstDay.winRate}% WR · {insights.worstDay.profit}$
                  </div>
                </div>
              )}
              {insights.winAvgHold !== null && (
                <div style={{ ...cardStyle, flex: 1, minWidth: '140px' }}>
                  <div style={cardLabel}>WIN AVG HOLD</div>
                  <div style={{ ...cardValue, color: '#4CAF50' }}>{formatHoldTime(insights.winAvgHold)}</div>
                </div>
              )}
              {insights.loseAvgHold !== null && (
                <div style={{ ...cardStyle, flex: 1, minWidth: '140px' }}>
                  <div style={cardLabel}>LOSE AVG HOLD</div>
                  <div style={{ ...cardValue, color: '#F44336' }}>{formatHoldTime(insights.loseAvgHold)}</div>
                </div>
              )}
              {insights.winAvgHour !== null && (
                <div style={{ ...cardStyle, flex: 1, minWidth: '140px' }}>
                  <div style={cardLabel}>WIN AVG HOUR (KST)</div>
                  <div style={{ ...cardValue, color: '#4CAF50' }}>{insights.winAvgHour}시</div>
                </div>
              )}
              {insights.loseAvgHour !== null && (
                <div style={{ ...cardStyle, flex: 1, minWidth: '140px' }}>
                  <div style={cardLabel}>LOSE AVG HOUR (KST)</div>
                  <div style={{ ...cardValue, color: '#F44336' }}>{insights.loseAvgHour}시</div>
                </div>
              )}
            </div>

            {/* 시간대별 성과 */}
            {hourlyData.length > 0 && (
              <div style={{ marginBottom: '3vh' }}>
                <div style={{ textShadow: '0 0 5px rgba(0,255,255,0.7)', fontSize: 'large', marginBottom: '1.5vh', fontFamily: 'Orbitron, sans-serif' }}>
                  Hourly Pattern (KST)
                </div>
                <div style={{ width: '100%', height: '26vh' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={hourlyData}>
                      <XAxis dataKey="hour" tick={{ fill: '#a8a8a8', fontSize: 9 }} />
                      <YAxis yAxisId="left" tick={{ fill: '#a8a8a8', fontSize: 10 }} />
                      <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={{ fill: '#a8a8a8', fontSize: 10 }} unit="%" />
                      <Tooltip
                        cursor={false}
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const d = payload[0].payload;
                          return (
                            <div style={tooltipStyle}>
                              <p style={{ color: 'cyan', fontWeight: 'bold', margin: '0 0 4px' }}>{d.hour}</p>
                              <p style={{ margin: '2px 0' }}>Trades: {d.trades}</p>
                              <p style={{ margin: '2px 0' }}>Win Rate: {d.winRate}%</p>
                              <p style={{ color: d.profit >= 0 ? '#4CAF50' : '#F44336', margin: '2px 0' }}>Profit: {d.profit}$</p>
                            </div>
                          );
                        }}
                      />
                      <Bar yAxisId="left" dataKey="profit" radius={[3, 3, 0, 0]}>
                        {hourlyData.map((entry, i) => (
                          <Cell key={i} fill={entry.profit >= 0 ? 'rgba(76,175,80,0.75)' : 'rgba(244,67,54,0.75)'} />
                        ))}
                      </Bar>
                      <Line yAxisId="right" type="monotone" dataKey="winRate" stroke="cyan" dot={false} strokeWidth={1.5} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* 요일별 성과 + 보유시간별 성과 */}
            <div style={{ display: 'flex', gap: '3%' }}>
              {weekdayData.length > 0 && (
                <div style={{ flex: 1 }}>
                  <div style={{ textShadow: '0 0 5px rgba(0,255,255,0.7)', fontSize: 'large', marginBottom: '1.5vh', fontFamily: 'Orbitron, sans-serif' }}>
                    Weekday Pattern
                  </div>
                  <div style={{ width: '100%', height: '24vh' }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={weekdayData}>
                        <XAxis dataKey="day" tick={{ fill: '#a8a8a8', fontSize: 11 }} />
                        <YAxis yAxisId="left" tick={{ fill: '#a8a8a8', fontSize: 10 }} />
                        <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={{ fill: '#a8a8a8', fontSize: 10 }} unit="%" />
                        <Tooltip
                          cursor={false}
                          content={({ active, payload }) => {
                            if (!active || !payload?.length) return null;
                            const d = payload[0].payload;
                            return (
                              <div style={tooltipStyle}>
                                <p style={{ color: 'cyan', fontWeight: 'bold', margin: '0 0 4px' }}>{d.day}요일</p>
                                <p style={{ margin: '2px 0' }}>Trades: {d.trades}</p>
                                <p style={{ margin: '2px 0' }}>Win Rate: {d.winRate}%</p>
                                <p style={{ color: d.profit >= 0 ? '#4CAF50' : '#F44336', margin: '2px 0' }}>Profit: {d.profit}$</p>
                              </div>
                            );
                          }}
                        />
                        <Bar yAxisId="left" dataKey="profit" radius={[4, 4, 0, 0]}>
                          {weekdayData.map((entry, i) => (
                            <Cell key={i} fill={entry.profit >= 0 ? 'rgba(76,175,80,0.75)' : 'rgba(244,67,54,0.75)'} />
                          ))}
                        </Bar>
                        <Line yAxisId="right" type="monotone" dataKey="winRate" stroke="cyan" dot={false} strokeWidth={1.5} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {holdBinData.length > 0 && (
                <div style={{ flex: 1 }}>
                  <div style={{ textShadow: '0 0 5px rgba(0,255,255,0.7)', fontSize: 'large', marginBottom: '1.5vh', fontFamily: 'Orbitron, sans-serif' }}>
                    Hold Time Pattern
                  </div>
                  <div style={{ width: '100%', height: '24vh' }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={holdBinData}>
                        <XAxis dataKey="label" tick={{ fill: '#a8a8a8', fontSize: 10 }} />
                        <YAxis yAxisId="left" tick={{ fill: '#a8a8a8', fontSize: 10 }} />
                        <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={{ fill: '#a8a8a8', fontSize: 10 }} unit="%" />
                        <Tooltip
                          cursor={false}
                          content={({ active, payload }) => {
                            if (!active || !payload?.length) return null;
                            const d = payload[0].payload;
                            return (
                              <div style={tooltipStyle}>
                                <p style={{ color: 'cyan', fontWeight: 'bold', margin: '0 0 4px' }}>{d.label}</p>
                                <p style={{ margin: '2px 0' }}>Trades: {d.trades} ({d.wins}W / {d.trades - d.wins}L)</p>
                                <p style={{ margin: '2px 0' }}>Win Rate: {d.winRate}%</p>
                                <p style={{ color: d.profit >= 0 ? '#4CAF50' : '#F44336', margin: '2px 0' }}>Profit: {d.profit}$</p>
                              </div>
                            );
                          }}
                        />
                        <Bar yAxisId="left" dataKey="profit" radius={[4, 4, 0, 0]}>
                          {holdBinData.map((entry, i) => (
                            <Cell key={i} fill={entry.profit >= 0 ? 'rgba(76,175,80,0.75)' : 'rgba(244,67,54,0.75)'} />
                          ))}
                        </Bar>
                        <Line yAxisId="right" type="monotone" dataKey="winRate" stroke="cyan" dot={false} strokeWidth={1.5} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {/* ROR Distribution + Long vs Short */}
      <div style={{ display: 'flex', width: '95%', margin: '3vh auto 0', gap: '2%' }}>
        {/* ROR Distribution */}
        <div style={{ flex: 2 }}>
          <div style={{ textShadow: '0 0 5px rgba(0,255,255,0.7)', fontSize: 'large', marginBottom: '1.5vh', fontFamily: 'Orbitron, sans-serif' }}>
            ROR Distribution
          </div>
          <div style={{ width: '100%', height: '25vh' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rorDistribution}>
                <XAxis dataKey="range" tick={{ fill: '#a8a8a8', fontSize: 9 }} />
                <YAxis tick={{ fill: '#a8a8a8', fontSize: 11 }} allowDecimals={false} />
                <Tooltip cursor={false} content={<RorTooltip />} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {rorDistribution.map((entry, i) => (
                    <Cell key={i} fill={entry.range.includes('-') || entry.range.includes('<') ? 'rgba(244,67,54,0.7)' : 'rgba(76,175,80,0.7)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Long vs Short */}
        <div style={{ flex: 1 }}>
          <div style={{ textShadow: '0 0 5px rgba(0,255,255,0.7)', fontSize: 'large', marginBottom: '1.5vh', fontFamily: 'Orbitron, sans-serif' }}>
            Long vs Short
          </div>
          <div style={{ width: '100%', height: '18vh' }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={sideData}
                  dataKey="trades"
                  nameKey="side"
                  cx="50%"
                  cy="50%"
                  outerRadius="85%"
                  innerRadius="50%"
                  paddingAngle={3}
                >
                  {sideData.map((_, i) => (
                    <Cell key={i} fill={SIDE_COLORS[i]} />
                  ))}
                </Pie>
                <Legend verticalAlign="bottom" height={0} />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const d = payload[0].payload;
                      return (
                        <div style={tooltipStyle}>
                          <p style={{ color: 'cyan', fontWeight: 'bold', margin: '0 0 6px' }}>{d.side}</p>
                          <p style={{ margin: '2px 0' }}>Trades: {d.trades} ({d.winRate}% win)</p>
                          <p style={{ margin: '2px 0' }}>Avg: {d.avgProfit}$</p>
                          <p style={{ color: d.profit >= 0 ? '#4CAF50' : '#F44336', margin: '2px 0' }}>
                            Total: {d.profit}$
                          </p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          {/* Side stats text */}
          <div style={{ display: 'flex', justifyContent: 'space-around', fontSize: '10px', fontFamily: 'Orbitron, sans-serif', marginTop: '1vh' }}>
            {sideData.map((s, i) => (
              <div key={s.side} style={{ textAlign: 'center' }}>
                <div style={{ color: SIDE_COLORS[i], fontWeight: 'bold' }}>{s.side}</div>
                <div style={{ color: '#a8a8a8' }}>{s.trades} trades</div>
                <div style={{ color: s.profit >= 0 ? '#4CAF50' : '#F44336' }}>{s.profit}$</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AnalyticsReport;
