import type { Language } from './types';

const pt = {
  brand: 'Normas BCB',
  newChat: 'Nova conversa',
  history: 'Conversas',
  noHistory: 'As conversas aparecem aqui depois da primeira pergunta.',
  chat: 'Conversa',
  logs: 'Logs',
  logsTitle: 'Logs do pipeline',
  docs: 'Documentos',
  docsTitle: 'Documentos indexados',
  deleteChat: 'Remover conversa',
  openMenu: 'Abrir menu',
  untitled: 'Nova conversa',
  emptyTitle: 'Pergunte sobre normas e comunicados do Banco Central',
  emptyBody:
    'As respostas vêm dos documentos indexados e citam as fontes. Clique em um número para ver o trecho usado.',
  examplesLabel: 'Exemplos',
  examples: [
    'O que diz o Comunicado nº 34.977?',
    'Qual o cronograma do primeiro ciclo de qualidade de dados do CCS?',
    'O que é o Catálogo de Serviços do SFN?',
  ],
  placeholder: 'Escreva sua pergunta',
  send: 'Enviar pergunta',
  sources: 'Fontes',
  sourceWord: 'Fonte',
  chunks: 'trechos analisados',
  connectError: 'Não foi possível conectar à API. Verifique se o serviço está em execução.',
  disclaimer: 'Respostas geradas a partir de documentos públicos do BCB. Confirme nas fontes antes de decidir.',
  language: 'Idioma da resposta',
};

const en: typeof pt = {
  brand: 'BCB Regulations',
  newChat: 'New chat',
  history: 'Chats',
  noHistory: 'Chats show up here after your first question.',
  chat: 'Chat',
  logs: 'Logs',
  logsTitle: 'Pipeline logs',
  docs: 'Documents',
  docsTitle: 'Indexed documents',
  deleteChat: 'Delete chat',
  openMenu: 'Open menu',
  untitled: 'New chat',
  emptyTitle: 'Ask about Banco Central regulations and notices',
  emptyBody:
    'Answers come from the indexed documents and cite their sources. Click a number to see the passage used.',
  examplesLabel: 'Examples',
  examples: [
    'What does Comunicado nº 34.977 say?',
    'What is the schedule for the first CCS data quality cycle?',
    'What is the SFN Service Catalog?',
  ],
  placeholder: 'Write your question',
  send: 'Send question',
  sources: 'Sources',
  sourceWord: 'Source',
  chunks: 'passages reviewed',
  connectError: 'Could not reach the API. Check that the service is running.',
  disclaimer: 'Answers are generated from public BCB documents. Check the sources before you act on them.',
  language: 'Answer language',
};

export const STRINGS: Record<Language, typeof pt> = { pt, en };
