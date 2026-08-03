# SentientOS development container
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    ninja-build \
    binutils \
    git \
    curl \
    file \
    python3 \
    python3-pip \
    python3-venv \
    pkg-config \
    libssl-dev \
    libffi-dev \
    libjpeg-dev \
    zlib1g-dev \
    libgl1 \
    libglu1-mesa \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv \
    && python -m pip install --upgrade pip setuptools wheel

WORKDIR /workspace

CMD ["/bin/bash"]
