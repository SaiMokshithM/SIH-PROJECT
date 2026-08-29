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
    CRITICAL: { bg: 'rgba(239, 68, 68, 0.12)', color: '#F87171', border: 'rgba(239, 68, 68, 0.35)' },
    HIGH: { bg: 'rgba(249, 115, 22, 0.12)', color: '#FB923C', border: 'rgba(249, 115, 22, 0.35)' },
    MEDIUM: { bg: 'rgba(245, 158, 11, 0.12)', color: '#FBBF24', border: 'rgba(245, 158, 11, 0.35)' },
    LOW: { bg: 'rgba(16, 185, 129, 0.12)', color: '#34D399', border: 'rgba(16, 185, 129, 0.35)' },
    INFO: { bg: 'rgba(59, 130, 246, 0.12)', color: '#60A5FA', border: 'rgba(59, 130, 246, 0.35)' },
  };
  const s = map[sev.toUpperCase()] || map.INFO;
  return (
    <span
      style={{
        background: s.bg,
        color: s.color,
        border: `1px solid ${s.border}`,
        borderRadius: 4,
        padding: '2px 6px',
        fontSize: 9,
        fontWeight: 800,
        letterSpacing: '0.04em',
      }}
    >
      {sev.toUpperCase()}
    </span>
  );
};

const statusBadge = (st: string = 'NEW') => {
  const map: Record<string, { bg: string; color: string; border: string }> = {
    NEW: { bg: '#7F1D1D', color: '#FECACA', border: '#EF4444' },
    ACKNOWLEDGED: { bg: '#78350F', color: '#FDE68A', border: '#F59E0B' },
    INVESTIGATING: { bg: '#1E3A8A', color: '#BFDBFE', border: '#3B82F6' },
    RESOLVED: { bg: '#064E3B', color: '#A7F3D0', border: '#10B981' },
  };
  const s = map[st.toUpperCase()] || map.NEW;
  return (
    <span
      style={{
        background: s.bg,
        color: s.color,
        border: `1px solid ${s.border}`,
        borderRadius: 4,
        padding: '2px 6px',
        fontSize: 9,
        fontWeight: 800,
        letterSpacing: '0.04em',
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
      {/* ── Defense Authority Header ── */}
      <header
        style={{
          background: 'var(--bg-surface)',
          borderBottom: '1px solid var(--border)',
          padding: '0 20px',
          height: 56,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'sticky',
          top: 0,
          zIndex: 300,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            style={{
              width: 36,
              height: 36,
              background: 'rgba(217, 119, 6, 0.12)',
              border: '1px solid rgba(217, 119, 6, 0.35)',
              borderRadius: 6,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 18,
            }}
          >
            🏛
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.06em', color: '#F8FAFC' }}>
                AGENCY COMMAND PORTAL
              </span>
              <span
                style={{
                  background: 'rgba(217, 119, 6, 0.12)',
                  border: '1px solid rgba(217, 119, 6, 0.35)',
                  color: '#FBBF24',
                  fontSize: 8,
                  fontWeight: 800,
                  padding: '2px 6px',
                  borderRadius: 4,
                  letterSpacing: '0.06em',
                }}
              >
                HIGHER CLEARANCE
              </span>
            </div>
            <div style={{ fontSize: 9, letterSpacing: '0.06em', color: 'var(--text-muted)', fontWeight: 600 }}>
              BORDER SECURITY HEADQUARTERS · STRATEGIC THREAT REPOSITORY · SIH 2026
            </div>
          </div>
        </div>

        {/* User Identity & Clearance */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div
            style={{
              background: wsStatus === 'connected' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
              border: `1px solid ${wsStatus === 'connected' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
              color: wsStatus === 'connected' ? '#10B981' : '#EF4444',
              fontSize: 9,
              fontWeight: 800,
              padding: '3px 8px',
              borderRadius: 4,
              letterSpacing: '0.06em',
              display: 'flex',
              alignItems: 'center',
              gap: 5,
            }}
          >
            <div className={wsStatus === 'connected' ? 'dot-live' : 'dot-offline'} style={{ width: 5, height: 5 }} />
            LINK {wsStatus.toUpperCase()}
          </div>

          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: '#F8FAFC', letterSpacing: '0.04em' }}>
              {user.name}
            </div>
            <div style={{ fontSize: 9, color: '#FBBF24', letterSpacing: '0.04em', fontWeight: 600 }}>
              {user.role} · {user.badge}
            </div>
          </div>

          <button
            onClick={onExit}
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid var(--border-light)',
              color: 'var(--text-secondary)',
              borderRadius: 6,
              padding: '6px 12px',
              fontSize: 10,
              fontWeight: 800,
              letterSpacing: '0.06em',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            ← LOCK / OPERATOR VIEW
          </button>
        </div>
      </header>

      {/* ── Real-Time Critical Alert Banner ── */}
      {latestCritEvent && (
        <div
          style={{
            background: '#7F1D1D',
            borderBottom: '2px solid #EF4444',
            padding: '8px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            zIndex: 250,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ fontSize: 18 }}>🚨</div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 800, color: '#FEF2F2', letterSpacing: '0.04em' }}>
                PRIORITY DEFENSE EVENT: {latestCritEvent.event_type}
              </div>
              <div style={{ fontSize: 9, color: '#FECACA' }}>
                Camera: <strong>{latestCritEvent.camera_id}</strong> | Zone: {latestCritEvent.zone_name || 'Border Perimeter'} | Trigger Time: {latestCritEvent.timestamp}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => handleAcknowledge(latestCritEvent.event_id)}
              style={{
                background: '#DC2626',
                border: '1px solid #F87171',
                color: '#FFFFFF',
                borderRadius: 4,
                padding: '5px 12px',
                fontSize: 10,
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
                background: 'rgba(0,0,0,0.4)',
                border: '1px solid #FECACA',
                color: '#FFFFFF',
                borderRadius: 4,
                padding: '5px 12px',
                fontSize: 10,
                fontWeight: 800,
                cursor: 'pointer',
              }}
            >
              INSPECT DOSSIER →
            </button>
          </div>
        </div>
      )}

      {/* Action Notification */}
      {actionMsg && (
        <div style={{ background: '#064E3B', color: '#A7F3D0', padding: '6px 20px', fontSize: 10, fontWeight: 700, textAlign: 'center' }}>
          ✓ {actionMsg}
        </div>
      )}

      {/* ── Main Authority Body with Navigation ── */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Tactical Navigation Sidebar */}
        <nav
          style={{
            width: 200,
            background: 'var(--bg-surface)',
            borderRight: '1px solid var(--border)',
            display: 'flex',
            flexDirection: 'column',
            padding: '12px 8px',
            gap: 4,
            flexShrink: 0,
          }}
        >
          <div style={{ fontSize: 8, fontWeight: 800, color: 'var(--text-dim)', letterSpacing: '0.1em', padding: '4px 8px' }}>
            COMMAND DIRECTORY
          </div>
          {[
            { id: 'overview', icon: '📊', label: 'Executive Posture' },
            { id: 'incidents', icon: '🚨', label: 'Incident Center', count: activeIncidentsCount },
            { id: 'cameras', icon: '🎥', label: 'Camera Network', count: activeCamerasCount },
            { id: 'evidence', icon: '📁', label: 'Evidence Vault', count: evidenceList.length },
            { id: 'health', icon: '⚡', label: 'Subsystem Health' },
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
                  gap: 8,
                  padding: '8px 10px',
                  borderRadius: 6,
                  border: active ? '1px solid var(--border-light)' : '1px solid transparent',
                  background: active ? 'var(--bg-hover)' : 'transparent',
                  color: active ? '#F8FAFC' : 'var(--text-muted)',
                  fontSize: 11,
                  fontWeight: active ? 800 : 600,
                  letterSpacing: '0.02em',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.15s',
                }}
              >
                <span style={{ fontSize: 14 }}>{item.icon}</span>
                <span style={{ flex: 1 }}>{item.label}</span>
                {item.count !== undefined && item.count > 0 && (
                  <span
                    style={{
                      background: active ? '#2563EB' : 'rgba(255,255,255,0.08)',
                      color: '#FFFFFF',
                      fontSize: 8,
                      fontWeight: 800,
                      borderRadius: 4,
                      padding: '1px 5px',
                    }}
                  >
                    {item.count}
                  </span>
                )}
              </button>
            );
          })}

          <div style={{ marginTop: 'auto', padding: '10px', background: 'var(--bg-panel)', borderRadius: 6, border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 8, color: 'var(--text-dim)', letterSpacing: '0.08em', fontWeight: 700 }}>COMMAND CLEARANCE</div>
            <div style={{ fontSize: 10, fontWeight: 800, color: '#FBBF24', marginTop: 2 }}>{user.department}</div>
            <div style={{ fontSize: 8, color: 'var(--text-muted)', marginTop: 2 }}>BADGE: {user.badge}</div>
          </div>
        </nav>

        {/* Content Area */}
        <main style={{ flex: 1, overflowY: 'auto', background: 'var(--bg-base)', padding: '16px 20px' }}>
          {/* ══════════ 1. OVERVIEW & POSTURE TAB ══════════ */}
          {tab === 'overview' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Telemetry Stat Row */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10 }}>
                <div className="stat-card">
                  <div style={{ fontSize: 8, color: 'var(--text-dim)', letterSpacing: '0.08em', fontWeight: 800 }}>ACTIVE CHANNELS</div>
                  <div style={{ fontSize: 20, fontWeight: 900, color: '#10B981', marginTop: 3, fontFamily: "'JetBrains Mono', monospace" }}>
                    {activeCamerasCount} / {cameras.length}
                  </div>
                  <div style={{ fontSize: 8, color: 'var(--text-muted)', marginTop: 2 }}>Surveillance Matrix</div>
                </div>

                <div className="stat-card">
                  <div style={{ fontSize: 8, color: 'var(--text-dim)', letterSpacing: '0.08em', fontWeight: 800 }}>ACTIVE INCIDENTS</div>
                  <div style={{ fontSize: 20, fontWeight: 900, color: activeIncidentsCount > 0 ? '#EF4444' : '#10B981', marginTop: 3, fontFamily: "'JetBrains Mono', monospace" }}>
                    {activeIncidentsCount}
                  </div>
                  <div style={{ fontSize: 8, color: 'var(--text-muted)', marginTop: 2 }}>{criticalCount} Critical Priority</div>
                </div>

                <div className="stat-card">
                  <div style={{ fontSize: 8, color: 'var(--text-dim)', letterSpacing: '0.08em', fontWeight: 800 }}>TRACKED SUBJECTS</div>
                  <div style={{ fontSize: 20, fontWeight: 900, color: '#60A5FA', marginTop: 3, fontFamily: "'JetBrains Mono', monospace" }}>
                    {msg?.counts?.tracked ?? 0}
                  </div>
                  <div style={{ fontSize: 8, color: 'var(--text-muted)', marginTop: 2 }}>Kalman Filters Active</div>
                </div>

                <div className="stat-card">
                  <div style={{ fontSize: 8, color: 'var(--text-dim)', letterSpacing: '0.08em', fontWeight: 800 }}>PERSONNEL IN SCENE</div>
                  <div style={{ fontSize: 20, fontWeight: 900, color: '#93C5FD', marginTop: 3, fontFamily: "'JetBrains Mono', monospace" }}>
                    {msg?.counts?.person ?? 0}
                  </div>
                  <div style={{ fontSize: 8, color: 'var(--text-muted)', marginTop: 2 }}>Body & Face Fusion</div>
                </div>

                <div className="stat-card">
                  <div style={{ fontSize: 8, color: 'var(--text-dim)', letterSpacing: '0.08em', fontWeight: 800 }}>FIREARMS DETECTED</div>
                  <div style={{ fontSize: 20, fontWeight: 900, color: (msg?.counts?.weapon ?? 0) > 0 ? '#EF4444' : '#64748B', marginTop: 3, fontFamily: "'JetBrains Mono', monospace" }}>
                    {msg?.counts?.weapon ?? 0}
                  </div>
                  <div style={{ fontSize: 8, color: 'var(--text-muted)', marginTop: 2 }}>Firearm AI Model</div>
                </div>

                <div className="stat-card">
                  <div style={{ fontSize: 8, color: 'var(--text-dim)', letterSpacing: '0.08em', fontWeight: 800 }}>OPERATIONAL THREAT</div>
                  <div style={{ fontSize: 20, fontWeight: 900, color: msg?.risk_score && msg.risk_score >= 80 ? '#EF4444' : '#F59E0B', marginTop: 3, fontFamily: "'JetBrains Mono', monospace" }}>
                    {msg?.risk_score ?? 0} / 100
                  </div>
                  <div style={{ fontSize: 8, color: 'var(--text-muted)', marginTop: 2 }}>Level: {msg?.risk_level ?? 'INFO'}</div>
                </div>
              </div>

              {/* 2-Column Command View */}
              <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 14 }}>
                {/* Live Surveillance Preview */}
                <div className="panel panel-glow">
                  <div className="panel-header">
                    <div className="panel-header-icon">🎥</div>
                    LIVE AGENCY SURVEILLANCE FEED · CHANNEL 01
                    <span className="badge badge-green" style={{ marginLeft: 'auto' }}>● FEED ACTIVE</span>
                  </div>
                  <div style={{ padding: 10 }}>
                    <div style={{ position: 'relative', background: '#000', borderRadius: 6, overflow: 'hidden', minHeight: 320 }}>
                      <img src={STREAM_URL} style={{ width: '100%', display: 'block', minHeight: 320, objectFit: 'contain' }} alt="Live Camera" />
                      <div className="scanline-overlay" />
                    </div>
                  </div>
                </div>

                {/* Critical Security Incidents List */}
                <div className="panel panel-glow" style={{ display: 'flex', flexDirection: 'column' }}>
                  <div className="panel-header">
                    <div className="panel-header-icon">🚨</div>
                    RECENT SECURITY INCIDENTS
                    <span style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--text-muted)', fontWeight: 700 }}>{incidents.length} RECORDED</span>
                  </div>
                  <div style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 8, flex: 1, overflowY: 'auto', maxHeight: 360 }}>
                    {incidents.length === 0 ? (
                      <div style={{ padding: 28, textAlign: 'center', color: 'var(--text-dim)', fontSize: 11 }}>
                        No active security incidents recorded in this session.
                      </div>
                    ) : (
                      incidents.slice(0, 5).map((inc) => (
                        <div
                          key={inc.event_id}
                          style={{
                            background: 'var(--bg-card)',
                            border: '1px solid var(--border)',
                            borderRadius: 6,
                            padding: 10,
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 5,
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontSize: 11, fontWeight: 800, color: '#F8FAFC' }}>{inc.event_type}</span>
                            <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                              {sevBadge(inc.severity)}
                              {statusBadge(inc.status)}
                            </div>
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>{inc.description}</div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 3 }}>
                            <span style={{ fontSize: 8, color: 'var(--text-dim)', fontFamily: "'JetBrains Mono', monospace" }}>
                              {inc.camera_id} · {inc.timestamp.slice(11, 19)}
                            </span>
                            <button
                              onClick={() => {
                                setTab('incidents');
                                setSelectedIncident(inc);
                              }}
                              style={{
                                background: 'rgba(59, 130, 246, 0.15)',
                                border: '1px solid rgba(59, 130, 246, 0.35)',
                                color: '#93C5FD',
                                borderRadius: 4,
                                padding: '2px 8px',
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Filter Controls */}
              <div className="panel panel-glow" style={{ padding: '10px 14px', display: 'flex', gap: 10, alignItems: 'center' }}>
                <span style={{ fontSize: 10, fontWeight: 800, color: '#FBBF24', letterSpacing: '0.06em' }}>FILTER INCIDENTS:</span>
                <select
                  value={sevFilter}
                  onChange={(e) => setSevFilter(e.target.value)}
                  style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-light)', color: '#F8FAFC', borderRadius: 4, padding: '5px 8px', fontSize: 10 }}
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
                  style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-light)', color: '#F8FAFC', borderRadius: 4, padding: '5px 8px', fontSize: 10 }}
                >
                  <option value="">All Statuses</option>
                  <option value="NEW">NEW</option>
                  <option value="ACKNOWLEDGED">ACKNOWLEDGED</option>
                  <option value="RESOLVED">RESOLVED</option>
                </select>

                <button
                  onClick={loadData}
                  style={{ marginLeft: 'auto', background: 'rgba(255, 255, 255, 0.05)', border: '1px solid var(--border-light)', color: '#FFFFFF', borderRadius: 4, padding: '5px 10px', fontSize: 10, fontWeight: 700, cursor: 'pointer' }}
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
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
                  <thead>
                    <tr>
                      <th>INCIDENT ID</th>
                      <th>EVENT TYPE</th>
                      <th>SEVERITY</th>
                      <th>CHANNEL</th>
                      <th>TIMESTAMP</th>
                      <th>TARGET</th>
                      <th>STATUS</th>
                      <th>EVIDENCE</th>
                      <th>ACTIONS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {incidents.length === 0 ? (
                      <tr>
                        <td colSpan={9} style={{ padding: 28, textAlign: 'center', color: 'var(--text-dim)' }}>
                          No incidents match the active filters.
                        </td>
                      </tr>
                    ) : (
                      incidents.map((inc) => (
                        <tr
                          key={inc.event_id}
                          style={{
                            background: selectedIncident?.event_id === inc.event_id ? 'rgba(59, 130, 246, 0.1)' : 'transparent',
                          }}
                        >
                          <td style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, color: '#3B82F6' }}>
                            {inc.event_id}
                          </td>
                          <td style={{ fontWeight: 700, color: '#F8FAFC' }}>{inc.event_type}</td>
                          <td>{sevBadge(inc.severity)}</td>
                          <td>{inc.camera_id}</td>
                          <td style={{ color: 'var(--text-secondary)' }}>{inc.timestamp.slice(11, 19)}</td>
                          <td>
                            {inc.object_type ? `${inc.object_type.toUpperCase()} #${inc.track_id ?? '?'}` : '—'}
                          </td>
                          <td>{statusBadge(inc.status)}</td>
                          <td>
                            {inc.evidence_path ? (
                              <span style={{ color: '#10B981', fontWeight: 700 }}>📷 Stored</span>
                            ) : (
                              <span style={{ color: 'var(--text-dim)' }}>None</span>
                            )}
                          </td>
                          <td style={{ display: 'flex', gap: 5 }}>
                            <button
                              onClick={() => setSelectedIncident(inc)}
                              style={{ background: 'rgba(59, 130, 246, 0.15)', border: '1px solid rgba(59, 130, 246, 0.35)', color: '#93C5FD', borderRadius: 4, padding: '3px 6px', fontSize: 9, fontWeight: 700, cursor: 'pointer' }}
                            >
                              Dossier
                            </button>
                            {inc.status === 'NEW' && (
                              <button
                                onClick={() => handleAcknowledge(inc.event_id)}
                                style={{ background: 'rgba(245, 158, 11, 0.15)', border: '1px solid rgba(245, 158, 11, 0.35)', color: '#FBBF24', borderRadius: 4, padding: '3px 6px', fontSize: 9, fontWeight: 700, cursor: 'pointer' }}
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
                                style={{ background: 'rgba(16, 185, 129, 0.15)', border: '1px solid rgba(16, 185, 129, 0.35)', color: '#34D399', borderRadius: 4, padding: '3px 6px', fontSize: 9, fontWeight: 700, cursor: 'pointer' }}
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
                <div className="panel panel-glow" style={{ padding: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 900, color: '#F8FAFC' }}>
                        INCIDENT DOSSIER: {selectedIncident.event_id}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                        {selectedIncident.event_type} · Channel: {selectedIncident.camera_id} at {selectedIncident.timestamp}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      {sevBadge(selectedIncident.severity)}
                      {statusBadge(selectedIncident.status)}
                      <button
                        onClick={() => setSelectedIncident(null)}
                        style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', fontSize: 14, cursor: 'pointer', marginLeft: 6 }}
                      >
                        ✕
                      </button>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                    {/* Left: Metadata */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 11 }}>
                      <div style={{ background: 'var(--bg-surface)', padding: 10, borderRadius: 6, border: '1px solid var(--border)' }}>
                        <div style={{ color: 'var(--text-dim)', fontSize: 9, fontWeight: 700 }}>TACTICAL DESCRIPTION</div>
                        <div style={{ color: '#F8FAFC', marginTop: 3 }}>{selectedIncident.description}</div>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                        <div style={{ background: 'var(--bg-surface)', padding: 8, borderRadius: 6, border: '1px solid var(--border)' }}>
                          <div style={{ color: 'var(--text-dim)', fontSize: 8 }}>PERIMETER SECTOR</div>
                          <div style={{ color: '#F8FAFC', fontWeight: 700 }}>{selectedIncident.zone_name || 'High Risk Sector'}</div>
                        </div>
                        <div style={{ background: 'var(--bg-surface)', padding: 8, borderRadius: 6, border: '1px solid var(--border)' }}>
                          <div style={{ color: 'var(--text-dim)', fontSize: 8 }}>THREAT PRIORITY</div>
                          <div style={{ color: '#EF4444', fontWeight: 900 }}>{selectedIncident.risk_score} / 100</div>
                        </div>
                        <div style={{ background: 'var(--bg-surface)', padding: 8, borderRadius: 6, border: '1px solid var(--border)' }}>
                          <div style={{ color: 'var(--text-dim)', fontSize: 8 }}>TARGET CLASS</div>
                          <div style={{ color: '#F8FAFC' }}>{selectedIncident.object_type || 'Unspecified'}</div>
                        </div>
                        <div style={{ background: 'var(--bg-surface)', padding: 8, borderRadius: 6, border: '1px solid var(--border)' }}>
                          <div style={{ color: 'var(--text-dim)', fontSize: 8 }}>TRACK ID</div>
                          <div style={{ color: '#3B82F6', fontFamily: "'JetBrains Mono', monospace" }}>
                            #{selectedIncident.track_id ?? 'N/A'}
                          </div>
                        </div>
                      </div>

                      {/* Audit Timeline */}
                      <div style={{ background: 'var(--bg-surface)', padding: 10, borderRadius: 6, border: '1px solid var(--border)' }}>
                        <div style={{ color: 'var(--text-dim)', fontSize: 9, fontWeight: 700, marginBottom: 4 }}>AUTHORITY AUDIT TRAIL</div>
                        <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                          • Recorded at: {selectedIncident.timestamp}<br />
                          {selectedIncident.acknowledged_by && (
                            <>• Acknowledged by: {selectedIncident.acknowledged_by} ({selectedIncident.acknowledged_at?.slice(11, 19)})<br /></>
                          )}
                          {selectedIncident.resolved_by && (
                            <>• Resolved by: {selectedIncident.resolved_by} ({selectedIncident.resolved_at?.slice(11, 19)}) — <em>{selectedIncident.resolution_notes}</em><br /></>
                          )}
                        </div>
                      </div>

                      {/* Actions */}
                      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
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
                            className="btn btn-green"
                            style={{ flex: 1 }}
                          >
                            ✓ RESOLVE INCIDENT
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Right: Real Evidence Image */}
                    <div>
                      <div style={{ color: 'var(--text-dim)', fontSize: 9, fontWeight: 700, marginBottom: 5 }}>
                        STORED EVIDENCE SNAPSHOT
                      </div>
                      {selectedIncident.evidence_path ? (
                        <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden', background: '#000' }}>
                          <img
                            src={selectedIncident.evidence_path}
                            alt="Evidence Snapshot"
                            style={{ width: '100%', height: 'auto', display: 'block' }}
                          />
                        </div>
                      ) : (
                        <div
                          style={{
                            height: 200,
                            background: 'var(--bg-surface)',
                            border: '1px dashed var(--border-light)',
                            borderRadius: 6,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            flexDirection: 'column',
                            gap: 6,
                            color: 'var(--text-dim)',
                          }}
                        >
                          <div style={{ fontSize: 24 }}>📷</div>
                          <div style={{ fontSize: 10 }}>Evidence snapshot stored at trigger</div>
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div className="panel panel-glow">
                <div className="panel-header">
                  <div className="panel-header-icon">🎥</div>
                  PERIMETER SURVEILLANCE CHANNELS ({cameras.length} ACTIVE)
                </div>
                <div style={{ padding: 14, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14 }}>
                  {cameras.map((cam) => {
                    const isOnline = cam.status === 'online';
                    return (
                      <div
                        key={cam.id}
                        style={{
                          background: 'var(--bg-card)',
                          border: `1px solid ${isOnline ? 'rgba(16,185,129,0.3)' : 'var(--border)'}`,
                          borderRadius: 8,
                          overflow: 'hidden',
                        }}
                      >
                        <div style={{ padding: '8px 12px', background: 'var(--bg-surface)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <span style={{ fontSize: 11, fontWeight: 800, color: '#F8FAFC' }}>{cam.name}</span>
                            <div style={{ fontSize: 8, color: 'var(--text-muted)' }}>{cam.location}</div>
                          </div>
                          <span className={isOnline ? 'badge badge-green' : 'badge badge-gray'}>
                            {isOnline ? '● ONLINE' : '● STANDBY'}
                          </span>
                        </div>

                        {/* Stream preview */}
                        <div style={{ height: 180, background: '#000', position: 'relative' }}>
                          {isOnline ? (
                            <img src={STREAM_URL} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt={cam.name} />
                          ) : (
                            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 6, color: 'var(--text-dim)' }}>
                              <div style={{ fontSize: 20 }}>📡</div>
                              <div style={{ fontSize: 9, letterSpacing: '0.08em' }}>CHANNEL STANDBY</div>
                            </div>
                          )}
                        </div>

                        <div style={{ padding: '8px 12px', fontSize: 9, color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between' }}>
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div className="panel panel-glow">
                <div className="panel-header">
                  <div className="panel-header-icon">📁</div>
                  OFFICIAL EVIDENCE ARCHIVE ({evidenceList.length} RECORDED FILES)
                </div>
                <div style={{ padding: 14 }}>
                  {evidenceList.length === 0 ? (
                    <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-dim)', fontSize: 11 }}>
                      No stored evidence snapshots found on disk. Snapshots are automatically saved when high-severity events occur.
                    </div>
                  ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
                      {evidenceList.map((ev) => (
                        <div
                          key={ev.filename}
                          style={{
                            background: 'var(--bg-card)',
                            border: '1px solid var(--border)',
                            borderRadius: 6,
                            overflow: 'hidden',
                          }}
                        >
                          <img
                            src={ev.path}
                            alt={ev.filename}
                            style={{ width: '100%', height: 140, objectFit: 'cover', display: 'block' }}
                          />
                          <div style={{ padding: 8 }}>
                            <div style={{ fontSize: 9, fontWeight: 700, color: '#F8FAFC', wordBreak: 'break-all' }}>
                              {ev.filename}
                            </div>
                            <div style={{ fontSize: 8, color: 'var(--text-dim)', marginTop: 3 }}>
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div className="panel panel-glow">
                <div className="panel-header">
                  <div className="panel-header-icon">⚡</div>
                  SUBSYSTEM OPERATIONAL STATUS
                </div>
                <div style={{ padding: 16, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
                  {health &&
                    Object.entries(health.subsystems).map(([name, data]: any) => (
                      <div
                        key={name}
                        style={{
                          background: 'var(--bg-card)',
                          border: '1px solid var(--border)',
                          borderRadius: 6,
                          padding: 14,
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: 11, fontWeight: 800, color: '#F8FAFC' }}>
                            {name.replace('_', ' ').toUpperCase()}
                          </span>
                          <span className={data.status === 'ACTIVE' ? 'badge badge-green' : 'badge badge-gray'}>
                            ● {data.status}
                          </span>
                        </div>
                        <div style={{ fontSize: 9, color: 'var(--text-secondary)', marginTop: 6 }}>
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div className="panel panel-glow">
                <div className="panel-header">
                  <div className="panel-header-icon">📜</div>
                  HIGHER AUTHORITY SECURITY AUDIT TRAIL ({auditLogs.length} ENTRIES)
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
                  <thead>
                    <tr>
                      <th>TIMESTAMP</th>
                      <th>ACTOR</th>
                      <th>CLEARANCE</th>
                      <th>ACTION</th>
                      <th>TARGET ID</th>
                      <th>DETAILS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.length === 0 ? (
                      <tr>
                        <td colSpan={6} style={{ padding: 28, textAlign: 'center', color: 'var(--text-dim)' }}>
                          No audit log entries recorded.
                        </td>
                      </tr>
                    ) : (
                      auditLogs.map((log) => (
                        <tr key={log.id}>
                          <td style={{ color: 'var(--text-secondary)', fontFamily: "'JetBrains Mono', monospace" }}>{log.timestamp.slice(0, 19)}</td>
                          <td style={{ fontWeight: 700, color: '#F8FAFC' }}>{log.actor}</td>
                          <td style={{ color: '#FBBF24' }}>{log.role}</td>
                          <td style={{ fontWeight: 800, color: '#3B82F6' }}>{log.action}</td>
                          <td style={{ fontFamily: "'JetBrains Mono', monospace" }}>{log.target_id || '—'}</td>
                          <td style={{ color: 'var(--text-secondary)' }}>{log.details}</td>
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
            background: 'rgba(8, 12, 20, 0.85)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 20,
          }}
        >
          <div
            className="panel"
            style={{
              width: '100%',
              maxWidth: 420,
              padding: 20,
              borderRadius: 8,
              background: 'var(--bg-panel)',
              border: '1px solid var(--border-light)',
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 900, color: '#F8FAFC', marginBottom: 4 }}>
              RESOLVE INCIDENT {selectedIncident.event_id}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 12 }}>
              Record official mitigation notes into the security audit ledger.
            </div>

            <textarea
              value={resolveNotes}
              onChange={(e) => setResolveNotes(e.target.value)}
              placeholder="e.g. Ground patrol dispatched. Sector verified and secured."
              rows={3}
              style={{
                width: '100%',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-light)',
                borderRadius: 6,
                padding: 8,
                color: '#F8FAFC',
                fontSize: 11,
                outline: 'none',
                boxSizing: 'border-box',
                marginBottom: 12,
              }}
            />

            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => setShowResolveModal(false)}
                style={{ flex: 1, background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-light)', color: '#FFFFFF', borderRadius: 6, padding: '8px 12px', fontSize: 11, cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={() => handleResolve(selectedIncident.event_id)}
                disabled={loading}
                className="btn btn-green"
                style={{ flex: 2, fontSize: 11 }}
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
