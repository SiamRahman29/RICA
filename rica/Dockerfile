FROM python:3.12-slim

# git + ssh for rica-ingest's knowledge repo sync
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY rica ./rica
RUN uv sync --frozen --no-dev \
 && python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"

# Volume mount points owned by the app user so named volumes inherit it
RUN useradd --uid 1000 --create-home rica && mkdir -p /knowledge /data /cache/fastembed \
 && chown rica /knowledge /data /cache/fastembed
USER rica

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"
CMD ["uvicorn", "rica.api:app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
