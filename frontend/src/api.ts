// src/api.ts — REST API calls to the FastAPI backend

const port = window.location.port
  ? `:${window.location.port}`
  : (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? ':8000' : '');
const BASE = `${window.location.protocol}//${window.location.hostname}${port}`;

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

export async function loginAuthority(pin: string, username = 'commander') {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin, username }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: 'Authentication failed' }));
    throw new Error(err.detail || 'Authentication failed');
  }
  return r.json();
}

export async function fetchCurrentAuthority(token: string) {
  const r = await fetch(`${BASE}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) return null;
  return r.json();
}

export async function fetchIncidents(params?: { severity?: string; status_filter?: string; camera_id?: string; limit?: number }) {
  const q = new URLSearchParams();
  if (params?.severity) q.set('severity', params.severity);
  if (params?.status_filter) q.set('status_filter', params.status_filter);
  if (params?.camera_id) q.set('camera_id', params.camera_id);
  if (params?.limit) q.set('limit', String(params.limit));
  const r = await fetch(`${BASE}/api/incidents?${q.toString()}`);
  return r.json();
}

export async function acknowledgeIncident(eventId: string, actor = 'Commander') {
  const r = await fetch(`${BASE}/api/incidents/${eventId}/acknowledge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor }),
  });
  if (!r.ok) throw new Error('Failed to acknowledge incident');
  return r.json();
}

export async function resolveIncident(eventId: string, actor = 'Commander', notes = 'Threat mitigated.') {
  const r = await fetch(`${BASE}/api/incidents/${eventId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor, notes }),
  });
  if (!r.ok) throw new Error('Failed to resolve incident');
  return r.json();
}

export async function fetchAuditLogs(limit = 50) {
  const r = await fetch(`${BASE}/api/authority/audit?limit=${limit}`);
  return r.json();
}

export async function fetchSystemHealth() {
  const r = await fetch(`${BASE}/api/authority/system-health`);
  return r.json();
}

export async function fetchEvidenceList(limit = 50) {
  const r = await fetch(`${BASE}/api/evidence-list?limit=${limit}`);
  return r.json();
}

export const STREAM_URL = `${BASE}/api/stream`;
export const BASE_URL = BASE;
