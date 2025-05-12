import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts";
import CustomTooltip from "./CustomTooltip";

const LingeGraph = ({datas}) => {
  return(
    <ResponsiveContainer width='100%' height='100%'>
      <LineChart data={datas}>
        <XAxis dataKey="name" />
        <YAxis domain={['dataMin - 5', 'dataMax + 10']}/>
        <Tooltip content={<CustomTooltip />} />
        <CartesianGrid horizontal={false} vertical={false} />
        {/* <CartesianGrid stroke="#9d9d9d" /> */}
        <Line type="linear" dataKey="balance" stroke="cyan" dot={false} strokeWidth={3}/>
      </LineChart>
    </ResponsiveContainer>
  )
};

export default LingeGraph;