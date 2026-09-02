import { useEffect, useState } from 'react';
import Modal from './Modal';
import Checkbox from './Checkbox';
import { Icon } from './Icons';
import { callDesktop, hasDesktopApi } from '../lib/desktopApi';

export default function DiscordAuthModal({ open, onAuthenticated }) {
  const [discordUser, setDiscordUser] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [liabilityAccepted, setLiabilityAccepted] = useState(false);
  const [manualInput, setManualInput] = useState('');
  const [showManual, setShowManual] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // Auto-detect local Discord and restore saved state on mount
  useEffect(() => {
    if (!open) return;
    const initModal = async () => {
      if (hasDesktopApi()) {
        try {
          const state = await callDesktop('get_auth_state');
          if (state) {
            if (state.discord_user) setDiscordUser(state.discord_user);
            if (state.terms_accepted) setTermsAccepted(true);
            if (state.terms_accepted) setLiabilityAccepted(true);
          }
        } catch {}
      }
      checkLocalDiscord();
    };
    initModal();
  }, [open]);

  const checkLocalDiscord = async () => {
    setConnecting(true);
    setErrorMsg('');
    try {
      const res = await callDesktop('detect_discord_user');
      if (res?.ok && res.user) {
        setDiscordUser(res.user);
      }
    } catch {
      // Best-effort
    } finally {
      setConnecting(false);
    }
  };

  const handleConnectClick = async () => {
    setConnecting(true);
    setErrorMsg('');
    const res = await callDesktop('detect_discord_user');
    if (res?.ok && res.user) {
      setDiscordUser(res.user);
    } else {
      setShowManual(true);
      setErrorMsg('Discord desktop app not detected. Enter your username/tag below or launch Discord.');
    }
    setConnecting(false);
  };

  const handleManualSubmit = (e) => {
    e?.preventDefault();
    const tag = manualInput.trim();
    if (!tag) return setErrorMsg('Please enter a Discord username or ID');
    const userObj = {
      id: 'manual_' + Date.now(),
      username: tag.replace(/^@/, ''),
      global_name: tag.replace(/^@/, ''),
      avatar_url: '',
      method: 'manual',
    };
    setDiscordUser(userObj);
    setShowManual(false);
    setErrorMsg('');
  };

  const handleContinue = async () => {
    if (!discordUser || !termsAccepted || !liabilityAccepted) return;

    const authPayload = {
      terms_accepted: true,
      liability_accepted: true,
      discord_user: discordUser,
      accepted_at: Date.now(),
    };

    await callDesktop('save_auth_state', authPayload);
    try {
      localStorage.setItem('meowware:auth_accepted', 'true');
      localStorage.setItem('meowware:discord_user', JSON.stringify(discordUser));
    } catch {}
    if (onAuthenticated) onAuthenticated(authPayload);
  };

  const canContinue = Boolean(discordUser && termsAccepted && liabilityAccepted);

  return (
    <Modal
      open={open}
      onClose={() => {}}
      title="Welcome to Vellium Tweaker"
      subtitle="Discord authentication & terms acceptance required."
      width="520px"
      footer={
        <button
          className="btn primary"
          style={{ width: '100%', height: 38, fontSize: 12.5 }}
          disabled={!canContinue}
          onClick={handleContinue}
        >
          {canContinue ? 'Continue to Key System →' : 'Complete Discord login & accept terms to continue'}
        </button>
      }
    >
      <div className="discord-auth-content">
        {/* Step 1: Discord Authentication */}
        <div className="auth-step-box">
          <div className="auth-step-head">
            <span className="auth-step-num">1</span>
            <strong>Discord Login</strong>
            {discordUser && <span className="auth-verified-badge"><Icon name="check" size={11} /> Connected</span>}
          </div>

          {discordUser ? (
            <div className="discord-user-profile-card">
              <div className="discord-avatar-wrap">
                {discordUser.avatar_url ? (
                  <img src={discordUser.avatar_url} alt={discordUser.username} className="discord-avatar-img" />
                ) : (
                  <div className="discord-avatar-fallback"><Icon name="discord" size={18} /></div>
                )}
              </div>
              <div className="discord-profile-details">
                <strong>{discordUser.global_name || discordUser.username}</strong>
                <small>@{discordUser.username}</small>
              </div>
              <button
                type="button"
                className="btn"
                style={{ height: 26, fontSize: 10, padding: '0 8px', marginLeft: 'auto' }}
                onClick={() => setDiscordUser(null)}
              >
                Change
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <button
                type="button"
                className="btn-discord-login"
                onClick={handleConnectClick}
                disabled={connecting}
              >
                <Icon name="discord" size={18} />
                <span>{connecting ? 'Checking Discord Client…' : 'Login with Discord'}</span>
              </button>

              {showManual && (
                <form onSubmit={handleManualSubmit} className="discord-manual-form">
                  <input
                    className="input"
                    placeholder="Discord username (e.g. user or user#0000)"
                    value={manualInput}
                    onChange={e => setManualInput(e.target.value)}
                    autoFocus
                  />
                  <button type="submit" className="btn" style={{ height: 32, fontSize: 11 }}>
                    Set
                  </button>
                </form>
              )}

              {errorMsg && <div className="discord-auth-hint">{errorMsg}</div>}
            </div>
          )}
        </div>

        {/* Step 2: Terms & Disclaimer */}
        <div className="auth-step-box" style={{ marginTop: 10 }}>
          <div className="auth-step-head">
            <span className="auth-step-num">2</span>
            <strong>Terms & Disclaimer</strong>
            {termsAccepted && liabilityAccepted && <span className="auth-verified-badge"><Icon name="check" size={11} /> Agreed</span>}
          </div>

          <div className="auth-disclaimer-box">
            <div className="disclaimer-title">Use at your own risk</div>
            <p>Vellium Tweaker modifies local Roblox configuration and interacts with Roblox processes.</p>
            <div className="disclaimer-title" style={{ marginTop: 6 }}>Account Liability</div>
            <p>You assume full responsibility for your account actions and any potential moderation or termination.</p>
          </div>

          <div className="auth-checkbox-stack">
            <Checkbox
              checked={termsAccepted}
              onChange={setTermsAccepted}
              label={
                <span>
                  I agree to the <strong>Terms of Service, EULA & Disclaimer</strong>
                </span>
              }
            />
            <Checkbox
              checked={liabilityAccepted}
              onChange={setLiabilityAccepted}
              label={
                <span>
                  I accept that <strong>if my account gets banned or terminated, it is solely my own fault & responsibility</strong>
                </span>
              }
            />
          </div>
        </div>
      </div>
    </Modal>
  );
}
