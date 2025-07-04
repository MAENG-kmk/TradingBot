const formatTimestamp = (timestamp) => {
  const convertedTS = String(parseInt(timestamp)).length === 10 ? parseFloat(timestamp)*1000 : parseFloat(timestamp);

  const date = new Date(convertedTS);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0'); // 0~11이므로 +1
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  const second = String(date.getSeconds()).padStart(2, '0');

  return `${year}/${month}/${day} ${hour}:${minute}:${second}`;
};

export default formatTimestamp;