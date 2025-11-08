# ---------- Builder ----------
FROM python:3.11-slim AS builder
ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config wget \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PIP_NO_CACHE_DIR=1 \
    PIP_PREFER_BINARY=1

WORKDIR /app
COPY requirements.txt .

# Upgrade pip stack first
RUN pip install --upgrade pip setuptools wheel

# Install PaddleOCR WITHOUT dependencies (prevents PyMuPDF from being pulled)
RUN pip install --no-deps paddleocr==2.7.0.3
# CPU Paddle runtime
RUN pip install paddlepaddle==2.6.1

# Now install pinned deps (opencv headless, pypdfium2, torch, transformers, etc.)
RUN pip install -r requirements.txt

# Download PP-Structure models (table detection)
RUN mkdir -p /root/.paddleocr/whl/table && \
    wget -q https://paddleocr.bj.bcebos.com/ppstructure/models/slanet/en_ppstructure_mobile_v2.0_SLANet_infer.tar -O /tmp/table.tar && \
    tar -xf /tmp/table.tar -C /root/.paddleocr/whl/table && \
    rm /tmp/table.tar

# ---------- Runtime ----------
FROM python:3.11-slim AS runtime
ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /root/.paddleocr /root/.paddleocr
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY . .

EXPOSE 8080
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8080","--workers","2"]

