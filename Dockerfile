# Docker image used for CI parity and local development
FROM python:3.12-slim

# Create non-root user for safety
RUN useradd -m sentient

WORKDIR /app
COPY . /app

# Install build tools for C-extension wheels
RUN apt-get update && apt-get install -y \
      build-essential gcc && \
    rm -rf /var/lib/apt/lists/*

# Install all dev dependencies
RUN pip install --no-cache-dir -r requirements-dev.txt

# Drop privileges
USER sentient

EXPOSE 5000

# Default command mirrors CI: run tests then launch API
CMD pytest -q && python sentient_api.py
