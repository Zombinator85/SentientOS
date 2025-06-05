# Minimal runtime for SentientOS connector
FROM python:3.11-slim
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
