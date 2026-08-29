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
          background: 'var(--bg-panel)',
          border: '1px solid var(--border-light)',
          borderRadius: 8,
          padding: 24,
          boxShadow: '0 20px 50px rgba(0, 0, 0, 0.85)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 6,
              background: 'rgba(217, 119, 6, 0.12)',
              border: '1px solid rgba(217, 119, 6, 0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 18,
            }}
          >
            🏛
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 800, letterSpacing: '0.06em', color: '#F8FAFC' }}>
              HIGHER AUTHORITY ACCESS
            </div>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.06em', fontWeight: 600 }}>
              DEFENSE SURVEILLANCE COMMAND PORTAL · SIH 2026
            </div>
          </div>
        </div>

        <p style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: 16 }}>
          Security clearance verification required to access executive incident dossiers, evidence repository, and operational audit ledgers.
        </p>

        {error && (
          <div className="alert-banner alert-danger" style={{ marginBottom: 14 }}>
            ⚠ {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-muted)', display: 'block', marginBottom: 5 }}>
              SELECT CLEARANCE IDENTITY
            </label>
            <select
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={{
                width: '100%',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-light)',
                borderRadius: 6,
                padding: '9px 12px',
                color: '#F8FAFC',
                fontSize: 12,
                outline: 'none',
              }}
            >
              <option value="commander">Col. Rajesh Sharma (Commanding Officer - BSF HQ)</option>
              <option value="agency_admin">Chief Security Director (Ministry Surveillance HQ)</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-muted)', display: 'block', marginBottom: 5 }}>
              ENTER CLEARANCE PIN
            </label>
            <input
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="Enter 4-digit PIN (e.g. 9926)"
              autoFocus
              style={{
                width: '100%',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-light)',
                borderRadius: 6,
                padding: '9px 12px',
                color: '#F8FAFC',
                fontSize: 13,
                fontFamily: "'JetBrains Mono', monospace",
                letterSpacing: '0.2em',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
            <div style={{ fontSize: 9, color: 'var(--text-dim)', marginTop: 4 }}>
              Demo Quick-Pass:{' '}
              <button
                type="button"
                onClick={() => setPin('9926')}
                style={{
                  background: 'rgba(59, 130, 246, 0.12)',
                  border: '1px solid rgba(59, 130, 246, 0.3)',
                  color: '#60A5FA',
                  borderRadius: 4,
                  padding: '1px 6px',
                  fontSize: 9,
                  fontWeight: 700,
                  cursor: 'pointer',
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                9926 (Click to Fill)
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                flex: 1,
                background: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid var(--border-light)',
                color: 'var(--text-secondary)',
                borderRadius: 6,
                padding: '9px 14px',
                fontSize: 11,
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
                padding: '9px 14px',
                fontSize: 11,
                fontWeight: 800,
                letterSpacing: '0.06em',
              }}
            >
              {loading ? 'Verifying...' : 'AUTHENTICATE CLEARANCE →'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
