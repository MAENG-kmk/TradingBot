import { useEffect, useState } from 'react'
import styles from './Main.module.css'
import axios from 'axios'
import LineGraph from '../../components/Graph/LineGraph';
import formatTimestamp from '../../tools/formatTimeStamp';
import BarGraph from '../../components/Graph/BarGraph';
import { useNavigate } from 'react-router-dom';

const Main = () => {
  const [startBalance, setStartBalance] = useState('');
  const [balance, setBalance] = useState('');
  const [pnl, setPnl] = useState(0);
  const [version, setVersion] = useState('');
  const [balanceDatas, setBalanceDatas] = useState([]);
  const [pnlDatas, setPnlDatas] = useState([]);
  const [positionDatas, setPositionDatas] = useState([]);

  const navigate  = useNavigate();

  useEffect(() => {
    // const getBalance = async () => {
    //   try {
    //     const response = await axios.get(`${process.env.REACT_APP_API_URL}/balance`);
    //     if (response.data.success) {
    //       setBalance(parseFloat(response.data.balance).toFixed(2));
    //     }
    //   } catch (error) {
    //     console.log(error)
    //   }
    // };

    const getDatas = async () => {
      try {
        const response_0 = await axios.get(`${process.env.REACT_APP_API_URL}/balance`);
        if (response_0.data.success) {
          setBalance(parseFloat(response_0.data.balance).toFixed(2));
        };

        const response = await axios.get(`${process.env.REACT_APP_API_URL}/currentVersion`);
        if (response.data.success) {
          const vers = response.data.version;
          const sb = response.data.balance;
          setStartBalance(sb);
          setVersion(vers);

          const positions = await axios.get(`${process.env.REACT_APP_API_URL}/positions`);
          if (positions.data.success) {
            const curPosition = positions.data.datas;
            const positionList = curPosition.map((data) => {
              const ror = (parseFloat(data.unrealizedProfit) / parseFloat(data.positionInitialMargin) * 100).toFixed(2);
              const side = parseFloat(data.positionAmt) > 0 ? 'long' : 'short';
              const cur = {
                symbol: data.symbol,
                ror: ror,
                side: side,
              };
              return cur;
            });
            setPositionDatas(positionList);
          };

          const incodig = encodeURIComponent(vers);
          const response_2 = await axios.get(`${process.env.REACT_APP_API_URL}/datas?collection=${incodig}`);
          if (response_2.data.success) {
            const messData = response_2.data.datas;
            const processed = messData.map(data => {
              const filter = {};
              const convertedDate = formatTimestamp(data.closeTime);
              filter['name'] =  convertedDate;
              filter['symbol'] = data.symbol;
              filter['enterTime'] = formatTimestamp(data.enterTime);
              filter['Profit'] = parseFloat(data.profit).toFixed(2);
              filter['balance'] = parseFloat(data.balance).toFixed(2);
              filter['side'] = data.side;

              return filter;
            });
            // setPnl(totalPnl.toFixed(2));
            setPnl((parseFloat(response_0.data.balance)-parseFloat(sb)).toFixed(2))
            setBalanceDatas(processed);
            setPnlDatas(processed);
          };
        }
      } catch (error) {
        console.log(error)
      }
    };

    // getBalance();
    getDatas();
  }, [])

  const handleClickButton = () => {
    navigate('/history');
  };

  const handlePositionClick = (symbol) => {
    window.open(`https://www.binance.com/en/futures/${symbol}`, '_blank');
  };

  return(
    <div className={styles.background}>
      <div className={styles.headerContainer}>
        <div className={styles.titleContainer}>
          <div className={`${styles.title} ${styles.glow_text}`}>CRYPTO TRADING BOT</div>
          <div className={styles.modelName}>Current Model : {version}</div>
        </div>
        <button className={styles.button} onClick={handleClickButton}>Model History</button>
      </div>
      <div className={styles.row}>
        <div className={`${styles.assetContent} ${styles.glow_box} ${styles.gradient_border}`}>
          <div className={styles.header}>
            <div className={styles.name}>Asset Value</div>
            <div className={styles.balance}><span className={styles.label}>Current Asset :</span>{balance} $</div>
          </div>
          <div className={styles.graph}>
            <LineGraph datas={balanceDatas} />
          </div>
        </div>
        <div className={`${styles.rorContent} ${styles.glow_box} ${styles.gradient_border}`}>
          <div className={styles.header}>
            <div className={styles.statistics}>Current Position</div>
          </div>
          {positionDatas.map((position) => {
            return(
              <div className={styles.position} key={position.symbol} onClick={() => {handlePositionClick(position.symbol)}}>
                <div>{position.symbol}<span>{position.side}</span></div>
                <div style={position.ror > 0 ? {color: 'rgb(35, 255, 35)'} : {color: '#F44336'}}>{position.ror}%</div>
              </div>
            )
          })}
        </div>
      </div>
      <div className={`${styles.secondRow} ${styles.glow_box} ${styles.gradient_border}`}>
        <div className={styles.header}>
          <div className={styles.name}>Profit and Loss ($)</div>
          <div className={pnl > 0 ? styles.plus : styles.minus}><span className={styles.label}>Total :</span>{pnl} $ ( {(pnl && pnl/startBalance*100).toFixed(2)} % )</div>
        </div>
        <div className={styles.graph}>
          <BarGraph datas={pnlDatas} />
        </div>
      </div>
    </div>
  )
}

export default Main