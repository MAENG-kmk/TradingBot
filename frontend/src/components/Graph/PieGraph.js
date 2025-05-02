import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const COLORS = ['#4CAF50', '#F44336']; // 초록, 빨강

const PieGraph = ({datas}) => {
  return (
    <ResponsiveContainer width='100%' height='100%'>
      <PieChart>
        <Tooltip />
        <Pie
          data={datas}
          dataKey="value"
          cx="50%"
          cy="50%"
          outerRadius='100%'
          innerRadius={0} // 도넛 모양으로 하고 싶을 경우
          paddingAngle={0}
          labelLine={false}
        >
          {datas.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={COLORS[index]} />
          ))}
        </Pie>
        <Legend verticalAlign="bottom" height='0' />
      </PieChart>
    </ResponsiveContainer>
  );
};

export default PieGraph
