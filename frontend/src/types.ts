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
}

export interface Counts {
  person: number;
  vehicle: number;
  animal: number;
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
