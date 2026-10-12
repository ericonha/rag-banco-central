FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/srv/.venv/bin:$PATH"
WORKDIR /srv

COPY pyproject.toml ./
RUN uv sync --no-dev

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

# Files copied from the host keep the host's permissions (e.g. 600 on macOS),
# which the non-root user could not read. Make everything world-readable.
RUN chmod -R a+rX /srv

RUN useradd --create-home appuser
USER appuser

# Run uvicorn from the prebuilt venv; no `uv run`, so nothing is re-resolved or written at start.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
