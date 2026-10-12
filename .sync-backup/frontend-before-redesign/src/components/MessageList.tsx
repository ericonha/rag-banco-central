import { useEffect, useRef } from 'react';
import type { Message } from '../types';
import { SourceCitations } from './SourceCitations';

interface MessageListProps {
  messages: Message[];
  loading: boolean;
}

export function MessageList({ messages, loading }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0 && !loading) {
    return (
      <div className="messages-placeholder">
        <h2>🤖 BCB RAG Chatbot</h2>
        <p>Faça uma pergunta sobre as normas e comunicados do Banco Central do Brasil.</p>
        <p>Ask a question about BCB regulations and communications.</p>
      </div>
    );
  }

  return (
    <div className="messages-container">
      {messages.map((message) => (
        <div key={message.id} className={`message message-${message.role}`}>
          <div className="message-content">
            <p className="message-text">{message.content}</p>
            {message.role === 'assistant' && message.sources && (
              <SourceCitations
                sources={message.sources}
                retrievedChunks={message.retrieved_chunks || 0}
              />
            )}
          </div>
          <div className="message-time">
            {message.timestamp.toLocaleTimeString('pt-BR', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </div>
        </div>
      ))}
      {loading && (
        <div className="message message-assistant">
          <div className="message-content">
            <div className="loading-indicator">
              <span className="dot"></span>
              <span className="dot"></span>
              <span className="dot"></span>
            </div>
          </div>
        </div>
      )}
      <div ref={messagesEndRef} />
    </div>
  );
}
