import { useEffect, useState } from 'react'
import styles from './Main.module.css'
import axios from 'axios'
import Graph from '../../components/Graph/Graph';
import formatTimestamp from '../../tools/formatTimeStamp';

const Main = () => {
  const [balance, setBalance] = useState('');
  const [version, setVersion] = useState('');
  const [startDate, setStartDate] = useState('');
  const [datas, setDatas] = useState([]);

  useEffect(() => {
    const getBalance = async () => {
      try {
        const response = await axios.get(`${process.env.REACT_APP_API_URL}/balance`);
        if (response.data.success) {
          setBalance(parseFloat(response.data.balance).toFixed(2));
        }
      } catch (error) {
        console.log(error)
      }
    };

    const getDatas = async () => {
      try {
        const response = await axios.get(`${process.env.REACT_APP_API_URL}/currentVersion`)
        if (response.data.success) {
          const vers = response.data.version;
          const date = response.data.date;
          const convertDate = formatTimestamp(date);
          setVersion(vers);
          setStartDate(convertDate);

          const incodig = encodeURIComponent(vers);
          const response_2 = await axios.get(`${process.env.REACT_APP_API_URL}/datas?collection=${incodig}`);
          if (response_2.data.success) {
            const messData = response_2.data.datas;
            const processed = messData.map(data => {
              const filter = {};
              filter['name'] =  formatTimestamp(data.closeTime);
              filter['value'] = data.ror;
              return filter;
            })
            setDatas(processed);
          };
        }
      } catch (error) {
        console.log(error)
      }
    };

    getBalance();
    getDatas();
  }, [])

  return(
    <div className={styles.background}>
      <div className={styles.headerContainer}>
        <div className={styles.titleContainer}>
          <div className={`${styles.title} ${styles.glow_text}`}>Crypto Trading Bot</div>
          <div className={styles.modelName}>Current Model : {version}</div>
        </div>
      </div>
      <div className={`${styles.assetContent} ${styles.glow_box}`}>
        <div className={styles.header}>
          <div className={styles.name}>Asset Value</div>
          <div className={styles.balance}>{balance} $</div>
        </div>
        <div className={styles.graph}>
          <Graph datas={datas} />
        </div>
      </div>
    </div>
  )
}

export default Main