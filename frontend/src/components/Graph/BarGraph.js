import { XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from "recharts";

const BarGraph = ({datas}) => {

  return(
    <ResponsiveContainer width='100%' height='100%'>
      <BarChart data={datas}>
        <XAxis dataKey="name" />
        <YAxis />
        <Tooltip cursor={false} />
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
        />
      </BarChart>
    </ResponsiveContainer>
  )
};

export default BarGraph;