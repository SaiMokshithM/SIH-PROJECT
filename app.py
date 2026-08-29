"""
app.py — Hugging Face Spaces entry point.
=========================================
Mounts FastAPI and Gradio lifecycle hooks so Hugging Face Spaces keeps the app running 24/7.
"""
import os
import gradio as gr
from api.server import app

# Create Gradio wrapper to satisfy Hugging Face Gradio supervisor
with gr.Blocks(title="AI Border Surveillance Command Center", css="footer {visibility: hidden}") as demo:
    gr.HTML("""
        <style>
            body, html { margin: 0; padding: 0; height: 100%; overflow: hidden; }
            iframe { width: 100%; height: 95vh; border: none; }
        </style>
        <iframe src="/" allow="camera; microphone; autoplay"></iframe>
    """)

# Mount Gradio app onto FastAPI app
mounted_app = gr.mount_gradio_app(app, demo, path="/gradio")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    print(f"[HF Space] Launching on port {port}...")
    demo.launch(server_name="0.0.0.0", server_port=port, app=mounted_app)
