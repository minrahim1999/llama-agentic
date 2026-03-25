FROM python:3.12-slim

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project
COPY pyproject.toml ./
COPY agent/ ./agent/
COPY plugins/ ./plugins/

# Install the package
RUN uv pip install --system -e .

# llama-server is expected to be provided via volume or environment variable
# Mount your model: -v /path/to/models:/models
# Set LLAMA_SERVER_URL to point to a running llama-server or use auto-start

ENV LLAMA_SERVER_URL=http://host.docker.internal:8080/v1

# Data dirs inside the container
ENV MEMORY_DIR=/data/memory
ENV SESSIONS_DIR=/data/sessions
ENV MODEL_CACHE_DIR=/models

VOLUME ["/data", "/models"]

ENTRYPOINT ["llama-agent"]
CMD ["--help"]
