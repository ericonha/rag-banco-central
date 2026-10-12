import { useCallback, useEffect, useState } from 'react';
import { ChatInterface } from './components/ChatInterface';
import { LanguageSwitcher } from './components/LanguageSwitcher';
import { SideNav, Sidebar } from './components/Sidebar';
import type { View } from './components/Sidebar';
import { Documents } from './pages/Documents';
import { Logs } from './pages/Logs';
import { ApiClient } from './services/api';
import { STRINGS } from './i18n';
import type { ConversationSummary, Language } from './types';
import './App.css';

const ACTIVE_KEY = 'bcb.activeConversation';
const LANG_KEY = 'bcb.language';

const readStore = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};

const writeStore = (key: string, value: string): void => {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable (private mode): the chat still works, it just won't be remembered */
  }
};

function App() {
  const [view, setView] = useState<View>('chat');
  const [language, setLanguage] = useState<Language>(() => (readStore(LANG_KEY) === 'en' ? 'en' : 'pt'));
  const [activeId, setActiveId] = useState<string>(() => readStore(ACTIVE_KEY) || crypto.randomUUID());
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const t = STRINGS[language];

  const refresh = useCallback(() => {
    ApiClient.listConversations()
      .then(setConversations)
      .catch(() => undefined);
  }, []);

  useEffect(refresh, [refresh]);
  useEffect(() => writeStore(ACTIVE_KEY, activeId), [activeId]);
  useEffect(() => {
    writeStore(LANG_KEY, language);
    document.documentElement.lang = language === 'pt' ? 'pt-BR' : 'en';
  }, [language]);

  const select = (id: string) => {
    setActiveId(id);
    setView('chat');
    setMenuOpen(false);
  };

  const remove = (id: string) => {
    ApiClient.deleteConversation(id)
      .then(() => {
        refresh();
        if (id === activeId) setActiveId(crypto.randomUUID());
      })
      .catch(() => undefined);
  };

  const activeTitle = conversations.find((c) => c.id === activeId)?.title || t.untitled;

  return (
    <div className="shell">
      <Sidebar
        view={view}
        language={language}
        conversations={conversations}
        activeId={activeId}
        onSelect={select}
        onNew={() => select(crypto.randomUUID())}
        onDelete={remove}
      />
      <SideNav
        view={view}
        language={language}
        onView={(v) => {
          setView(v);
          setMenuOpen(false);
        }}
      />
      <div className={`scrim${menuOpen ? ' show' : ''}`} onClick={() => setMenuOpen(false)} />
      <div className={`main${menuOpen ? ' menu-open' : ''}`}>
        <header className="topbar">
          <button type="button" className="icon-btn menu-btn" aria-label={t.openMenu} onClick={() => setMenuOpen((o) => !o)}>
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M3 5h12M3 9h12M3 13h12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
          <h1 className="topbar-title">{view === 'chat' ? activeTitle : view === 'docs' ? t.docsTitle : t.logsTitle}</h1>
          <LanguageSwitcher language={language} onLanguageChange={setLanguage} />
        </header>
        <main className="content">
          {view === 'chat' ? (
            <ChatInterface key={activeId} conversationId={activeId} language={language} onExchange={refresh} />
          ) : view === 'docs' ? (
            <Documents />
          ) : (
            <Logs />
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
