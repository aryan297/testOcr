FROM python:3.11-slim as builder

# Install build dependencies including SWIG for PyMuPDF
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    make \
    swig \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
# Upgrade pip first for better wheel support and install build tools
RUN pip install --upgrade pip setuptools wheel
# Install all dependencies (PyMuPDF will build from source with available tools)
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]

