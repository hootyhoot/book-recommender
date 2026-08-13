# Build stage
FROM python:3.8.18-slim AS builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements-render.txt .

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies (runtime-only set; app.py never imports torch/transformers)
RUN pip install --no-cache-dir -r requirements-render.txt

# Pre-download NLTK corpora at build time instead of on every container start,
# straight into the venv so it comes along with the COPY --from=builder below.
ENV NLTK_DATA=/opt/venv/nltk_data
RUN python -m nltk.downloader -d /opt/venv/nltk_data punkt stopwords wordnet && \
    python -c "import zipfile; zipfile.ZipFile('/opt/venv/nltk_data/corpora/wordnet.zip').extractall('/opt/venv/nltk_data/corpora/')"

# Remove unnecessary files from venv
RUN find /opt/venv -name "*.pyc" -delete && \
    find /opt/venv -name "*.pyo" -delete && \
    find /opt/venv -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -name "test" -type d -exec rm -rf {} + 2>/dev/null || true && \
    rm -rf /opt/venv/lib/python3.8/site-packages/pip

# Runtime stage
FROM python:3.8.18-slim

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy only the virtual environment (includes pre-downloaded NLTK data) from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY . .

# Set environment to use the venv
ENV PATH="/opt/venv/bin:$PATH"
ENV NLTK_DATA=/opt/venv/nltk_data

# Run the application
CMD ["python", "app.py"]
