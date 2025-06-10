# Docker image used for CI parity and local development
FROM python:3.12-slim

# Create non-root user for safety
RUN useradd -m sentient

WORKDIR /app
COPY . /app

# Install all dev dependencies
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-dev.txt

# Drop privileges
USER sentient

EXPOSE 5000

# Default command mirrors CI: run tests then launch API
CMD pytest -q && python sentient_api.py
