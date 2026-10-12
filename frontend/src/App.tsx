import { useCallback, useEffect, useState } from 'react';
import { ChatInterface } from './components/ChatInterface';
import { LanguageSwitcher } from './components/LanguageSwitcher';
import { SideNav, Sidebar } from './components/Sidebar';
import type { View } from './components/Sidebar';
import { Documents } from './pages/Documents';
import { Logs } from './pages/Logs';
import { ApiClient } from './services/api';
import { STRINGS } from './i18n';
import type { PipelineHealth } from './types/admin';
import type { ConversationSummary, Language } from './types';
import './App.css';

const ACTIVE_KEY = 'bcb.activeConversation';
const LANG_KEY = 'bcb.language';
const DISMISS_KEY = 'bcb.dismissedHealth';

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
  const [search, setSearch] = useState('');
  const [days, setDays] = useState(0);
  const [health, setHealth] = useState<PipelineHealth | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(() => readStore(DISMISS_KEY));
  const [exportOpen, setExportOpen] = useState(false);
  const t = STRINGS[language];

  // Poll the pipeline health so a failed run is visible without opening the Logs page.
  useEffect(() => {
    const load = () =>
      ApiClient.getPipelineHealth()
        .then(setHealth)
        .catch(() => undefined);
    load();
    const timer = window.setInterval(load, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const healthKey = health ? `${health.status}:${health.issues.map((i) => `${i.stage}${i.kind}${i.at}`).join('|')}` : '';
  const showBanner = !!health && health.status !== 'ok' && dismissed !== healthKey;
  const dismissBanner = () => {
    setDismissed(healthKey);
    writeStore(DISMISS_KEY, healthKey);
  };

  const refresh = useCallback(() => {
    ApiClient.listConversations({ q: search.trim() || undefined, days: days || undefined })
      .then(setConversations)
      .catch(() => undefined);
  }, [search, days]);

  // Debounce typing in the search box.
  useEffect(() => {
    const timer = window.setTimeout(refresh, search ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [refresh, search]);
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
        search={search}
        onSearch={setSearch}
        days={days}
        onDays={setDays}
      />
      <SideNav
        view={view}
        language={language}
        alert={health && health.status !== 'ok' ? health.status : null}
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
          {view === 'chat' && conversations.some((c) => c.id === activeId) && (
            <div className="export-menu">
              <button
                type="button"
                className="icon-btn export-trigger"
                aria-haspopup="menu"
                aria-expanded={exportOpen}
                onClick={() => setExportOpen((o) => !o)}
                onBlur={() => window.setTimeout(() => setExportOpen(false), 150)}
              >
                {t.exportChat} ▾
              </button>
              {exportOpen && (
                <div className="export-popover" role="menu">
                  <a role="menuitem" href={ApiClient.exportUrl(activeId, 'md')} download>
                    {t.exportMd}
                  </a>
                  <a role="menuitem" href={ApiClient.exportUrl(activeId, 'json')} download>
                    {t.exportJson}
                  </a>
                </div>
              )}
            </div>
          )}
          <LanguageSwitcher language={language} onLanguageChange={setLanguage} />
        </header>
        {showBanner && health && (
          <div className={`health-banner ${health.status}`} role="alert">
            <span>
              <strong>{health.status === 'error' ? t.pipelineAlertError : t.pipelineAlertWarn}</strong>
              {health.issues[0] ? ` — ${health.issues[0].stage}: ${health.issues[0].message}` : ''}
              {health.issues.length > 1 ? ` (+${health.issues.length - 1})` : ''}
            </span>
            <span className="health-actions">
              <button type="button" onClick={() => setView('logs')}>
                {t.viewLogs}
              </button>
              <button type="button" onClick={dismissBanner} aria-label={t.dismiss}>
                ✕
              </button>
            </span>
          </div>
        )}
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
