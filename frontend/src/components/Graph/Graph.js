import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts";

const Graph = ({datas}) => {

  return(
    <ResponsiveContainer width='100%' height='100%'>
      <LineChart data={datas}>
        <XAxis dataKey="name" />
        <YAxis />
        <Tooltip />
        <CartesianGrid horizontal={false} vertical={false} />
        {/* <CartesianGrid stroke="#9d9d9d" /> */}
        <linearGradient id="lineGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#00FFD1" stopOpacity={0.6} />
          <stop offset="100%" stopColor="#00FFD1" stopOpacity={0} />
        </linearGradient>
        <Line type="linear" dataKey="value" stroke="cyan" />
      </LineChart>
    </ResponsiveContainer>
  )
};

export default Graph;