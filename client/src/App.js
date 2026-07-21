// ============================================================
// App.js
// 역할: React 클라이언트의 루트 컴포넌트. 현재는 CRA(create-react-app)
//       기본 템플릿 화면 그대로이며 자판기용 UI는 아직 구현되지 않았다.
// ============================================================
import logo from './logo.svg';
import './App.css';

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <img src={logo} className="App-logo" alt="logo" />
        <p>
          Edit <code>src/App.js</code> and save to reload.
        </p>
        <a
          className="App-link"
          href="https://reactjs.org"
          target="_blank"
          rel="noopener noreferrer"
        >
          Learn React
        </a>
      </header>
    </div>
  );
}

export default App;
