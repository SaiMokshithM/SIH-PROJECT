"""
app.py — Hugging Face Spaces entry point.
=========================================
Mounts our complete AI Border Surveillance Command Center and React dashboard.
"""
import os
import uvicorn
from api.server import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    print(f"[HF Space] Launching AI Border Surveillance Command Center on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
