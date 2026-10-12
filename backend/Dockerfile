FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/srv/.venv/bin:$PATH"
WORKDIR /srv

COPY backend/pyproject.toml ./
# Install all deps including dev (pytest etc.)
RUN uv sync

COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY tests ./tests

# Make everything world-readable (Mac sets 600 on COPY'd files)
RUN chmod -R a+rX /srv

RUN useradd --create-home appuser
USER appuser

CMD ["sh", "-c", "until alembic upgrade head; do echo waiting for db; sleep 3; done; exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
