import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts";

const LingeGraph = ({datas}) => {

  return(
    <ResponsiveContainer width='100%' height='100%'>
      <LineChart data={datas}>
        <XAxis dataKey="name" />
        <YAxis domain={['dataMin - 1', 'dataMax + 1']}/>
        <Tooltip />
        <CartesianGrid horizontal={false} vertical={false} />
        {/* <CartesianGrid stroke="#9d9d9d" /> */}
        <Line type="linear" dataKey="Balance" stroke="cyan" dot={false} strokeWidth={3}/>
      </LineChart>
    </ResponsiveContainer>
  )
};

export default LingeGraph;