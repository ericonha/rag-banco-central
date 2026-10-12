# BCB RAG

RAG chatbot over Banco Central do Brasil regulations. See `bcb-rag-plan.md` for the full plan.

## Quick start (Phase 0)

```bash
cp .env.example .env      # fill DATABASE_URL after the Phase 0 spike
docker compose up --build
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok","pgvector":"enabled"}`

---

## Features

- Fetch and store regulatory documents from the Central Bank of Brazil.
- Process and embed document data for downstream tasks.
- Query and analyze stored data using PostgreSQL.
- Support for Anthropic and embedding models for advanced processing.

---

## Prerequisites

Before setting up the project, ensure you have the following installed:

- **Docker** and **Docker Compose**
- **Python 3.8+** and `venv` for virtual environments
- **PostgreSQL** (if not using Docker)
- API keys for Anthropic and embedding providers

---

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/ericonha/rag-banco-central.git
cd rag-banco-central
```

### 2. Create and Activate Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the `.env` file and fill in the required values:

```bash
cp .env.example .env
```

Update the following variables in `.env`:

```properties
POSTGRES_USER=postgresml
POSTGRES_PASSWORD=postgresml
POSTGRES_DB=postgresml
DATABASE_URL=postgresql://postgresml:postgresml@db:5432/postgresml

ANTHROPIC_API_KEY=your-anthropic-api-key
ANTHROPIC_MODEL=claude-haiku-5-5

EMBEDDING_PROVIDER=your-provider
EMBEDDING_API_KEY=your-api-key
EMBEDDING_MODEL=intfloat/multilingual-e5-base
EMBEDDING_DIM=768

TZ=America/Sao_Paulo
```

### 5. Start Docker Services

```bash
docker compose up -d
```

---

## Usage

### 1. Fetch Data from the Central Bank API

Use the following `curl` command to fetch data:

```bash
curl -l GET "https://www.bcb.gov.br/api/conteudo/app/normativos/exibeoutrasnormas?p1=COMUNICADO&p2=36656"
```

### 2. Query the Database

Run queries directly in the database using Docker:

```bash
docker compose exec -e PGPASSWORD=postgresml db psql -h localhost -U postgresml -d postgresml -c \
"SELECT id, doc_type, published_at::date, left(title,60), length(raw_text) FROM documents ORDER BY published_at DESC;"
```

### 3. Run the Application

To run the application, execute the main script:

```bash
python main.py
```

---

## Database

The project uses a PostgreSQL database to store documents. The `documents` table contains the following fields:

- `id`: Unique identifier for each document.
- `doc_type`: Type of document (e.g., "Comunicado").
- `published_at`: Date the document was published.
- `title`: Title of the document.
- `raw_text`: Full text of the document.

---

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your changes.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Acknowledgments

- Central Bank of Brazil for providing the API.
- Anthropic for the language model support.
- Open-source contributors for embedding models and tools.