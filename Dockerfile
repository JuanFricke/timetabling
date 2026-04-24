FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_CACHE_DIR=/tmp/uv-cache
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PYTHONPATH=/app/src

# Install dependencies (cached layer)
COPY pyproject.toml .python-version uv.lock README.md ./
RUN uv sync --frozen --no-dev

# Copy source code
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY data/ ./data/

CMD ["uv", "run", "python", "-m", "timetabling.main", "serve"]
