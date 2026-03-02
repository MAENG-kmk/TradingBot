import { XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from "recharts";

const CoinComparisonTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div style={{
        backgroundColor: '#1a1a2e',
        padding: '10px 14px',
        border: '1px solid rgba(0,255,255,0.3)',
        borderRadius: '8px',
        color: '#e2e2e2',
        fontFamily: 'Orbitron, sans-serif',
        fontSize: '11px',
      }}>
        <p style={{color: 'cyan', fontWeight: 'bold', margin: '0 0 6px'}}>{data.coin}</p>
        <p style={{margin: '2px 0'}}>Trades: {data.trades}</p>
        <p style={{margin: '2px 0'}}>Win Rate: {data.winRate}%</p>
        <p style={{color: data.profit >= 0 ? '#4CAF50' : '#F44336', margin: '2px 0'}}>
          Profit: {data.profit}$
        </p>
      </div>
    );
  }
  return null;
};

const CoinComparisonChart = ({ datas, onCoinClick }) => {
  return (
    <ResponsiveContainer width='100%' height='100%'>
      <BarChart data={datas} layout="vertical" margin={{ left: 10, right: 20 }}>
        <XAxis type="number" tick={{ fill: '#a8a8a8', fontSize: 11 }} />
        <YAxis type="category" dataKey="coin" width={60} tick={{ fill: '#e2e2e2', fontSize: 12 }} />
        <Tooltip cursor={false} content={<CoinComparisonTooltip />} />
        <Bar
          dataKey="profit"
          onClick={(data) => onCoinClick && onCoinClick(data.coin)}
          style={{ cursor: 'pointer' }}
        >
          {datas.map((entry, index) => (
            <Cell
              key={`cell-${index}`}
              fill={entry.profit >= 0 ? '#4CAF50' : '#F44336'}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
};

export default CoinComparisonChart;
