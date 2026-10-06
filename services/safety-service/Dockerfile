# syntax=docker/dockerfile:1
# Shared safety-service (Member-2 + Member-4): venv + uvicorn policy gate.
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /srv/safety-service

COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY app ./app
ENV PYTHONPATH="/srv/safety-service:/srv/simulation-service:${PYTHONPATH}"

EXPOSE 5003
CMD ["/opt/venv/bin/uvicorn", "safety_app.main:app", "--host", "0.0.0.0", "--port", "5003"]
