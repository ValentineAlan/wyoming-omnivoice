FROM python:3.12-slim-bookworm
ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ffmpeg libsndfile1 ca-certificates g++ ninja-build \
    && rm -rf /var/lib/apt/lists/*
COPY constraints.txt /opt/constraints.txt
COPY requirements.lock /opt/requirements.lock
ENV PIP_CONSTRAINT=/opt/requirements.lock
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install torch==2.14.0+cu130 torchaudio==2.11.0+cu130 \
       --index-url https://download.pytorch.org/whl/cu130 --extra-index-url https://pypi.org/simple
RUN python -m pip install \
    'omnivoice @ git+https://github.com/k2-fsa/OmniVoice.git@08be0b4ccbac3e13e374e86fbfead4b4cac343e2' \
    transformers==5.17.0 torchcodec==0.16.0 wyoming==1.10.2 \
    flashinfer-python==0.6.18.post1 \
    && python -m pip install flashinfer-jit-cache==0.6.18.post1+cu130 \
       --index-url https://flashinfer.ai/whl/cu130 \
    && python -m pip check \
    && python -m pip freeze > /opt/requirements.freeze.txt
RUN python -c "import torch, torchaudio, torchcodec; from omnivoice.models.omnivoice import OmniVoice; assert torch.version.cuda == '13.0'; print(torch.__version__, torchaudio.__version__, torch._C._cuda_getArchFlags())"
ENV HF_HOME=/data/cache TORCH_HOME=/data/cache XDG_CACHE_HOME=/data/cache \
    HOME=/data NUMBA_CACHE_DIR=/data/cache/numba NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV OMNIVOICE_DEVICE=cpu HF_HUB_DISABLE_PROGRESS_BARS=1
RUN groupadd --gid 568 apps && useradd --uid 568 --gid 568 --no-create-home --home-dir /data apps \
    && mkdir -p /data/cache /data/voices /app && chown -R 568:568 /data
COPY wyoming_omnivoice.py voice_files.py acceleration.py healthcheck.py /app/
COPY voices/ /opt/omnivoice/example-voices/
USER 568:568
WORKDIR /app
EXPOSE 10200
HEALTHCHECK --interval=30s --timeout=10s --start-period=30m --retries=3 CMD ["python3", "/app/healthcheck.py"]
ENTRYPOINT ["python3", "/app/wyoming_omnivoice.py"]
