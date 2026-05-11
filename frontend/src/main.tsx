import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './utils/time'; // 副作用: dayjs.tz.setDefault('Asia/Shanghai')
import 'antd/dist/reset.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
