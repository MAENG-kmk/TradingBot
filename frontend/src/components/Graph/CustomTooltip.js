const CustomTooltip = ({ active, payload, label }) => {
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
        <p style={{color: 'cyan', fontWeight: 'bold', margin: '0 0 6px'}}>Symbol: {data.symbol}</p>
        <p style={{margin: '2px 0'}}>Side: {data.side}</p>
        <p style={{margin: '2px 0'}}>Enter: {data.enterTime}</p>
        <p style={{margin: '2px 0'}}>Close: {label}</p>
        <p style={{margin: '2px 0'}}>Balance: {data.balance}$</p>
        <p style={{color: parseFloat(data.Profit) >= 0 ? '#4CAF50' : '#F44336', margin: '2px 0'}}>
          Profit: {data.Profit}$
        </p>
      </div>
    );
  }

  return null;
};

export default CustomTooltip;
