FROM python:3.10-slim

# Install system dependencies for OpenCV and image analytics
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    tesseract-ocr \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application codebase and built frontend distribution
COPY . .

# Expose port 8000 for FastAPI + WebSocket
EXPOSE 8000

# Start server
CMD ["python", "run_dashboard.py", "--host", "0.0.0.0", "--port", "8000"]
