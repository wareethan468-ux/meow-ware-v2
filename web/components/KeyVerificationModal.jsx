import { useEffect, useState } from 'react';
import Modal from './Modal';
import { Icon } from './Icons';
import { callDesktop, hasDesktopApi } from '../lib/desktopApi';

export default function KeyVerificationModal({ open, discordUser, notice, onKeyVerified, onBackToAuth }) {
  const [keyCode, setKeyCode] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [keyInfo, setKeyInfo] = useState(null);
  const [keyError, setKeyError] = useState('');

  useEffect(() => {
    if (!open) return;
    const loadExisting = async () => {
      if (hasDesktopApi()) {
        try {
          const state = await callDesktop('get_auth_state');
          if (state?.license_key) {
            setKeyCode(state.license_key);
            if (state.key_valid) {
              setKeyInfo({ key_type: state.key_type, expires_at: state.expires_at });
            }
          }
        } catch {}
      }
    };
    loadExisting();
  }, [open]);

  const handleVerify = async (e) => {
    e?.preventDefault();
    const cleanKey = keyCode.trim().toUpperCase();
    if (!cleanKey) {
      setKeyError('Please enter a key code');
      return;
    }
    setVerifying(true);
    setKeyError('');
    try {
      const res = await callDesktop('validate_license_key', cleanKey, discordUser);
      if (res?.ok) {
        setKeyInfo(res);
        setKeyError('');
        onKeyVerified(res);
      } else {
        setKeyInfo(null);
        setKeyError(res?.error || 'Invalid or expired key. Generate a 12h key via /getkey');
      }
    } catch (err) {
      setKeyInfo(null);
      setKeyError(String(err));
    } finally {
      setVerifying(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => {}}
      title="Vellium Tweaker Key System"
      width="480px"
    >
      <div className="key-system-modal-wrap">
        {notice && (
          <div className="key-system-msg error" style={{ marginBottom: 12 }}>
            <Icon name="alert" size={14} />
            <span>{notice}</span>
          </div>
        )}
        {/* User identification badge */}
        {discordUser && (
          <div className="key-user-pill-bar">
            <div className="key-user-avatar">
              {discordUser.avatar_url ? (
                <img src={discordUser.avatar_url} alt={discordUser.username} />
              ) : (
                <Icon name="discord" size={14} />
              )}
            </div>
            <div className="key-user-text">
              <span className="key-user-name">{discordUser.global_name || discordUser.username}</span>
              <span className="key-user-tag">@{discordUser.username}</span>
            </div>
            {onBackToAuth && (
              <button
                type="button"
                className="btn-key-change-user"
                onClick={onBackToAuth}
                title="Switch Discord Account"
              >
                Switch Account
              </button>
            )}
          </div>
        )}

        <p className="modal-body-text" style={{ margin: '14px 0 10px' }}>
          Enter your 12-hour daily key from our Discord bot (<code>/getkey</code>) or your permanent lifetime key:
        </p>

        {/* Input box */}
        <div className="modal-field" style={{ marginBottom: 10 }}>
          <div className="key-input-row">
            <input
              className={`input key-input-field ${keyError ? 'has-error' : keyInfo ? 'has-success' : ''}`}
              placeholder="MEOW-XXXX-XXXX-XXXX"
              value={keyCode}
              onChange={e => {
                setKeyCode(e.target.value);
                setKeyError('');
              }}
              onKeyDown={e => e.key === 'Enter' && handleVerify(e)}
              autoFocus
            />
            <button
              type="button"
              className="btn primary key-btn-verify"
              disabled={verifying || !keyCode.trim()}
              onClick={handleVerify}
            >
              {verifying ? 'Verifying…' : keyInfo ? <><Icon name="check" size={13} /> Verified</> : 'Verify Key'}
            </button>
          </div>

          {keyError && (
            <div className="key-system-msg error">
              <Icon name="alert" size={13} />
              <span>{keyError}</span>
            </div>
          )}

          {keyInfo && (
            <div className="key-system-msg success">
              <Icon name="check" size={13} />
              <span>Active {keyInfo.key_type || 'daily'} license verified!</span>
            </div>
          )}
        </div>

        {/* Help & Links */}
        <div className="key-system-footer-box">
          <div className="key-footer-info">
            <Icon name="discord" size={15} />
            <span>Need a key? Run <strong>/getkey</strong> in our Discord server</span>
          </div>
          <button
            type="button"
            className="btn"
            style={{ height: 28, fontSize: 11, padding: '0 10px' }}
            onClick={() => callDesktop('open_url', 'https://discord.com')}
          >
            Open Discord
          </button>
        </div>

        {/* Unlock Action Button */}
        <button
          type="button"
          className="btn primary btn-unlock-full"
          disabled={verifying || !keyCode.trim()}
          onClick={handleVerify}
        >
          {verifying ? 'Activating License…' : 'Unlock Vellium Tweaker'}
        </button>
      </div>
    </Modal>
  );
}
