FROM golang:1.27.0-alpine@sha256:4c9fe60190a2a3350ddc51de80d0224b8a6698d12bdfc999fee45ea9d6c46dbc AS trivy-builder

RUN apk add --no-cache git
WORKDIR /trivy-source
RUN git clone https://github.com/aquasecurity/trivy.git . && \
    git checkout 89d3acfce93a34e2120dbff0f71c947aadce4c83 && \
    CGO_ENABLED=0 go build -trimpath -o /trivy ./cmd/trivy

FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Copy a commit-pinned Trivy build containing the current gRPC security fix.
COPY --from=trivy-builder /trivy /usr/local/bin/trivy

# Install Python dependencies
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir -r requirements.txt && \
    python -m pip uninstall --yes pip setuptools wheel

# Copy application files
COPY . .

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Make entrypoint scripts executable
RUN chmod 0755 /app/entrypoint.sh /app/worker-entrypoint.sh

# Expose port
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
