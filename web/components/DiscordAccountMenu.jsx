import { useEffect, useRef, useState } from 'react';
import { Icon } from './Icons';
import { callDesktop, hasDesktopApi } from '../lib/desktopApi';

export default function DiscordAccountMenu() {
  const [user, setUser] = useState(null);
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);

  const loadUser = async () => {
    if (!hasDesktopApi()) {
      try {
        const cached = localStorage.getItem('meowware:discord_user');
        if (cached) setUser(JSON.parse(cached));
      } catch {}
      return;
    }
    const state = await callDesktop('get_auth_state');
    if (state?.authenticated && state.discord_user) {
      setUser(state.discord_user);
    } else {
      try {
        const cached = localStorage.getItem('meowware:discord_user');
        if (cached) setUser(JSON.parse(cached));
      } catch {}
    }
  };

  useEffect(() => {
    loadUser();
    const handleAuth = (e) => {
      if (e.detail?.discord_user) setUser(e.detail.discord_user);
      else loadUser();
    };
    window.addEventListener('meowware:auth_change', handleAuth);
    return () => window.removeEventListener('meowware:auth_change', handleAuth);
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

  const handleLogout = async () => {
    setOpen(false);
    try {
      localStorage.removeItem('meowware:auth_accepted');
      localStorage.removeItem('meowware:discord_user');
    } catch {}
    await callDesktop('save_auth_state', {
      authenticated: false,
      terms_accepted: false,
      discord_user: null,
    });
    setUser(null);
    window.dispatchEvent(new CustomEvent('meowware:logout'));
  };

  if (!user) return null;

  return (
    <div className="discord-account-menu-wrap" ref={menuRef}>
      <button
        type="button"
        className={`discord-account-trigger${open ? ' active' : ''}`}
        onClick={() => setOpen(cur => !cur)}
        title={`Discord: @${user.username}`}
      >
        <div className="discord-mini-avatar">
          {user.avatar_url ? (
            <img src={user.avatar_url} alt={user.username} />
          ) : (
            <Icon name="discord" size={12} />
          )}
        </div>
        <span className="discord-mini-name">{user.global_name || user.username}</span>
        <Icon name="chevron" size={10} className={`discord-chevron${open ? ' open' : ''}`} />
      </button>

        <div className={`discord-menu-popover${open ? ' is-visible' : ''}`} aria-hidden={!open}>
          <div className="discord-menu-header">
            <div className="discord-menu-avatar">
              {user.avatar_url ? (
                <img src={user.avatar_url} alt={user.username} />
              ) : (
                <Icon name="discord" size={18} />
              )}
            </div>
            <div className="discord-menu-info">
              <strong>{user.global_name || user.username}</strong>
              <small>@{user.username}</small>
              <span className="discord-status-pill">
                <span className="discord-dot" /> Discord Connected
              </span>
            </div>
          </div>

          <div className="discord-menu-divider" />

          <div className="discord-menu-actions">
            <button
              type="button"
              className="discord-menu-item"
              onClick={() => {
                setOpen(false);
                callDesktop('open_url', 'https://discord.com');
              }}
            >
              <Icon name="discord" size={13} />
              <span>Discord Community</span>
            </button>
            <button
              type="button"
              className="discord-menu-item"
              onClick={() => {
                setOpen(false);
                window.dispatchEvent(new Event('vellium:show-terms'));
              }}
            >
              <Icon name="info" size={13} />
              <span>Terms of Service</span>
            </button>
            <button
              type="button"
              className="discord-menu-item danger"
              onClick={handleLogout}
            >
              <Icon name="logout" size={13} />
              <span>Log Out</span>
            </button>
          </div>
        </div>
    </div>
  );
}
