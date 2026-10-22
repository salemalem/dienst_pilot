FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY mcp_servers/pyproject.toml mcp_servers/pyproject.toml
COPY mcp_servers/src mcp_servers/src
COPY backend/pyproject.toml backend/pyproject.toml
COPY agents/pyproject.toml agents/pyproject.toml
COPY engine engine
COPY ml/pyproject.toml ml/pyproject.toml
COPY synthdata/pyproject.toml synthdata/pyproject.toml
COPY eval/pyproject.toml eval/pyproject.toml
RUN mkdir -p backend/src ml/src agents/src && uv sync --frozen --no-dev --package dienstpilot-mcp
EXPOSE 8200
CMD ["uvicorn", "dienstpilot_mcp.app:asgi", "--factory", "--host", "0.0.0.0", "--port", "8200"]
