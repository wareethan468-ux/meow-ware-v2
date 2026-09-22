import { useEffect, useRef, useState } from 'react';
import { Icon } from './Icons';

const shortVersion = value => value ? value.replace(/^version-/, '').slice(0, 8) : 'unknown';

export default function RobloxMonitorStrip({ status, onOpen }) {
  const live = Boolean(status?.running);
  const [menuOpen, setMenuOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const wrapRef = useRef(null);
  const copyTimer = useRef();

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = e => { if (!wrapRef.current?.contains(e.target)) setMenuOpen(false); };
    const onKey = e => { if (e.key === 'Escape') setMenuOpen(false); };
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('pointerdown', onDown); document.removeEventListener('keydown', onKey); };
  }, [menuOpen]);

  useEffect(() => () => window.clearTimeout(copyTimer.current), []);

  const fullVersion = status?.version || null;
  const offsetsVersion = status?.offsets_version || null;

  const copyVersion = async (e) => {
    e.stopPropagation();
    if (!fullVersion) return;
    try {
      await navigator.clipboard.writeText(fullVersion);
      setCopied(true);
      window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1400);
    } catch {}
  };

  const openMonitor = (e) => { e.stopPropagation(); setMenuOpen(false); onOpen?.(); };

  return <div
    className={`roblox-monitor-strip${live ? ' live' : ''}`}
    role="button"
    tabIndex={0}
    onClick={onOpen}
    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen?.(); } }}
    title="Open Roblox Monitor"
  >
    <span className="monitor-strip-lead"><i/><Icon name="activity" size={13}/><strong>{live ? 'Roblox live' : 'Roblox idle'}</strong></span>
    <span><small>CPU</small><b>{live ? `${status.cpu_percent.toFixed(1)}%` : '—'}</b></span>
    <span><small>Memory</small><b>{live ? status.memory_label : '—'}</b></span>
    <span><small>Process</small><b>{live ? `PID ${status.pid}` : 'Not running'}</b></span>
    <span className={status?.offsets_ok ? 'healthy' : 'warning'}><small>Offsets</small><b>{status?.offsets_ok ? 'Ready' : 'Check'}</b></span>

    <div className="monitor-version-wrap" ref={wrapRef} onClick={e => e.stopPropagation()}>
      <button
        type="button"
        className={`monitor-version${menuOpen ? ' open' : ''}`}
        onClick={e => { e.stopPropagation(); setMenuOpen(v => !v); }}
        aria-expanded={menuOpen}
        aria-haspopup="menu"
        title="Roblox version details"
      >
        <Icon name="roblox" size={11}/>
        <span className="monitor-version-hash">{shortVersion(fullVersion)}</span>
        <Icon name="chevron" size={11} className={`monitor-version-caret${menuOpen ? ' open' : ''}`}/>
      </button>

      <div className={`monitor-version-menu${menuOpen ? ' is-visible' : ''}`} role="menu" aria-hidden={!menuOpen}>
        <div className="mv-menu-head">
          <span className="mv-menu-eyebrow"><Icon name="roblox" size={12}/> Roblox version</span>
          <span className={`mv-menu-health ${status?.offsets_ok ? 'good' : 'warn'}`}>{status?.offsets_ok ? 'Matched' : 'Check'}</span>
        </div>
        <div className="mv-menu-row"><small>Client</small><code>{fullVersion || 'Not detected'}</code></div>
        <div className="mv-menu-row"><small>Active offsets</small><code>{offsetsVersion || 'Loading…'}</code></div>
        <div className="mv-menu-row"><small>Known flags</small><code>{Number(status?.offset_count || 0).toLocaleString()}</code></div>
        <div className="mv-menu-actions">
          <button type="button" className="mv-menu-item" onClick={copyVersion} disabled={!fullVersion}>
            <Icon name={copied ? 'check' : 'copy'} size={12}/> {copied ? 'Copied' : 'Copy version'}
          </button>
          <button type="button" className="mv-menu-item" onClick={openMonitor}>
            <Icon name="activity" size={12}/> Open monitor
          </button>
        </div>
      </div>
    </div>
  </div>;
}
