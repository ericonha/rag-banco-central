import type { Language } from '../types';
import { STRINGS } from '../i18n';

interface LanguageSwitcherProps {
  language: Language;
  onLanguageChange: (lang: Language) => void;
}

const OPTIONS: { value: Language; label: string; title: string }[] = [
  { value: 'pt', label: 'PT', title: 'Português' },
  { value: 'en', label: 'EN', title: 'English' },
];

export function LanguageSwitcher({ language, onLanguageChange }: LanguageSwitcherProps) {
  return (
    <div className="segmented" role="group" aria-label={STRINGS[language].language}>
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          className={language === opt.value ? 'active' : ''}
          aria-pressed={language === opt.value}
          title={opt.title}
          onClick={() => onLanguageChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
