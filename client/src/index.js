// ============================================================
// index.js
// 역할: React 클라이언트의 진입점. #root 엘리먼트에 App 컴포넌트를
//       StrictMode로 렌더링하고 reportWebVitals를 초기화한다. (CRA 기본 구조)
// ============================================================
import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();
