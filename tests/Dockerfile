FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534

WORKDIR /validation
COPY requirements.txt ./controller-requirements.txt
COPY agent/requirements.txt ./agent-requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir -r controller-requirements.txt -r agent-requirements.txt && \
    python -m pip uninstall --yes pip setuptools wheel
