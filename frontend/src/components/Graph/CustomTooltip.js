const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div style={{ backgroundColor: "#fff", padding: "10px", border: "1px solid black", color: 'gray' }}>
        <p style={{color: 'black'}}>Symbol: {data.symbol}</p>
        <p>Side: {data.side}</p>
        <p>Enter: {data.enterTime}</p>
        <p>Close: {label}</p>
        <p>Balance: {data.balance}$</p>
        <p>Profit: {data.Profit}$</p>
      </div>
    );
  }

  return null;
};

export default CustomTooltip;
