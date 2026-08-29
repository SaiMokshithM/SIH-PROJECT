"""
app.py — Hugging Face Spaces entry point.
=========================================
Mounts FastAPI and Gradio interface so Hugging Face Spaces serves the application seamlessly.
"""
import os
import uvicorn
import gradio as gr
from api.server import app

# Gradio interface container
with gr.Blocks(title="AI Border Surveillance Command Center") as demo:
    gr.HTML("""
        <style>
            body, html { margin: 0; padding: 0; height: 100vh; overflow: hidden; }
            iframe { width: 100%; height: 100vh; border: none; }
        </style>
        <iframe src="/" allow="camera; microphone; autoplay"></iframe>
    """)

# Mount Gradio app onto FastAPI app so Hugging Face supervisor detects Gradio
app = gr.mount_gradio_app(app, demo, path="/gradio")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    print(f"[HF Space] Launching on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
