FROM golang:1.27.0-alpine@sha256:4c9fe60190a2a3350ddc51de80d0224b8a6698d12bdfc999fee45ea9d6c46dbc AS buildx-builder

RUN apk add --no-cache git
WORKDIR /buildx-source
RUN git clone https://github.com/docker/buildx.git . && \
    git checkout 1b3aad3219b45e0c38532d0374c25858a4b08f35 && \
    go mod edit -require=github.com/moby/go-archive@v0.3.0 && \
    GOFLAGS=-mod=mod go mod tidy && \
    CGO_ENABLED=0 GOFLAGS=-mod=mod go build -trimpath -o /buildx ./cmd/buildx

FROM docker:29-cli@sha256:eccaacfeed644c7de222ff047483568cb988dde95476fbaaf10ea2d04921bb66

RUN apk upgrade --no-cache && \
    apk add --no-cache python3 py3-pip git ca-certificates && \
    python3 -m venv /venv && \
    /venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /agent
COPY requirements.txt ./
RUN /venv/bin/pip install --no-cache-dir -r requirements.txt
RUN /venv/bin/pip uninstall --yes pip setuptools wheel && \
    apk del py3-pip && \
    rm -f /usr/local/libexec/docker/cli-plugins/docker-buildx
COPY --from=buildx-builder /buildx /usr/local/libexec/docker/cli-plugins/docker-buildx
COPY app.py entrypoint.sh gunicorn_conf.py ./
RUN chmod 0755 /agent/entrypoint.sh && mkdir -p /opt/dockdash-managed

ENV PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 9002
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD python -c "import docker; docker.from_env(timeout=5).ping()"
ENTRYPOINT ["/agent/entrypoint.sh"]
