"""
app.py — Hugging Face Spaces entry point.
=========================================
Mounts FastAPI into Gradio so Hugging Face Spaces serves the application natively.
"""
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

# Mount Gradio onto our FastAPI application
app = gr.mount_gradio_app(app, demo, path="/gradio")

# Launch Gradio using its native server (no port collision)
if __name__ == "__main__":
    demo.launch()
