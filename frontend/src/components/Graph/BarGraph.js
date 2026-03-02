import { XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from "recharts";
import CustomTooltip from "./CustomTooltip";

const BarGraph = ({datas}) => {

  const handleBarClick = (data, index) => {
    window.open(`https://www.binance.com/en/futures/${data.symbol}`, '_blank');
  };

  return(
    <ResponsiveContainer width='100%' height='100%'>
      <BarChart data={datas}>
        <XAxis dataKey="name" tick={{ fill: '#a8a8a8', fontSize: 11 }} />
        <YAxis tick={{ fill: '#a8a8a8', fontSize: 11 }} />
        <Tooltip cursor={false} content={<CustomTooltip />} />
        <Bar dataKey="Profit" 
          fill="#8884d8"  
          shape={(props) => {
            const { x, y, width, height, value } = props;
            const color = value >= 0 ? '#4CAF50' : '#F44336'; 
            const adjustedY = value >= 0 ? y : y + height;   
            const adjustedHeight = Math.abs(height);  
            return (
              <rect
                x={x}
                y={adjustedY}
                width={width}
                height={adjustedHeight}
                fill={color}
              />
            );
          }}
          onClick={handleBarClick}
        />
      </BarChart>
    </ResponsiveContainer>
  )
};

export default BarGraph;