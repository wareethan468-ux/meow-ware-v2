import { useEffect, useState } from 'react';
import { callDesktop, hasDesktopApi } from '../lib/desktopApi';

export default function RobloxAccountCard() {
  const [status, setStatus] = useState({
    attached: false,
    selected_pid: 0,
    processes: [],
    session_seconds: 0,
    applied: false,
    account: null,
  });

  useEffect(() => {
    if (!hasDesktopApi()) return undefined;
    const refresh = () => callDesktop('get_attachment_targets').then(next => next && setStatus(next));
    refresh();
    const timer = window.setInterval(refresh, 1500);
    return () => window.clearInterval(timer);
  }, []);

  const running = Boolean(status.processes?.length > 0 || status.attached);
  const account = status.account;
  const username = account?.username
    ? `@${account.username}`
    : status.attached
    ? `Client ${status.selected_pid}`
    : running
    ? 'Roblox Client'
    : 'Not connected';

  const formatTime = (secs) => {
    if (!secs || secs <= 0) return '';
    const m = Math.floor(secs / 60);
    if (m < 1) return '< 1m';
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
  };

  const timeStr = formatTime(status.session_seconds);

  const subtitle = status.attached
    ? (status.applied
        ? (timeStr ? `Applied · ${timeStr}` : 'Applied')
        : (timeStr ? `Not applied · ${timeStr}` : 'Not applied'))
    : running
    ? (timeStr ? `Detected · ${timeStr}` : 'Ready to attach')
    : account
    ? 'Offline'
    : 'Launch Roblox to connect';

  return (
    <div className={`roblox-account-card${status.attached ? ' connected' : ''}`}>
      <div className="roblox-avatar-wrap">
        {account?.avatar_url ? (
          <img
            src={account.avatar_url}
            alt={account.username || 'Roblox User'}
            className="roblox-avatar-img"
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
          />
        ) : (
          <span className="roblox-avatar">R</span>
        )}
      </div>
      <span className="roblox-account-copy">
        <div className="roblox-account-top">
          <small>ROBLOX ACCOUNT</small>
          <span className={`roblox-status-dot ${status.attached ? 'online' : running ? 'idle' : 'offline'}`} />
        </div>
        <strong title={account?.display_name ? `${account.display_name} (${username})` : username}>
          {account?.display_name && account.display_name !== account.username ? account.display_name : username}
        </strong>
        {account?.display_name && account.display_name !== account.username && (
          <small style={{ color: 'var(--text-3)', fontSize: '9px', marginTop: '-2px' }}>{username}</small>
        )}
        <em>{subtitle}</em>
      </span>
    </div>
  );
}
