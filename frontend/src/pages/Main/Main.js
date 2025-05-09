import { useEffect, useState } from 'react'
import styles from './Main.module.css'
import axios from 'axios'
import LineGraph from '../../components/Graph/LineGraph';
import formatTimestamp from '../../tools/formatTimeStamp';
import BarGraph from '../../components/Graph/BarGraph';
import PieGraph from '../../components/Graph/PieGraph';

const Main = () => {
  const [startBalance, setStartBalance] = useState('');
  const [balance, setBalance] = useState('');
  const [pnl, setPnl] = useState(0);
  const [numTrade, setNumTrade] = useState(0);
  const [version, setVersion] = useState('');
  const [balanceDatas, setBalanceDatas] = useState([]);
  const [pnlDatas, setPnlDatas] = useState([]);
  const [winningRateData, setWinningRateData] = useState([]);

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

        const response = await axios.get(`${process.env.REACT_APP_API_URL}/currentVersion`)
        if (response.data.success) {
          const vers = response.data.version;
          const sb = response.data.balance;
          setStartBalance(sb);
          setVersion(vers);

          const incodig = encodeURIComponent(vers);
          const response_2 = await axios.get(`${process.env.REACT_APP_API_URL}/datas?collection=${incodig}`);
          if (response_2.data.success) {
            const messData = response_2.data.datas;
            setNumTrade(messData.length);
            var win = 0;
            var lose = 0;
            const balances = [];
            const processed = messData.map(data => {
              const filter = {};
              const convertedDate = formatTimestamp(data.closeTime);
              balances.push({
                name: convertedDate,
                Balance: parseFloat(data.balance).toFixed(2),
              })
              filter['name'] =  convertedDate;
              filter['Profit'] = parseFloat(data.profit).toFixed(2);
              if (data.ror > 0) {
                win += 1;
              } else {
                lose += 1;
              };

              return filter;
            });
            // setPnl(totalPnl.toFixed(2));
            setPnl((parseFloat(response_0.data.balance)-parseFloat(sb)).toFixed(2))
            setBalanceDatas(balances);
            setPnlDatas(processed);
            setWinningRateData([
              {
                name: 'win',
                value: win,
              },
              {
                name: 'lose',
                value: lose,
              }
            ]);
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
    alert('Open Soon');
  };

  return(
    <div className={styles.background}>
      <div className={styles.headerContainer}>
        <div className={styles.titleContainer}>
          <div className={`${styles.title} ${styles.glow_text}`}>CRYPTO TRADING BOT</div>
          <div className={styles.modelName}>Current Model : {version}</div>
        </div>
        <button className={styles.button} onClick={handleClickButton}>Go Model History</button>
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
            <div className={styles.statistics}>Winning Rate</div>
          </div>
          <div className={styles.pieGraph}>
            <PieGraph datas={winningRateData} />
          </div>
          <div className={styles.floor}>
            <div className={styles.statistics}>Total Trade : {numTrade}</div>
          </div>
          <div className={styles.floor}>
            <div className={styles.statistics}>Total ROR :</div>
            <div className={pnl > 0 ? styles.plus : styles.minus}>{(pnl/startBalance*100).toFixed(2)} %</div>
          </div>
        </div>
      </div>
      <div className={`${styles.secondRow} ${styles.glow_box} ${styles.gradient_border}`}>
        <div className={styles.header}>
          <div className={styles.name}>Profit and Loss ($)</div>
          <div className={pnl > 0 ? styles.plus : styles.minus}><span className={styles.label}>Total :</span>{pnl} $</div>
        </div>
        <div className={styles.graph}>
          <BarGraph datas={pnlDatas} />
        </div>
      </div>
    </div>
  )
}

export default Main