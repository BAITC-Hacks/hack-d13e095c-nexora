FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
RUN mkdir -p /app/storage /models && chown -R app:app /app /models

FROM base AS api
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM base AS worker
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
COPY requirements-ai.txt .
RUN pip install --index-url ${TORCH_INDEX_URL} torch==2.8.0 torchaudio==2.8.0 \
    && pip install -r requirements-ai.txt
ENV HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 PYANNOTE_METRICS_ENABLED=0
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib:/usr/local/lib/python3.12/site-packages/nvidia/cuda_runtime/lib
USER app
CMD ["python", "-m", "app.worker"]

FROM base AS bootstrap
RUN pip install huggingface-hub==0.36.0
COPY scripts/bootstrap_models.py ./scripts/bootstrap_models.py
# The initialization service writes only model weights; it never mounts meeting storage.
CMD ["python", "scripts/bootstrap_models.py"]

FROM base AS speech
COPY requirements-speech.txt .
RUN pip install -r requirements-speech.txt
ENV HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
USER app
EXPOSE 8001
CMD ["uvicorn", "app.speech_server:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]

FROM base AS speech-bootstrap
RUN pip install huggingface-hub==0.36.0
COPY scripts/bootstrap_speech.py ./scripts/bootstrap_speech.py
CMD ["python", "scripts/bootstrap_speech.py"]

FROM speech AS speech-gpu
USER root
RUN pip install nvidia-cublas-cu12==12.8.4.1 nvidia-cudnn-cu12==9.10.2.21
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib
USER app

FROM base AS tests
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY tests ./tests
COPY pyproject.toml .
CMD ["pytest", "-q"]
