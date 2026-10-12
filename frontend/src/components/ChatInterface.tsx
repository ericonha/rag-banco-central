import { useState, useRef, useEffect } from 'react';
import { MessageList } from './MessageList';
import { LanguageSwitcher } from './LanguageSwitcher';
import { ApiClient } from '../services/api';
import type { Message, Language, ChatResponse } from '../types';

export function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [language, setLanguage] = useState<Language>('pt');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [conversationId] = useState<string>(() => crypto.randomUUID());
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Check backend health on load
    ApiClient.checkHealth()
      .then(() => {
        console.log('✓ Backend is healthy');
        setError(undefined);
      })
      .catch((err) => {
        console.error('✗ Backend health check failed:', err);
        setError('Cannot connect to backend. Make sure the API is running.');
      });
  }, []);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();

    const trimmedInput = input.trim();
    if (!trimmedInput) return;

    // Add user message
    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmedInput,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setError(undefined);

    try {
      // Call backend
      const response: ChatResponse = await ApiClient.chat({
        question: trimmedInput,
        language,
        conversation_id: conversationId,
      });

      // Add assistant message
      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: response.answer,
        sources: response.sources,
        retrieved_chunks: response.retrieved_chunks,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      console.error('Chat error:', err);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  return (
    <div className="chat-interface">
      <div className="chat-header">
        <div className="header-content">
          <h1>BCB RAG Chatbot</h1>
          <LanguageSwitcher language={language} onLanguageChange={setLanguage} />
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <MessageList messages={messages} loading={loading} />

      <form className="chat-input-form" onSubmit={handleSendMessage}>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            language === 'pt'
              ? 'Digite sua pergunta...'
              : 'Type your question...'
          }
          disabled={loading}
          className="chat-input"
          autoFocus
        />
        <button type="submit" disabled={loading || !input.trim()} className="send-button">
          {loading ? '⏳' : '📤'}
        </button>
      </form>
    </div>
  );
}
