# Minimal runtime for SentientOS connector
# Use `--build-arg BASE_IMAGE=nvidia/cuda:12.3.2-runtime-ubuntu22.04` for GPU support
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Runtime secrets are provided via environment variables
ARG CONNECTOR_TOKEN
ENV CONNECTOR_TOKEN=${CONNECTOR_TOKEN}
ARG PORT=5000
ENV PORT=${PORT}
EXPOSE ${PORT}

CMD ["python", "openai_connector.py"]
