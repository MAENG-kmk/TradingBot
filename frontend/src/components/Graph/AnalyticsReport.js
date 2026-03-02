import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, PieChart, Pie, Legend,
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
