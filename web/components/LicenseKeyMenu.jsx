import { useEffect, useRef, useState } from 'react';
import { Icon } from './Icons';
import Modal from './Modal';
import { callDesktop, hasDesktopApi } from '../lib/desktopApi';

function formatRemaining(expiresAt, keyType = 'daily', licenseKey = '') {
  const isLife = String(keyType).toLowerCase() === 'lifetime' ||
                 String(licenseKey).toUpperCase().startsWith('LIFE-') ||
                 !expiresAt;
  if (isLife) {
    return { short: 'Lifetime', full: 'Permanent Lifetime Access', isLifetime: true, isExpired: false };
  }
  try {
    const exp = new Date(expiresAt).getTime();
    const now = Date.now();
    const diffMs = exp - now;

    if (diffMs <= 0) {
      return { short: 'Expired', full: 'Key has expired. Generate a new key in Discord.', isLifetime: false, isExpired: true };
    }

    const totalMinutes = Math.floor(diffMs / (1000 * 60));
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;

    if (hours > 0) {
      return {
        short: `${hours}h ${minutes}m`,
        full: `${hours} hours, ${minutes} minutes left`,
        isLifetime: false,
        isExpired: false
      };
    }
    return {
      short: `${minutes}m left`,
      full: `${minutes} minutes left`,
      isLifetime: false,
      isExpired: false
    };
  } catch {
    return { short: 'Active', full: 'Active License', isLifetime: false, isExpired: false };
  }
}

export default function LicenseKeyMenu() {
  const [authState, setAuthState] = useState(null);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showChangeModal, setShowChangeModal] = useState(false);
  const [newKeyInput, setNewKeyInput] = useState('');
  const [changeError, setChangeError] = useState('');
  const [verifying, setVerifying] = useState(false);
  const menuRef = useRef(null);

  const loadLicense = async () => {
    if (!hasDesktopApi()) return;
    try {
      const state = await callDesktop('get_auth_state');
      setAuthState(state);
    } catch {}
  };

  useEffect(() => {
    loadLicense();
    const timer = setInterval(() => {
      loadLicense();
    }, 30000); // refresh every 30s

    const handleAuth = (e) => {
      if (e.detail) setAuthState(e.detail);
      else loadLicense();
    };

    window.addEventListener('meowware:auth_change', handleAuth);
    return () => {
      clearInterval(timer);
      window.removeEventListener('meowware:auth_change', handleAuth);
    };
  }, []);

  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (!menuRef.current?.contains(e.target)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener('pointerdown', handleOutsideClick);
    }
    return () => document.removeEventListener('pointerdown', handleOutsideClick);
  }, [open]);

  const licenseKey = authState?.license_key;
  if (!licenseKey) return null;

  const keyType = authState?.key_type || 'daily';
  const expiresAt = authState?.expires_at;
  const timeInfo = formatRemaining(expiresAt, keyType, licenseKey);

  const maskedKey = licenseKey.length > 10
    ? `${licenseKey.slice(0, 5)}••••-••••-${licenseKey.slice(-4)}`
    : licenseKey;

  const handleCopy = () => {
    navigator.clipboard.writeText(licenseKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleChangeKeySubmit = async (e) => {
    e?.preventDefault();
    const clean = newKeyInput.trim().toUpperCase();
    if (!clean) return setChangeError('Please enter a key code');

    setVerifying(true);
    setChangeError('');
    try {
      const res = await callDesktop('validate_license_key', clean, authState?.discord_user);
      if (res?.ok) {
        await loadLicense();
        setShowChangeModal(false);
        setNewKeyInput('');
        setOpen(false);
      } else {
        setChangeError(res?.error || 'Invalid or expired key');
      }
    } catch (err) {
      setChangeError(String(err));
    } finally {
      setVerifying(false);
    }
  };

  return (
    <>
      <div className="license-key-menu-wrap" ref={menuRef}>
        <button
          type="button"
          className={`license-key-trigger${open ? ' active' : ''}${timeInfo.isExpired ? ' expired' : ''}`}
          onClick={() => setOpen(cur => !cur)}
          title={`License: ${timeInfo.isLifetime ? 'Lifetime' : timeInfo.full}`}
        >
          <Icon name={timeInfo.isLifetime ? 'crown' : 'key'} size={13} />
          <span className="license-hover-time">{timeInfo.short}</span>
        </button>

          <div className={`license-menu-popover${open ? ' is-visible' : ''}`} aria-hidden={!open}>
            {/* Header */}
            <div className="license-menu-header">
              <div className="license-header-title-wrap">
                <span className="license-menu-title">License Status</span>
                <span className={`license-status-badge ${timeInfo.isExpired ? 'expired' : timeInfo.isLifetime ? 'lifetime' : 'active'}`}>
                  <span className="status-dot" />
                  {timeInfo.isExpired ? 'Expired' : timeInfo.isLifetime ? 'Lifetime' : 'Active (12h)'}
                </span>
              </div>
              <div className="license-expiration-text">
                {timeInfo.isLifetime ? (
                  <span>Never expires • Permanent access</span>
                ) : timeInfo.isExpired ? (
                  <span style={{ color: '#f87171' }}>Expired • Generate a new key</span>
                ) : (
                  <span>Expires in <strong>{timeInfo.full}</strong></span>
                )}
              </div>
            </div>

            {/* Key Card */}
            <div className="license-key-card">
              <div className="license-key-masked-wrap">
                <span className="license-key-label">Key Code</span>
                <span className="license-key-code">{maskedKey}</span>
              </div>
              <button
                type="button"
                className={`btn-copy-license${copied ? ' copied' : ''}`}
                onClick={handleCopy}
                title="Copy full key code"
              >
                <Icon name={copied ? 'check' : 'copy'} size={12} />
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>

            {/* Actions list */}
            <div className="license-menu-actions">
              <button
                type="button"
                className="license-menu-item"
                onClick={() => {
                  setShowChangeModal(true);
                  setNewKeyInput('');
                  setChangeError('');
                }}
              >
                <Icon name="edit" size={13} />
                <span>Change License Key</span>
              </button>
              <button
                type="button"
                className="license-menu-item"
                onClick={() => callDesktop('open_url', 'https://discord.com')}
              >
                <Icon name="discord" size={13} />
                <span>Get Daily Key on Discord (/getkey)</span>
              </button>
            </div>
          </div>
      </div>

      {/* Change Key Modal */}
      <Modal
        open={showChangeModal}
        onClose={() => setShowChangeModal(false)}
        title="Change Vellium Tweaker License Key"
        width="460px"
        footer={<>
          <button className="btn" onClick={() => setShowChangeModal(false)}>Cancel</button>
          <button className="btn primary" disabled={verifying || !newKeyInput.trim()} onClick={handleChangeKeySubmit}>
            {verifying ? 'Verifying…' : 'Activate Key'}
          </button>
        </>}
      >
        <p className="modal-body-text" style={{ marginBottom: 12 }}>
          Enter a new 12-hour daily key from <code>/getkey</code> or a lifetime key:
        </p>
        <div className="modal-field">
          <input
            className="input"
            style={{ letterSpacing: '0.06em', fontFamily: 'monospace', textTransform: 'uppercase' }}
            placeholder="MEOW-XXXX-XXXX-XXXX"
            value={newKeyInput}
            onChange={e => {
              setNewKeyInput(e.target.value);
              setChangeError('');
            }}
            autoFocus
          />
        </div>
        {changeError && (
          <div style={{ color: '#f87171', fontSize: 11.5, marginTop: 6, fontWeight: 550 }}>
            {changeError}
          </div>
        )}
      </Modal>
    </>
  );
}
