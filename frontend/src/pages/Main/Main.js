import { useEffect, useState } from 'react'
import styles from './Main.module.css'
import axios from 'axios'

const Main = () => {
  const [balance, setBalance] = useState('');

  useEffect(() => {
    const getBalance = async () => {
      try {
        const response = await axios.get(`${process.env.REACT_APP_API_URL}/balance`)
        console.log(response)
        if (response.data.success) {
          setBalance(parseFloat(response.data.balance).toFixed(2));
        }
      } catch (error) {
        console.log(error)
      }
    };
    getBalance();
  }, [])

  return(
    <div>
      {balance}$
    </div>
  )
}

export default Main