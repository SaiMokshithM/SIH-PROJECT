// src/types.ts — All TypeScript types matching the backend API

export interface Detection {
  track_id: number;
  class_name: string;
  category: string;
  confidence: number;
  bbox: [number, number, number, number];
  center: [number, number];
  movement_state: string;
  direction: string;
  is_confirmed: boolean;
  current_zone: string | null;
  risk_score: number;
  time_in_scene: number;
  first_seen: string;
  last_seen: string;
}

export interface AIEvent {
  event_id: string;
  event_type: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';
  camera_id: string;
  timestamp: string;
  track_id: number | null;
  object_type: string | null;
  zone_id: string | null;
  zone_name: string | null;
  description: string;
  risk_score: number;
  status?: 'NEW' | 'ACKNOWLEDGED' | 'INVESTIGATING' | 'RESOLVED';
  evidence_path?: string | null;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
  resolution_notes?: string | null;
  confidence?: number | null;
  bbox?: [number, number, number, number] | null;
}

export interface Incident extends AIEvent {
  status: 'NEW' | 'ACKNOWLEDGED' | 'INVESTIGATING' | 'RESOLVED';
}

export interface AuthorityUser {
  token: string;
  username: string;
  name: string;
  role: 'OPERATOR' | 'HIGHER_AUTHORITY' | 'AGENCY_ADMIN';
  badge: string;
  department: string;
  issued_at: number;
  expires_at: number;
}

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  action: string;
  actor: string;
  role: string;
  target_id: string | null;
  details: string;
  ip_address: string;
}

export interface SystemHealthInfo {
  system_status: 'OPERATIONAL' | 'DEGRADED' | 'OFFLINE';
  uptime_seconds: number;
  camera_status: string;
  fps: number;
  frame_number: number;
  active_tracks: number;
  session_events: number;
  ws_connected_clients: number;
  subsystems: {
    yolo_detector: { status: string; model: string };
    weapon_detector: { status: string };
    anpr_engine: { status: string };
    face_detector: { status: string };
    risk_engine: { status: string; score: number; level: string };
    zones_engine: { status: string; zones_loaded: number };
  };
}

export interface EvidenceItem {
  filename: string;
  path: string;
  size_bytes: number;
  modified: string;
}

export interface CameraInfo {
  id: string;
  name: string;
  location: string;
  enabled: boolean;
  status: 'online' | 'offline' | 'disabled';
  source: string;
}

export interface Counts {
  person: number;
  vehicle: number;
  animal: number;
  weapon?: number;
  plate?: number;
  total: number;
  tracked: number;
}

export interface ModuleStatus {
  anpr: boolean;
  weapon: boolean;
  face: boolean;
  zones: number;
}

export interface WSMessage {
  timestamp: string;
  camera_id: string;
  fps: number;
  model: string;
  processing: boolean;
  camera_status: 'online' | 'offline';
  is_night: boolean;
  risk_score: number;
  risk_level: string;
  counts: Counts;
  detections: Detection[];
  events: AIEvent[];
  module_status: ModuleStatus;
  error: string;
}

export type InputMode = 'live' | 'image' | 'video';

export interface ImageResult {
  annotated_image: string;
  detections: Detection[];
  counts: Counts;
  model: string;
  timestamp: string;
}
