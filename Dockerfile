# Minimal runtime for SentientOS connector
# Use `--build-arg BASE_IMAGE=nvidia/cuda:12.3.2-runtime-ubuntu22.04` for GPU support
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

RUN apt-get update \
    && apt-get install -y --no-install-recommends vim-common gosu tini \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 --shell /bin/bash sentient
WORKDIR /workspace

# requirements.txt delegates to requirements-codex.txt; copy both before install.
COPY requirements.txt requirements-codex.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R sentient:sentient /workspace

USER sentient
ENV SENTIENTOS_DATA_DIR=/workspace/sentientos_data \
    PATH=/home/sentient/.local/bin:${PATH}

VOLUME ["/workspace"]
EXPOSE 5000

ENTRYPOINT ["tini", "--"]
CMD ["python", "sentientosd.py"]
