FROM nvidia/cuda:12.6.3-runtime-ubuntu22.04 AS base
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_CONSTRAINT=/opt/p40-constraints.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git ffmpeg libsndfile1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY p40-constraints.txt /opt/p40-constraints.txt
RUN python3 -m pip install --upgrade pip setuptools wheel \
    && python3 -m pip install torch==2.8.0+cu126 torchaudio==2.8.0+cu126 \
    --index-url https://download.pytorch.org/whl/cu126 \
    && python3 -m pip install numpy requests wyoming==1.10.0
RUN python3 -c "import torch; assert torch.__version__ == '2.8.0+cu126'; assert torch.version.cuda == '12.6'; assert 'sm_60' in torch._C._cuda_getArchFlags() or 'sm_61' in torch._C._cuda_getArchFlags(); print(torch._C._cuda_getArchFlags())"

FROM base AS runtime
COPY requirements.lock /opt/requirements.lock
RUN python3 -m pip install -r /opt/requirements.lock \
    && python3 -m pip check
ENV HF_HOME=/data/cache TORCH_HOME=/data/cache XDG_CACHE_HOME=/data/cache \
    HOME=/data PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    NUMBA_CACHE_DIR=/data/cache/numba OMNIVOICE_DEVICE=cpu
RUN groupadd --gid 568 apps && useradd --uid 568 --gid 568 --no-create-home --home-dir /data apps \
    && mkdir -p /data/cache /data/voices /app \
    && chown -R 568:568 /data
COPY wyoming_omnivoice.py healthcheck.py /app/
USER 568:568
WORKDIR /app
EXPOSE 10200
HEALTHCHECK --interval=30s --timeout=10s --start-period=30m --retries=3 CMD ["python3", "/app/healthcheck.py"]
ENTRYPOINT ["python3", "/app/wyoming_omnivoice.py"]
