# syntax=docker/dockerfile:1
# Member-4 rl-service: venv + Jupyter Lab serving the DT/Sim/RL notebook.
# Python proposes decisions only; it never touches the Kubernetes API.
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /srv/rl-service

COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
    && /opt/venv/bin/python -m ipykernel install --name dt-ram --display-name "DT-RAM (venv)"

COPY rl_app ./rl_app
COPY notebooks ./notebooks
ENV PYTHONPATH="/srv/rl-service:/srv/simulation-service:${PYTHONPATH}"

EXPOSE 5001 8888
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD /opt/venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:8888/lab')"
CMD ["/opt/venv/bin/jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser", \
     "--notebook-dir=/srv/rl-service/notebooks"]
