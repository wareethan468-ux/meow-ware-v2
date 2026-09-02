import { Icon } from './Icons';

const shortVersion = value => value ? value.replace(/^version-/, '').slice(0, 8) : 'unknown';

export default function RobloxMonitorStrip({ status, onOpen }) {
  const live = Boolean(status?.running);
  return <button className={`roblox-monitor-strip${live ? ' live' : ''}`} onClick={onOpen} title="Open Roblox Monitor">
    <span className="monitor-strip-lead"><i/><Icon name="activity" size={13}/><strong>{live ? 'Roblox live' : 'Roblox idle'}</strong></span>
    <span><small>CPU</small><b>{live ? `${status.cpu_percent.toFixed(1)}%` : '—'}</b></span>
    <span><small>Memory</small><b>{live ? status.memory_label : '—'}</b></span>
    <span><small>Process</small><b>{live ? `PID ${status.pid}` : 'Not running'}</b></span>
    <span className={status?.offsets_ok ? 'healthy' : 'warning'}><small>Offsets</small><b>{status?.offsets_ok ? 'Ready' : 'Check'}</b></span>
    <span className="monitor-version">v {shortVersion(status?.version)}</span>
    <Icon name="chevron" size={11}/>
  </button>;
}
