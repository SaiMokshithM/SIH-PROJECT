import { useState, type FormEvent } from 'react';
import { loginAuthority } from '../api';
import type { AuthorityUser } from '../types';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (user: AuthorityUser) => void;
}

export function AuthorityLoginModal({ isOpen, onClose, onSuccess }: Props) {
  const [pin, setPin] = useState('');
  const [username, setUsername] = useState('commander');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!pin.trim()) {
      setError('Please enter your 4-digit security clearance PIN.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const user = await loginAuthority(pin, username);
      localStorage.setItem('authority_token', user.token);
      localStorage.setItem('authority_user', JSON.stringify(user));
      onSuccess(user);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Invalid security clearance PIN.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'rgba(2, 6, 14, 0.85)',
        backdropFilter: 'blur(12px)',
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
          background: 'linear-gradient(180deg, #07101e 0%, #030810 100%)',
          border: '1px solid rgba(56, 182, 255, 0.35)',
          borderRadius: 14,
          padding: 28,
          boxShadow: '0 20px 60px rgba(0, 0, 0, 0.9), 0 0 40px rgba(56, 182, 255, 0.15)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 10,
              background: 'rgba(56, 182, 255, 0.15)',
              border: '1px solid rgba(56, 182, 255, 0.4)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 22,
            }}
          >
            🏛
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800, letterSpacing: '0.12em', color: '#fff' }}>
              HIGHER AUTHORITY ACCESS
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.08em' }}>
              SIH 2026 · AGENCY COMMAND PORTAL
            </div>
          </div>
        </div>

        <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: 20 }}>
          Security clearance required to access the executive command portal, incident dossiers, evidence repository, and operational audit logs.
        </p>

        {error && (
          <div className="alert-banner alert-danger" style={{ marginBottom: 16 }}>
            ⚠ {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', color: 'var(--text-dim)', display: 'block', marginBottom: 6 }}>
              CLEARANCE IDENTITY
            </label>
            <select
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={{
                width: '100%',
                background: 'rgba(10, 25, 47, 0.8)',
                border: '1px solid rgba(56, 182, 255, 0.25)',
                borderRadius: 8,
                padding: '10px 14px',
                color: '#fff',
                fontSize: 13,
                outline: 'none',
              }}
            >
              <option value="commander">Col. Rajesh Sharma (Commanding Officer)</option>
              <option value="agency_admin">Chief Security Director (Ministry HQ)</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', color: 'var(--text-dim)', display: 'block', marginBottom: 6 }}>
              SECURITY PASSCODE / PIN
            </label>
            <input
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="Enter 4-digit PIN (Default: 9926)"
              autoFocus
              style={{
                width: '100%',
                background: 'rgba(10, 25, 47, 0.8)',
                border: '1px solid rgba(56, 182, 255, 0.3)',
                borderRadius: 8,
                padding: '10px 14px',
                color: '#fff',
                fontSize: 14,
                fontFamily: "'JetBrains Mono', monospace",
                letterSpacing: '0.2em',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
            <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>
              Demo Quick-Pass PIN:{' '}
              <button
                type="button"
                onClick={() => setPin('9926')}
                style={{
                  background: 'rgba(56, 182, 255, 0.15)',
                  border: '1px solid rgba(56, 182, 255, 0.3)',
                  color: 'var(--accent-cyan)',
                  borderRadius: 4,
                  padding: '1px 6px',
                  fontSize: 10,
                  fontWeight: 700,
                  cursor: 'pointer',
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                9926 (Click to Fill)
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                flex: 1,
                background: 'rgba(255, 255, 255, 0.06)',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                color: 'var(--text-secondary)',
                borderRadius: 8,
                padding: '10px 16px',
                fontSize: 12,
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary"
              style={{
                flex: 2,
                padding: '10px 16px',
                fontSize: 12,
                fontWeight: 800,
                letterSpacing: '0.1em',
              }}
            >
              {loading ? 'Verifying...' : 'VERIFY CLEARANCE →'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
