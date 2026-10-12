import type { Language } from '../types';

interface LanguageSwitcherProps {
  language: Language;
  onLanguageChange: (lang: Language) => void;
}

export function LanguageSwitcher({
  language,
  onLanguageChange,
}: LanguageSwitcherProps) {
  return (
    <div className="language-switcher">
      <button
        className={`lang-btn ${language === 'pt' ? 'active' : ''}`}
        onClick={() => onLanguageChange('pt')}
        title="Português"
      >
        🇧🇷 PT
      </button>
      <button
        className={`lang-btn ${language === 'en' ? 'active' : ''}`}
        onClick={() => onLanguageChange('en')}
        title="English"
      >
        🇺🇸 EN
      </button>
    </div>
  );
}
