// src/api.ts — REST API calls to the FastAPI backend

const BASE = `http://${window.location.hostname}:${window.location.port || 8000}`;

export async function fetchStatus() {
  const r = await fetch(`${BASE}/api/status`);
  return r.json();
}

export async function fetchConfig() {
  const r = await fetch(`${BASE}/api/config`);
  return r.json();
}

export async function fetchCameras() {
  const r = await fetch(`${BASE}/api/cameras`);
  return r.json();
}

export async function fetchEvents(limit = 50) {
  const r = await fetch(`${BASE}/api/events?limit=${limit}`);
  return r.json();
}

export async function fetchZones() {
  const r = await fetch(`${BASE}/api/zones`);
  return r.json();
}

export async function startCamera(source: string, cameraId = 'camera_001') {
  const fd = new FormData();
  fd.append('source', source);
  fd.append('camera_id', cameraId);
  const r = await fetch(`${BASE}/api/start-camera`, { method: 'POST', body: fd });
  return r.json();
}

export async function stopCamera() {
  const r = await fetch(`${BASE}/api/stop-camera`, { method: 'POST' });
  return r.json();
}

export async function detectImage(file: File) {
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch(`${BASE}/api/detect/image`, { method: 'POST', body: fd });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || 'Detection failed');
  }
  return r.json();
}

export async function startVideoProcessing(file: File) {
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch(`${BASE}/api/detect/video/start`, { method: 'POST', body: fd });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: 'Video upload failed' }));
    throw new Error(err.detail || 'Video upload failed');
  }
  return r.json();
}

export const STREAM_URL = `${BASE}/api/stream`;
