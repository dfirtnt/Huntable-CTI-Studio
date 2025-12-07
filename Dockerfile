# Use Python 3.11 slim image for production
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        postgresql-client \
        curl \
        git \
        ca-certificates \
        gnupg \
        lsb-release \
        tzdata \
        # Playwright browser dependencies
        libglib2.0-0 \
        libnspr4 \
        libnss3 \
        libdbus-1-3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libxcb1 \
        libxkbcommon0 \
        libatspi2.0-0 \
        libx11-6 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libcairo2 \
        libpango-1.0-0 \
        libasound2 \
        # Additional GUI dependencies for Playwright
        libxcursor1 \
        libgtk-3-0 \
        libgdk-pixbuf-2.0-0 \
        libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set timezone
ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install Docker CLI
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install test dependencies (for running tests in container)
COPY requirements-test.txt .
RUN pip install --no-cache-dir -r requirements-test.txt

# Ensure langgraph-cli is available system-wide
RUN pip install --no-cache-dir "langgraph-cli[inmem]"

# Update pip and setuptools to fix security vulnerabilities
RUN pip install --upgrade pip==25.2 setuptools==78.1.1

# Install security auditing tools
RUN pip install --no-cache-dir pip-audit==2.9.0 safety==3.2.0

# Copy project
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash cti_user \
    && chown -R cti_user:cti_user /app
USER cti_user

# Create necessary directories
RUN mkdir -p /app/logs /app/data

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Default command
CMD ["uvicorn", "src.web.modern_main:app", "--host", "0.0.0.0", "--port", "8001"]
