# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=8 \
    PREDICTION_DATA_PATH=/data/node_samples.sqlite \
    PREDICTION_REGISTRY_PATH=/models/registry.json

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt ./
ARG TORCH_CUDA_INDEX=
# Keep successfully downloaded packages across BuildKit retries and rebuilds.
RUN --mount=type=cache,target=/root/.cache/pip \
    install_with_retry() { \
      attempts=0; \
      until pip install "$@"; do \
        attempts=$((attempts + 1)); \
        if [ "$attempts" -ge 3 ]; then return 1; fi; \
        echo "pip install failed; retrying ($attempts/3)" >&2; \
        sleep 5; \
      done; \
    }; \
    install_with_retry torch==2.6.0 --index-url "${TORCH_CUDA_INDEX:-https://download.pytorch.org/whl/cpu}" && \
    install_with_retry -r requirements.txt
COPY prediction_app ./prediction_app
RUN mkdir -p /data /models && chown -R 10001:10001 /data /models /opt/venv
USER 10001:10001
EXPOSE 5000
CMD ["python", "-m", "uvicorn", "prediction_app.service:app", "--host", "0.0.0.0", "--port", "5000"]
