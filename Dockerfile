FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and buffer output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=sse \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

# Install dependencies and project
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

EXPOSE 8000

# Entrypoint runs the SSE server for remote agent network connectivity
CMD ["unofficial-proxmox-mcp", "--transport", "sse", "--host", "0.0.0.0", "--port", "8000"]
