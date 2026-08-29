import { useState, useEffect, useCallback } from 'react';
import {
  fetchIncidents,
  acknowledgeIncident,
  resolveIncident,
  fetchAuditLogs,
  fetchSystemHealth,
  fetchEvidenceList,
  fetchCameras,
  STREAM_URL,
} from '../api';
import type {
  WSMessage,
  AuthorityUser,
  Incident,
  AuditLogEntry,
  SystemHealthInfo,
  EvidenceItem,
  CameraInfo,
} from '../types';

interface Props {
  user: AuthorityUser;
  msg: WSMessage | null;
  wsStatus: string;
  onExit: () => void;
}

const sevBadge = (sev: string) => {
  const map: Record<string, { bg: string; color: string; border: string }> = {
    CRITICAL: { bg: 'rgba(255,59,92,0.15)', color: '#ff3b5c', border: 'rgba(255,59,92,0.4)' },
    HIGH: { bg: 'rgba(255,112,67,0.15)', color: '#ff7043', border: 'rgba(255,112,67,0.4)' },
    MEDIUM: { bg: 'rgba(255,180,68,0.15)', color: '#ffb444', border: 'rgba(255,180,68,0.4)' },
    LOW: { bg: 'rgba(0,255,136,0.15)', color: '#00ff88', border: 'rgba(0,255,136,0.4)' },
    INFO: { bg: 'rgba(56,182,255,0.15)', color: '#38b6ff', border: 'rgba(56,182,255,0.4)' },
  };
  const s = map[sev.toUpperCase()] || map.INFO;
  return (
    <span
      style={{
        background: s.bg,
        color: s.color,
        border: `1px solid ${s.border}`,
        borderRadius: 4,
        padding: '2px 8px',
        fontSize: 10,
        fontWeight: 800,
        letterSpacing: '0.08em',
      }}
    >
      {sev.toUpperCase()}
    </span>
  );
};

const statusBadge = (st: string = 'NEW') => {
  const map: Record<string, { bg: string; color: string }> = {
    NEW: { bg: '#7f1d1d', color: '#fca5a5' },
    ACKNOWLEDGED: { bg: '#78350f', color: '#fde68a' },
    INVESTIGATING: { bg: '#1e3a8a', color: '#93c5fd' },
    RESOLVED: { bg: '#064e3b', color: '#6ee7b7' },
  };
  const s = map[st.toUpperCase()] || map.NEW;
  return (
    <span
      style={{
        background: s.bg,
        color: s.color,
        borderRadius: 99,
        padding: '2px 10px',
        fontSize: 9,
        fontWeight: 800,
        letterSpacing: '0.08em',
      }}
    >
      ● {st.toUpperCase()}
    </span>
  );
};

export function AuthorityPortal({ user, msg, wsStatus, onExit }: Props) {
  const [tab, setTab] = useState<'overview' | 'incidents' | 'cameras' | 'evidence' | 'health' | 'audit'>('overview');
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [health, setHealth] = useState<SystemHealthInfo | null>(null);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState('');
  const [resolveNotes, setResolveNotes] = useState('');
  const [showResolveModal, setShowResolveModal] = useState(false);

  // Filters
  const [sevFilter, setSevFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Load data
  const loadData = useCallback(async () => {
    try {
      const [incData, camData, audData, hData, evData] = await Promise.all([
        fetchIncidents({ severity: sevFilter, status_filter: statusFilter, limit: 100 }),
        fetchCameras(),
        fetchAuditLogs(50),
        fetchSystemHealth(),
        fetchEvidenceList(50),
      ]);
      setIncidents(incData || []);
      setCameras(camData || []);
      setAuditLogs(audData || []);
      setHealth(hData || null);
      setEvidenceList(evData || []);
    } catch (e) {
      console.error('Error loading authority data:', e);
    }
  }, [sevFilter, statusFilter]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 4000);
    return () => clearInterval(interval);
  }, [loadData]);

  // Handle Acknowledge
  const handleAcknowledge = async (eventId: string) => {
    try {
      setLoading(true);
      await acknowledgeIncident(eventId, user.name);
      setActionMsg(`Incident ${eventId} acknowledged by ${user.name}`);
      await loadData();
      if (selectedIncident && selectedIncident.event_id === eventId) {
        setSelectedIncident((prev) => (prev ? { ...prev, status: 'ACKNOWLEDGED', acknowledged_by: user.name } : null));
      }
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    } finally {
      setLoading(false);
      setTimeout(() => setActionMsg(''), 4000);
    }
  };

  // Handle Resolve
  const handleResolve = async (eventId: string) => {
    try {
      setLoading(true);
      await resolveIncident(eventId, user.name, resolveNotes || 'Verified & resolved by Higher Authority');
      setActionMsg(`Incident ${eventId} resolved successfully.`);
      setShowResolveModal(false);
      setResolveNotes('');
      await loadData();
      if (selectedIncident && selectedIncident.event_id === eventId) {
        setSelectedIncident((prev) => (prev ? { ...prev, status: 'RESOLVED', resolved_by: user.name } : null));
      }
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    } finally {
      setLoading(false);
      setTimeout(() => setActionMsg(''), 4000);
    }
  };

  // Active critical alert from latest WebSocket message
  const latestCritEvent = msg?.events?.find(
    (e) => (e.severity === 'CRITICAL' || e.severity === 'HIGH') && (!e.status || e.status === 'NEW')
  );

  const activeIncidentsCount = incidents.filter((i) => i.status === 'NEW' || i.status === 'INVESTIGATING').length;
  const criticalCount = incidents.filter((i) => i.severity === 'CRITICAL').length;
  const activeCamerasCount = cameras.filter((c) => c.status === 'online').length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg-void)', overflow: 'hidden' }}>
      {/* ── Authority Header ── */}
      <header
        style={{
          background: 'linear-gradient(180deg, #020712 0%, #040d1a 100%)',
          borderBottom: '1px solid rgba(255, 180, 68, 0.25)',
          padding: '0 24px',
          height: 62,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'sticky',
          top: 0,
          zIndex: 300,
          boxShadow: '0 4px 30px rgba(0,0,0,0.85)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div
            style={{
              width: 40,
              height: 40,
              background: 'linear-gradient(135deg, rgba(255, 180, 68, 0.2), rgba(255, 59, 92, 0.15))',
              border: '1px solid rgba(255, 180, 68, 0.4)',
              borderRadius: 10,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 20,
              boxShadow: '0 0 25px rgba(255, 180, 68, 0.2)',
            }}
          >
            🏛
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 900, letterSpacing: '0.14em', color: '#ffb444' }}>
                BORDER SURVEILLANCE COMMAND
              </span>
              <span
                style={{
                  background: 'rgba(255, 180, 68, 0.15)',
                  border: '1px solid rgba(255, 180, 68, 0.35)',
                  color: '#ffb444',
                  fontSize: 9,
                  fontWeight: 800,
                  padding: '2px 8px',
                  borderRadius: 4,
                  letterSpacing: '0.1em',
                }}
              >
                HIGHER AUTHORITY PORTAL
              </span>
            </div>
            <div style={{ fontSize: 9, letterSpacing: '0.15em', color: 'var(--text-muted)' }}>
              AGENCY HEADQUARTERS · REAL-TIME STRATEGIC OVERVIEW · SIH 2026
            </div>
          </div>
        </div>

        {/* User Identity & Clearance */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <div
            style={{
              background: wsStatus === 'connected' ? 'rgba(0, 255, 136, 0.1)' : 'rgba(255, 59, 92, 0.1)',
              border: `1px solid ${wsStatus === 'connected' ? 'rgba(0, 255, 136, 0.3)' : 'rgba(255, 59, 92, 0.3)'}`,
              color: wsStatus === 'connected' ? '#00ff88' : '#ff3b5c',
              fontSize: 9,
              fontWeight: 800,
              padding: '4px 10px',
              borderRadius: 99,
              letterSpacing: '0.1em',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <div className={wsStatus === 'connected' ? 'dot-live' : 'dot-offline'} style={{ width: 6, height: 6 }} />
            WS {wsStatus.toUpperCase()}
          </div>

          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: '#fff', letterSpacing: '0.06em' }}>
              {user.name}
            </div>
            <div style={{ fontSize: 9, color: '#ffb444', letterSpacing: '0.08em', fontWeight: 600 }}>
              {user.role} · {user.badge}
            </div>
          </div>

          <button
            onClick={onExit}
            style={{
              background: 'rgba(56, 182, 255, 0.12)',
              border: '1px solid rgba(56, 182, 255, 0.3)',
              color: 'var(--accent-blue)',
              borderRadius: 8,
              padding: '6px 14px',
              fontSize: 10,
              fontWeight: 800,
              letterSpacing: '0.1em',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            ← OPERATOR VIEW
          </button>
        </div>
      </header>

      {/* ── Real-Time Critical Alert Banner ── */}
      {latestCritEvent && (
        <div
          style={{
            background: 'linear-gradient(90deg, #7f1d1d 0%, #450a0a 100%)',
            borderBottom: '2px solid #ef4444',
            padding: '10px 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            animation: 'pulse 2s infinite',
            zIndex: 250,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ fontSize: 22, animation: 'spin 3s linear infinite' }}>🚨</div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 900, color: '#fef2f2', letterSpacing: '0.1em' }}>
                CRITICAL SECURITY EVENT IN PROGRESS · {latestCritEvent.event_type}
              </div>
              <div style={{ fontSize: 10, color: '#fca5a5' }}>
                Camera: <strong>{latestCritEvent.camera_id}</strong> | Zone: {latestCritEvent.zone_name || 'Restricted Zone'} | Time: {latestCritEvent.timestamp}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              onClick={() => handleAcknowledge(latestCritEvent.event_id)}
              style={{
                background: '#dc2626',
                border: '1px solid #f87171',
                color: '#fff',
                borderRadius: 6,
                padding: '6px 14px',
                fontSize: 11,
                fontWeight: 800,
                cursor: 'pointer',
              }}
            >
              ✓ ACKNOWLEDGE
            </button>
            <button
              onClick={() => {
                setTab('incidents');
                setSelectedIncident(latestCritEvent as Incident);
              }}
              style={{
                background: 'rgba(0,0,0,0.5)',
                border: '1px solid #fca5a5',
                color: '#fff',
                borderRadius: 6,
                padding: '6px 14px',
                fontSize: 11,
                fontWeight: 800,
                cursor: 'pointer',
              }}
            >
              VIEW DOSSIER →
            </button>
          </div>
        </div>
      )}

      {/* Action Notification */}
      {actionMsg && (
        <div style={{ background: '#064e3b', color: '#6ee7b7', padding: '8px 24px', fontSize: 11, fontWeight: 700, textAlign: 'center' }}>
          ✓ {actionMsg}
        </div>
      )}

      {/* ── Main Authority Body with Navigation ── */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Navigation Sidebar */}
        <nav
          style={{
            width: 220,
            background: 'linear-gradient(180deg, #020712, #040c18)',
            borderRight: '1px solid rgba(255, 180, 68, 0.15)',
            display: 'flex',
            flexDirection: 'column',
            padding: '16px 12px',
            gap: 6,
            flexShrink: 0,
          }}
        >
          <div style={{ fontSize: 9, fontWeight: 800, color: 'var(--text-dim)', letterSpacing: '0.15em', padding: '6px 12px' }}>
            COMMAND SECTIONS
          </div>
          {[
            { id: 'overview', icon: '📊', label: 'Overview & Posture' },
            { id: 'incidents', icon: '🚨', label: 'Incident Center', count: activeIncidentsCount },
            { id: 'cameras', icon: '🎥', label: 'Camera Network', count: activeCamerasCount },
            { id: 'evidence', icon: '📁', label: 'Evidence Vault', count: evidenceList.length },
            { id: 'health', icon: '⚡', label: 'System & AI Health' },
            { id: 'audit', icon: '📜', label: 'Security Audit Log' },
          ].map((item) => {
            const active = tab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setTab(item.id as any)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 14px',
                  borderRadius: 8,
                  border: active ? '1px solid rgba(255, 180, 68, 0.4)' : '1px solid transparent',
                  background: active ? 'rgba(255, 180, 68, 0.12)' : 'transparent',
                  color: active ? '#ffb444' : 'var(--text-secondary)',
                  fontSize: 12,
                  fontWeight: active ? 800 : 600,
                  letterSpacing: '0.04em',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.15s',
                }}
              >
                <span style={{ fontSize: 16 }}>{item.icon}</span>
                <span style={{ flex: 1 }}>{item.label}</span>
                {item.count !== undefined && item.count > 0 && (
                  <span
                    style={{
                      background: active ? '#ffb444' : 'rgba(255,255,255,0.1)',
                      color: active ? '#000' : '#fff',
                      fontSize: 9,
                      fontWeight: 800,
                      borderRadius: 99,
                      padding: '1px 6px',
                    }}
                  >
                    {item.count}
                  </span>
                )}
              </button>
            );
          })}

          <div style={{ marginTop: 'auto', padding: '12px', background: 'rgba(0,0,0,0.3)', borderRadius: 8, border: '1px solid rgba(255,180,68,0.1)' }}>
            <div style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>CLEARANCE LEVEL</div>
            <div style={{ fontSize: 11, fontWeight: 800, color: '#ffb444', marginTop: 2 }}>{user.department}</div>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 4 }}>ID: {user.badge}</div>
          </div>
        </nav>

        {/* Content Area */}
        <main style={{ flex: 1, overflowY: 'auto', background: 'var(--bg-base)', padding: '20px 24px' }}>
          {/* ══════════ 1. OVERVIEW & POSTURE TAB ══════════ */}
          {tab === 'overview' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              {/* Telemetry Stat Row */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 12 }}>
                <div className="panel panel-glow" style={{ padding: 14 }}>
                  <div style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.12em', fontWeight: 700 }}>ACTIVE CAMERAS</div>
                  <div style={{ fontSize: 24, fontWeight: 900, color: '#00ff88', marginTop: 4 }}>{activeCamerasCount} / {cameras.length}</div>
                  <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>Real-time RTSP/Webcam</div>
                </div>

                <div className="panel panel-glow" style={{ padding: 14 }}>
                  <div style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.12em', fontWeight: 700 }}>ACTIVE INCIDENTS</div>
                  <div style={{ fontSize: 24, fontWeight: 900, color: activeIncidentsCount > 0 ? '#ff3b5c' : '#00ff88', marginTop: 4 }}>
                    {activeIncidentsCount}
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>{criticalCount} Critical Threats</div>
                </div>

                <div className="panel panel-glow" style={{ padding: 14 }}>
                  <div style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.12em', fontWeight: 700 }}>TRACKED SUBJECTS</div>
                  <div style={{ fontSize: 24, fontWeight: 900, color: 'var(--accent-cyan)', marginTop: 4 }}>
                    {msg?.counts?.tracked ?? 0}
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>Kalman Trackers Active</div>
                </div>

                <div className="panel panel-glow" style={{ padding: 14 }}>
                  <div style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.12em', fontWeight: 700 }}>PEOPLE IN PERIMETER</div>
                  <div style={{ fontSize: 24, fontWeight: 900, color: 'var(--accent-blue)', marginTop: 4 }}>
                    {msg?.counts?.person ?? 0}
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>YOLOv8 + Face Verified</div>
                </div>

                <div className="panel panel-glow" style={{ padding: 14 }}>
                  <div style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.12em', fontWeight: 700 }}>WEAPONS DETECTED</div>
                  <div style={{ fontSize: 24, fontWeight: 900, color: (msg?.counts?.weapon ?? 0) > 0 ? '#ff3b5c' : '#3d6080', marginTop: 4 }}>
                    {msg?.counts?.weapon ?? 0}
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>Firearm AI Model</div>
                </div>

                <div className="panel panel-glow" style={{ padding: 14 }}>
                  <div style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.12em', fontWeight: 700 }}>OPERATIONAL THREAT</div>
                  <div style={{ fontSize: 24, fontWeight: 900, color: msg?.risk_score && msg.risk_score >= 80 ? '#ff3b5c' : '#ffb444', marginTop: 4 }}>
                    {msg?.risk_score ?? 0} / 100
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>{msg?.risk_level ?? 'INFO'}</div>
                </div>
              </div>

              {/* 2-Column Command View */}
              <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 16 }}>
                {/* Live Surveillance Preview */}
                <div className="panel panel-glow">
                  <div className="panel-header">
                    <div className="panel-header-icon">🎥</div>
                    LIVE AGENCY SURVEILLANCE FEED · CAMERA_001
                    <span className="badge badge-green" style={{ marginLeft: 'auto' }}>● LIVE STREAM</span>
                  </div>
                  <div style={{ padding: 12 }}>
                    <div style={{ position: 'relative', background: '#000', borderRadius: 8, overflow: 'hidden', minHeight: 320 }}>
                      <img src={STREAM_URL} style={{ width: '100%', display: 'block', minHeight: 320, objectFit: 'contain' }} alt="Live Camera" />
                      <div className="scanline-overlay" />
                    </div>
                  </div>
                </div>

                {/* Critical Security Incidents List */}
                <div className="panel panel-glow" style={{ display: 'flex', flexDirection: 'column' }}>
                  <div className="panel-header">
                    <div className="panel-header-icon">🚨</div>
                    RECENT CRITICAL INCIDENTS
                    <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-muted)' }}>{incidents.length} TOTAL</span>
                  </div>
                  <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 10, flex: 1, overflowY: 'auto', maxHeight: 360 }}>
                    {incidents.length === 0 ? (
                      <div style={{ padding: 30, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12 }}>
                        No active security incidents recorded.
                      </div>
                    ) : (
                      incidents.slice(0, 5).map((inc) => (
                        <div
                          key={inc.event_id}
                          style={{
                            background: 'rgba(7, 16, 30, 0.8)',
                            border: '1px solid rgba(56, 182, 255, 0.15)',
                            borderRadius: 8,
                            padding: 12,
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 6,
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontSize: 11, fontWeight: 800, color: '#fff' }}>{inc.event_type}</span>
                            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                              {sevBadge(inc.severity)}
                              {statusBadge(inc.status)}
                            </div>
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>{inc.description}</div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
                            <span style={{ fontSize: 9, color: 'var(--text-dim)', fontFamily: "'JetBrains Mono', monospace" }}>
                              {inc.camera_id} · {inc.timestamp}
                            </span>
                            <button
                              onClick={() => {
                                setTab('incidents');
                                setSelectedIncident(inc);
                              }}
                              style={{
                                background: 'rgba(56, 182, 255, 0.15)',
                                border: '1px solid rgba(56, 182, 255, 0.3)',
                                color: 'var(--accent-cyan)',
                                borderRadius: 4,
                                padding: '3px 8px',
                                fontSize: 9,
                                fontWeight: 700,
                                cursor: 'pointer',
                              }}
                            >
                              Open Dossier →
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ══════════ 2. INCIDENT MANAGEMENT CENTER ══════════ */}
          {tab === 'incidents' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Filter Controls */}
              <div className="panel panel-glow" style={{ padding: '12px 18px', display: 'flex', gap: 14, alignItems: 'center' }}>
                <span style={{ fontSize: 11, fontWeight: 800, color: '#ffb444', letterSpacing: '0.1em' }}>FILTER INCIDENTS:</span>
                <select
                  value={sevFilter}
                  onChange={(e) => setSevFilter(e.target.value)}
                  style={{ background: 'rgba(10,25,47,0.8)', border: '1px solid rgba(56,182,255,0.25)', color: '#fff', borderRadius: 6, padding: '6px 10px', fontSize: 11 }}
                >
                  <option value="">All Severities</option>
                  <option value="CRITICAL">CRITICAL</option>
                  <option value="HIGH">HIGH</option>
                  <option value="MEDIUM">MEDIUM</option>
                  <option value="LOW">LOW</option>
                </select>

                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  style={{ background: 'rgba(10,25,47,0.8)', border: '1px solid rgba(56,182,255,0.25)', color: '#fff', borderRadius: 6, padding: '6px 10px', fontSize: 11 }}
                >
                  <option value="">All Statuses</option>
                  <option value="NEW">NEW</option>
                  <option value="ACKNOWLEDGED">ACKNOWLEDGED</option>
                  <option value="RESOLVED">RESOLVED</option>
                </select>

                <button
                  onClick={loadData}
                  style={{ marginLeft: 'auto', background: 'rgba(56,182,255,0.15)', border: '1px solid rgba(56,182,255,0.3)', color: '#fff', borderRadius: 6, padding: '6px 12px', fontSize: 10, fontWeight: 700, cursor: 'pointer' }}
                >
                  ↻ Refresh
                </button>
              </div>

              {/* Incidents Table */}
              <div className="panel panel-glow">
                <div className="panel-header">
                  <div className="panel-header-icon">🚨</div>
                  SECURITY INCIDENT DOSSIERS ({incidents.length})
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                  <thead>
                    <tr style={{ background: 'rgba(7, 16, 30, 0.9)', borderBottom: '1px solid rgba(56, 182, 255, 0.15)', color: 'var(--text-dim)', textAlign: 'left' }}>
                      <th style={{ padding: '10px 14px' }}>INCIDENT ID</th>
                      <th style={{ padding: '10px 14px' }}>EVENT TYPE</th>
                      <th style={{ padding: '10px 14px' }}>SEVERITY</th>
                      <th style={{ padding: '10px 14px' }}>CAMERA</th>
                      <th style={{ padding: '10px 14px' }}>TIMESTAMP</th>
                      <th style={{ padding: '10px 14px' }}>OBJECT / TRACK</th>
                      <th style={{ padding: '10px 14px' }}>STATUS</th>
                      <th style={{ padding: '10px 14px' }}>EVIDENCE</th>
                      <th style={{ padding: '10px 14px' }}>ACTIONS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {incidents.length === 0 ? (
                      <tr>
                        <td colSpan={9} style={{ padding: 30, textAlign: 'center', color: 'var(--text-dim)' }}>
                          No incidents match the active filters.
                        </td>
                      </tr>
                    ) : (
                      incidents.map((inc) => (
                        <tr
                          key={inc.event_id}
                          style={{
                            borderBottom: '1px solid rgba(56, 182, 255, 0.08)',
                            background: selectedIncident?.event_id === inc.event_id ? 'rgba(56, 182, 255, 0.12)' : 'transparent',
                          }}
                        >
                          <td style={{ padding: '10px 14px', fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, color: 'var(--accent-cyan)' }}>
                            {inc.event_id}
                          </td>
                          <td style={{ padding: '10px 14px', fontWeight: 700, color: '#fff' }}>{inc.event_type}</td>
                          <td style={{ padding: '10px 14px' }}>{sevBadge(inc.severity)}</td>
                          <td style={{ padding: '10px 14px' }}>{inc.camera_id}</td>
                          <td style={{ padding: '10px 14px', color: 'var(--text-secondary)' }}>{inc.timestamp}</td>
                          <td style={{ padding: '10px 14px' }}>
                            {inc.object_type ? `${inc.object_type.toUpperCase()} #${inc.track_id ?? '?'}` : '—'}
                          </td>
                          <td style={{ padding: '10px 14px' }}>{statusBadge(inc.status)}</td>
                          <td style={{ padding: '10px 14px' }}>
                            {inc.evidence_path ? (
                              <span style={{ color: '#00ff88', fontWeight: 700 }}>📷 Available</span>
                            ) : (
                              <span style={{ color: 'var(--text-dim)' }}>None</span>
                            )}
                          </td>
                          <td style={{ padding: '10px 14px', display: 'flex', gap: 6 }}>
                            <button
                              onClick={() => setSelectedIncident(inc)}
                              style={{ background: 'rgba(56, 182, 255, 0.15)', border: '1px solid rgba(56, 182, 255, 0.3)', color: '#fff', borderRadius: 4, padding: '4px 8px', fontSize: 10, fontWeight: 700, cursor: 'pointer' }}
                            >
                              Dossier
                            </button>
                            {inc.status === 'NEW' && (
                              <button
                                onClick={() => handleAcknowledge(inc.event_id)}
                                style={{ background: 'rgba(255, 180, 68, 0.15)', border: '1px solid rgba(255, 180, 68, 0.4)', color: '#ffb444', borderRadius: 4, padding: '4px 8px', fontSize: 10, fontWeight: 700, cursor: 'pointer' }}
                              >
                                Ack
                              </button>
                            )}
                            {inc.status !== 'RESOLVED' && (
                              <button
                                onClick={() => {
                                  setSelectedIncident(inc);
                                  setShowResolveModal(true);
                                }}
                                style={{ background: 'rgba(0, 255, 136, 0.15)', border: '1px solid rgba(0, 255, 136, 0.4)', color: '#00ff88', borderRadius: 4, padding: '4px 8px', fontSize: 10, fontWeight: 700, cursor: 'pointer' }}
                              >
                                Resolve
                              </button>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Incident Dossier Detail Pane */}
              {selectedIncident && (
                <div className="panel panel-glow" style={{ padding: 20, border: '1px solid rgba(56, 182, 255, 0.35)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                    <div>
                      <div style={{ fontSize: 16, fontWeight: 900, color: '#fff' }}>
                        INCIDENT DOSSIER: {selectedIncident.event_id}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                        {selectedIncident.event_type} · Detected on {selectedIncident.camera_id} at {selectedIncident.timestamp}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      {sevBadge(selectedIncident.severity)}
                      {statusBadge(selectedIncident.status)}
                      <button
                        onClick={() => setSelectedIncident(null)}
                        style={{ background: 'transparent', border: 'none', color: 'var(--text-dim)', fontSize: 16, cursor: 'pointer', marginLeft: 8 }}
                      >
                        ✕
                      </button>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                    {/* Left: Metadata */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 12 }}>
                      <div style={{ background: 'rgba(0,0,0,0.3)', padding: 12, borderRadius: 8 }}>
                        <div style={{ color: 'var(--text-dim)', fontSize: 10, fontWeight: 700 }}>DESCRIPTION</div>
                        <div style={{ color: '#fff', marginTop: 4 }}>{selectedIncident.description}</div>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                        <div style={{ background: 'rgba(0,0,0,0.3)', padding: 10, borderRadius: 8 }}>
                          <div style={{ color: 'var(--text-dim)', fontSize: 9 }}>ZONE</div>
                          <div style={{ color: '#fff', fontWeight: 700 }}>{selectedIncident.zone_name || 'Restricted Zone'}</div>
                        </div>
                        <div style={{ background: 'rgba(0,0,0,0.3)', padding: 10, borderRadius: 8 }}>
                          <div style={{ color: 'var(--text-dim)', fontSize: 9 }}>RISK SCORE</div>
                          <div style={{ color: '#ff3b5c', fontWeight: 900 }}>{selectedIncident.risk_score} / 100</div>
                        </div>
                        <div style={{ background: 'rgba(0,0,0,0.3)', padding: 10, borderRadius: 8 }}>
                          <div style={{ color: 'var(--text-dim)', fontSize: 9 }}>OBJECT CLASS</div>
                          <div style={{ color: '#fff' }}>{selectedIncident.object_type || 'Unspecified'}</div>
                        </div>
                        <div style={{ background: 'rgba(0,0,0,0.3)', padding: 10, borderRadius: 8 }}>
                          <div style={{ color: 'var(--text-dim)', fontSize: 9 }}>TRACK ID</div>
                          <div style={{ color: 'var(--accent-cyan)', fontFamily: "'JetBrains Mono', monospace" }}>
                            #{selectedIncident.track_id ?? 'N/A'}
                          </div>
                        </div>
                      </div>

                      {/* Audit Timeline */}
                      <div style={{ background: 'rgba(0,0,0,0.3)', padding: 12, borderRadius: 8 }}>
                        <div style={{ color: 'var(--text-dim)', fontSize: 10, fontWeight: 700, marginBottom: 6 }}>AUTHORITY LIFECYCLE</div>
                        <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                          • Created: {selectedIncident.timestamp}<br />
                          {selectedIncident.acknowledged_by && (
                            <>• Acknowledged by: {selectedIncident.acknowledged_by} ({selectedIncident.acknowledged_at})<br /></>
                          )}
                          {selectedIncident.resolved_by && (
                            <>• Resolved by: {selectedIncident.resolved_by} ({selectedIncident.resolved_at}) — <em>{selectedIncident.resolution_notes}</em><br /></>
                          )}
                        </div>
                      </div>

                      {/* Actions */}
                      <div style={{ display: 'flex', gap: 10, marginTop: 6 }}>
                        {selectedIncident.status === 'NEW' && (
                          <button
                            onClick={() => handleAcknowledge(selectedIncident.event_id)}
                            className="btn btn-primary"
                            style={{ flex: 1 }}
                          >
                            ✓ ACKNOWLEDGE INCIDENT
                          </button>
                        )}
                        {selectedIncident.status !== 'RESOLVED' && (
                          <button
                            onClick={() => setShowResolveModal(true)}
                            style={{ flex: 1, background: '#059669', border: '1px solid #34d399', color: '#fff', borderRadius: 8, padding: '8px 16px', fontWeight: 800, cursor: 'pointer' }}
                          >
                            ✓ RESOLVE INCIDENT
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Right: Real Evidence Image */}
                    <div>
                      <div style={{ color: 'var(--text-dim)', fontSize: 10, fontWeight: 700, marginBottom: 6 }}>
                        VERIFIED EVIDENCE SNAPSHOT
                      </div>
                      {selectedIncident.evidence_path ? (
                        <div style={{ border: '1px solid rgba(56, 182, 255, 0.3)', borderRadius: 8, overflow: 'hidden', background: '#000' }}>
                          <img
                            src={selectedIncident.evidence_path}
                            alt="Evidence Snapshot"
                            style={{ width: '100%', height: 'auto', display: 'block' }}
                          />
                        </div>
                      ) : (
                        <div
                          style={{
                            height: 220,
                            background: 'rgba(0,0,0,0.4)',
                            border: '1px dashed rgba(56, 182, 255, 0.2)',
                            borderRadius: 8,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            flexDirection: 'column',
                            gap: 8,
                            color: 'var(--text-dim)',
                          }}
                        >
                          <div style={{ fontSize: 32 }}>📷</div>
                          <div style={{ fontSize: 11 }}>Evidence image captured at trigger</div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ══════════ 3. CAMERA NETWORK MATRIX TAB ══════════ */}
          {tab === 'cameras' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="panel panel-glow">
                <div className="panel-header">
                  <div className="panel-header-icon">🎥</div>
                  BORDER SURVEILLANCE CAMERA MATRIX ({cameras.length} CHANNELS)
                </div>
                <div style={{ padding: 16, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
                  {cameras.map((cam) => {
                    const isOnline = cam.status === 'online';
                    return (
                      <div
                        key={cam.id}
                        style={{
                          background: 'rgba(7, 16, 30, 0.9)',
                          border: `1px solid ${isOnline ? 'rgba(0,255,136,0.3)' : 'rgba(255,59,92,0.3)'}`,
                          borderRadius: 10,
                          overflow: 'hidden',
                        }}
                      >
                        <div style={{ padding: '10px 14px', background: 'rgba(0,0,0,0.4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <span style={{ fontSize: 12, fontWeight: 800, color: '#fff' }}>{cam.name}</span>
                            <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>{cam.location}</div>
                          </div>
                          <span className={isOnline ? 'badge badge-green' : 'badge badge-red'}>
                            {isOnline ? '● ONLINE' : '● OFFLINE'}
                          </span>
                        </div>

                        {/* Stream preview */}
                        <div style={{ height: 200, background: '#000', position: 'relative' }}>
                          {isOnline ? (
                            <img src={STREAM_URL} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt={cam.name} />
                          ) : (
                            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 6, color: 'var(--text-dim)' }}>
                              <div style={{ fontSize: 24 }}>📡</div>
                              <div style={{ fontSize: 10, letterSpacing: '0.1em' }}>CHANNEL STANDBY</div>
                            </div>
                          )}
                        </div>

                        <div style={{ padding: '10px 14px', fontSize: 10, color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between' }}>
                          <span>FPS: {isOnline ? (msg?.fps ?? 0) : '0'}</span>
                          <span>Source: {cam.source}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* ══════════ 4. EVIDENCE VAULT TAB ══════════ */}
          {tab === 'evidence' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="panel panel-glow">
                <div className="panel-header">
                  <div className="panel-header-icon">📁</div>
                  OFFICIAL EVIDENCE REPOSITORY ({evidenceList.length} RECORDED FILES)
                </div>
                <div style={{ padding: 16 }}>
                  {evidenceList.length === 0 ? (
                    <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12 }}>
                      No stored evidence snapshots found on disk. Snapshots are automatically saved when high-severity events occur.
                    </div>
                  ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
                      {evidenceList.map((ev) => (
                        <div
                          key={ev.filename}
                          style={{
                            background: 'rgba(7, 16, 30, 0.8)',
                            border: '1px solid rgba(56, 182, 255, 0.2)',
                            borderRadius: 8,
                            overflow: 'hidden',
                          }}
                        >
                          <img
                            src={ev.path}
                            alt={ev.filename}
                            style={{ width: '100%', height: 150, objectFit: 'cover', display: 'block' }}
                          />
                          <div style={{ padding: 10 }}>
                            <div style={{ fontSize: 10, fontWeight: 700, color: '#fff', wordBreak: 'break-all' }}>
                              {ev.filename}
                            </div>
                            <div style={{ fontSize: 9, color: 'var(--text-dim)', marginTop: 4 }}>
                              Size: {(ev.size_bytes / 1024).toFixed(1)} KB | {ev.modified.slice(0, 19)}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ══════════ 5. SYSTEM & AI HEALTH TAB ══════════ */}
          {tab === 'health' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="panel panel-glow">
                <div className="panel-header">
                  <div className="panel-header-icon">⚡</div>
                  SUBSYSTEM OPERATIONAL DIAGNOSTICS
                </div>
                <div style={{ padding: 20, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
                  {health &&
                    Object.entries(health.subsystems).map(([name, data]: any) => (
                      <div
                        key={name}
                        style={{
                          background: 'rgba(7, 16, 30, 0.8)',
                          border: '1px solid rgba(56, 182, 255, 0.2)',
                          borderRadius: 8,
                          padding: 16,
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: 12, fontWeight: 800, color: '#fff' }}>
                            {name.replace('_', ' ').toUpperCase()}
                          </span>
                          <span className={data.status === 'ACTIVE' ? 'badge badge-green' : 'badge badge-red'}>
                            ● {data.status}
                          </span>
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 8 }}>
                          {Object.entries(data)
                            .filter(([k]) => k !== 'status')
                            .map(([k, v]) => (
                              <div key={k}>
                                {k}: <strong>{String(v)}</strong>
                              </div>
                            ))}
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            </div>
          )}

          {/* ══════════ 6. SECURITY AUDIT LOG TAB ══════════ */}
          {tab === 'audit' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="panel panel-glow">
                <div className="panel-header">
                  <div className="panel-header-icon">📜</div>
                  HIGHER AUTHORITY SECURITY AUDIT TRAIL ({auditLogs.length} ENTRIES)
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                  <thead>
                    <tr style={{ background: 'rgba(7, 16, 30, 0.9)', borderBottom: '1px solid rgba(56, 182, 255, 0.15)', color: 'var(--text-dim)', textAlign: 'left' }}>
                      <th style={{ padding: '10px 14px' }}>TIMESTAMP</th>
                      <th style={{ padding: '10px 14px' }}>ACTOR</th>
                      <th style={{ padding: '10px 14px' }}>CLEARANCE</th>
                      <th style={{ padding: '10px 14px' }}>ACTION</th>
                      <th style={{ padding: '10px 14px' }}>TARGET ID</th>
                      <th style={{ padding: '10px 14px' }}>DETAILS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.length === 0 ? (
                      <tr>
                        <td colSpan={6} style={{ padding: 30, textAlign: 'center', color: 'var(--text-dim)' }}>
                          No audit log entries recorded.
                        </td>
                      </tr>
                    ) : (
                      auditLogs.map((log) => (
                        <tr key={log.id} style={{ borderBottom: '1px solid rgba(56, 182, 255, 0.08)' }}>
                          <td style={{ padding: '10px 14px', color: 'var(--text-secondary)' }}>{log.timestamp.slice(0, 19)}</td>
                          <td style={{ padding: '10px 14px', fontWeight: 700, color: '#fff' }}>{log.actor}</td>
                          <td style={{ padding: '10px 14px', color: '#ffb444' }}>{log.role}</td>
                          <td style={{ padding: '10px 14px', fontWeight: 800, color: 'var(--accent-cyan)' }}>{log.action}</td>
                          <td style={{ padding: '10px 14px', fontFamily: "'JetBrains Mono', monospace" }}>{log.target_id || '—'}</td>
                          <td style={{ padding: '10px 14px', color: 'var(--text-secondary)' }}>{log.details}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* ── Resolve Incident Modal ── */}
      {showResolveModal && selectedIncident && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            background: 'rgba(2, 6, 14, 0.85)',
            backdropFilter: 'blur(10px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 20,
          }}
        >
          <div
            className="panel panel-glow"
            style={{
              width: '100%',
              maxWidth: 440,
              padding: 24,
              borderRadius: 12,
              background: '#07101e',
            }}
          >
            <div style={{ fontSize: 15, fontWeight: 900, color: '#fff', marginBottom: 6 }}>
              RESOLVE INCIDENT {selectedIncident.event_id}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 14 }}>
              Record official resolution notes into the security audit ledger.
            </div>

            <textarea
              value={resolveNotes}
              onChange={(e) => setResolveNotes(e.target.value)}
              placeholder="e.g. Ground patrol dispatched. Perimeter verified and secured."
              rows={3}
              style={{
                width: '100%',
                background: 'rgba(10, 25, 47, 0.8)',
                border: '1px solid rgba(56, 182, 255, 0.3)',
                borderRadius: 8,
                padding: 10,
                color: '#fff',
                fontSize: 12,
                outline: 'none',
                boxSizing: 'border-box',
                marginBottom: 14,
              }}
            />

            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={() => setShowResolveModal(false)}
                style={{ flex: 1, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', borderRadius: 8, padding: '8px 14px', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={() => handleResolve(selectedIncident.event_id)}
                disabled={loading}
                style={{ flex: 2, background: '#059669', border: '1px solid #34d399', color: '#fff', borderRadius: 8, padding: '8px 14px', fontWeight: 800, cursor: 'pointer' }}
              >
                {loading ? 'Submitting...' : 'CONFIRM RESOLUTION'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
