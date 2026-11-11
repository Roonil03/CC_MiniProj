# syntax=docker/dockerfile:1
# Member-4 rl-service: reproducible CLI for DT/Sim/RL experiments.
# Python proposes decisions only; it never touches the Kubernetes API.
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /srv/rl-service

COPY services/rl-service/requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
ARG TORCH_CUDA_INDEX=
RUN if [ -n "$TORCH_CUDA_INDEX" ]; then /opt/venv/bin/pip install --no-cache-dir --force-reinstall torch==2.5.1 --index-url "$TORCH_CUDA_INDEX"; fi

COPY services/rl-service/rl_app ./rl_app
COPY services/rl-service/cli.py ./cli.py
COPY services/simulation-service/app /srv/simulation-service/app
ENV PYTHONPATH="/srv/rl-service:/srv/simulation-service:${PYTHONPATH}"

CMD ["/opt/venv/bin/python", "cli.py", "--output", "/runs/member4.json"]
