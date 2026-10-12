import { useState } from 'react';
import { ChatInterface } from './components/ChatInterface';
import { Logs } from './pages/Logs';
import './App.css';

type View = 'chat' | 'logs';

function App() {
  const [view, setView] = useState<View>('chat');

  return (
    <div className="app">
      <nav className="view-switch" aria-label="Navegação">
        <button
          className={view === 'chat' ? 'active' : ''}
          onClick={() => setView('chat')}
        >
          Chat
        </button>
        <button
          className={view === 'logs' ? 'active' : ''}
          onClick={() => setView('logs')}
        >
          Logs
        </button>
      </nav>
      {view === 'chat' ? <ChatInterface /> : <Logs />}
    </div>
  );
}

export default App;
