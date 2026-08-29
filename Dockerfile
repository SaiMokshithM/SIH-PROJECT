FROM python:3.10-slim

# Install system dependencies for OpenCV, OCR, and AI analytics
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    tesseract-ocr \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set up user for Hugging Face Spaces permission compliance
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copy and install python dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application codebase and pre-built frontend distribution
COPY --chown=user . .

# Expose port 7860 (Hugging Face default) and 8000
EXPOSE 7860
EXPOSE 8000

# Start server
CMD ["python", "run_dashboard.py", "--host", "0.0.0.0", "--port", "7860"]
