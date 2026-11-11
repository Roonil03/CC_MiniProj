FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PREDICTION_DATA_PATH=/data/node_samples.sqlite \
    PREDICTION_REGISTRY_PATH=/models/registry.json

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
ARG TORCH_CUDA_INDEX=
RUN if [ -n "$TORCH_CUDA_INDEX" ]; then pip install --no-cache-dir --force-reinstall torch==2.5.1 --index-url "$TORCH_CUDA_INDEX"; fi
COPY prediction_app ./prediction_app
RUN mkdir -p /data /models && chown -R 10001:10001 /data /models
USER 10001:10001
EXPOSE 5000
CMD ["python", "-m", "uvicorn", "prediction_app.service:app", "--host", "0.0.0.0", "--port", "5000"]
