# ---------- Stage 1: build ----------
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system deps needed for mysql-connector and py7zr
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first (Docker layer caching)
COPY agent-requirements.txt service/requirements.txt ./
ARG HTTP_PROXY
ARG HTTPS_PROXY
RUN pip install --no-cache-dir \
    -r agent-requirements.txt -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim

WORKDIR /app

# Install Azure CLI (needed for az login / Managed Identity token)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl gnupg lsb-release && \
    curl -sL https://aka.ms/InstallAzureCLIDeb | bash && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY agent/ ./agent/
COPY tools/ ./tools/
COPY service/ ./service/

# Non-root user for security
RUN useradd --create-home appuser
USER appuser

# Expose the service port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Start uvicorn
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
