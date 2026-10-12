# BCB RAG Chatbot Frontend

React + TypeScript frontend for the BCB Regulatory AI chatbot.

## Features

- 🤖 Real-time chat with the RAG backend
- 📚 Source citations with expandable chunks
- 🌐 Bilingual support (Portuguese/English)
- 📱 Responsive mobile-first design
- ⚡ Built with React 18 + TypeScript + Vite

## Quick Start

### Prerequisites
- Node.js 18+
- npm or yarn

### Development

```bash
# Install dependencies
npm install

# Start development server (port 3000)
npm run dev

# The app will be available at http://localhost:3000
# Ensure the backend API is running on http://localhost:8000
```

### Production Build

```bash
# Build for production
npm run build

# Preview production build locally
npm run preview
```

## Project Structure

```
frontend/
├── src/
│   ├── components/          # React components
│   │   ├── ChatInterface    # Main chat component
│   │   ├── MessageList      # Message display
│   │   ├── SourceCitations  # Source references
│   │   └── LanguageSwitcher # Language toggle
│   ├── services/
│   │   └── api.ts           # API client
│   ├── types/
│   │   └── index.ts         # TypeScript interfaces
│   ├── App.tsx              # Root component
│   ├── App.css              # Component styles
│   ├── main.tsx             # Entry point
│   └── index.css            # Global styles
├── index.html               # HTML entry point
├── package.json             # Dependencies
├── tsconfig.json            # TypeScript config
├── vite.config.ts           # Vite config
└── Dockerfile               # Docker build config
```

## Configuration

### Environment Variables

Create a `.env` file based on `.env.example`:

```env
VITE_API_URL=http://localhost:8000/api
```

### API Integration

The frontend calls the following backend endpoints:

- `GET /api/health` — Health check
- `POST /api/chat` — Ask questions
- `GET /api/documents` — Browse documents
- `GET /api/conversations/{id}` — Conversation history (placeholder)

## Components

### ChatInterface
Main component that manages the chat state and user interaction.

### MessageList
Displays messages with animations and auto-scroll.

### SourceCitations
Shows cited sources with expandable chunk text.

### LanguageSwitcher
Toggles between Portuguese (PT) and English (EN).

## Styling

The app uses custom CSS with:
- Responsive flexbox layout
- Gradient backgrounds (purple theme)
- Smooth animations and transitions
- Mobile-first design

### Color Scheme
- Primary: `#667eea` to `#764ba2` (purple gradient)
- Secondary: `#f0f0f0` (light gray)
- Text: `#333` (dark gray)

## Docker Deployment

Build and run with Docker:

```bash
# Build image
docker build -t bcb-rag-frontend .

# Run container
docker run -p 3000:3000 -e VITE_API_URL=http://api:8000/api bcb-rag-frontend
```

## Technologies

- **React 18** — UI framework
- **TypeScript** — Type safety
- **Vite** — Fast build tool
- **CSS3** — Styling and animations

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## License

Part of the BCB RAG project. See main README for details.
