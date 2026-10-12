import type { ConversationSummary, Language } from '../types';
import { STRINGS } from '../i18n';

export type View = 'chat' | 'logs';

interface SidebarProps {
  view: View;
  language: Language;
  conversations: ConversationSummary[];
  activeId: string;
  onView: (view: View) => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}

export function Sidebar(props: SidebarProps) {
  const { view, language, conversations, activeId, onView, onSelect, onNew, onDelete } = props;
  const t = STRINGS[language];

  return (
    <aside className="sidebar">
      <div className="brand">
        <img src="/favicon.svg" alt="" width="26" height="26" />
        <span>{t.brand}</span>
      </div>

      <button type="button" className="new-chat" onClick={onNew}>
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M8 3v10M3 8h10" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
        {t.newChat}
      </button>

      <div className="history-label">{t.history}</div>
      <nav className="history" aria-label={t.history}>
        {conversations.length === 0 && <p className="history-empty">{t.noHistory}</p>}
        {conversations.map((c) => {
          const active = view === 'chat' && c.id === activeId;
          return (
            <div key={c.id} className={`history-item${active ? ' active' : ''}`}>
              <button
                type="button"
                className="history-open"
                aria-current={active ? 'true' : undefined}
                onClick={() => onSelect(c.id)}
              >
                <span className="history-title">{c.title || t.untitled}</span>
                <span className="history-date">{shortDate(c.updated_at)}</span>
              </button>
              <button
                type="button"
                className="history-delete"
                aria-label={t.deleteChat}
                title={t.deleteChat}
                onClick={() => onDelete(c.id)}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                  <path d="M3 3l8 8M11 3l-8 8" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          );
        })}
      </nav>

      <div className="side-nav">
        <button type="button" className={view === 'chat' ? 'active' : ''} onClick={() => onView('chat')}>
          {t.chat}
        </button>
        <button type="button" className={view === 'logs' ? 'active' : ''} onClick={() => onView('logs')}>
          {t.logs}
        </button>
      </div>
    </aside>
  );
}
