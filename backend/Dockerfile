FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/src backend/src
COPY engine engine
COPY synthdata/pyproject.toml synthdata/pyproject.toml
COPY eval/pyproject.toml eval/pyproject.toml
RUN uv sync --frozen --no-dev --package dienstpilot
# The transparency screen (W13) shows the eval summaries written by eval/ scripts.
COPY eval/results eval/results

COPY backend backend
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn dienstpilot.main:app --host 0.0.0.0 --port 8000"]
