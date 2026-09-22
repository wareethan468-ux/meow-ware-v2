import { Icon } from '../components/Icons';

const formatTime = seconds => {
  const value = Math.max(0, Number(seconds) || 0);
  const h = Math.floor(value / 3600);
  const m = Math.floor((value % 3600) / 60);
  const s = value % 60;
  return h ? `${h}h ${m}m` : `${m}m ${s}s`;
};

export default function MonitorView({ monitor = {}, onNavigate }) {
  const live = Boolean(monitor.running);
  const cpu = Math.min(100, Number(monitor.cpu_percent) || 0);
  const memGb = (Number(monitor.memory_bytes) || 0) / (1024 ** 3);
  return <div className="monitor-view view">
    <header className="monitor-heading">
      <div><span className="eyebrow">ROBLOX RUNTIME</span><h1>Process monitor</h1><p>Live performance, process, and FastFlag offset health.</p></div>
      <span className={`monitor-live-pill${live ? ' online' : ''}`}><i/>{live ? 'Live session' : 'Waiting for Roblox'}</span>
    </header>
    <div className="monitor-metric-grid">
      <article><span><Icon name="cpu" size={14}/> CPU</span><strong>{live ? `${cpu.toFixed(1)}%` : '—'}</strong><div><i style={{width:`${cpu}%`}}/></div><small>Roblox processor usage</small></article>
      <article><span><Icon name="database" size={14}/> Memory</span><strong>{live ? monitor.memory_label : '—'}</strong><div><i style={{width:`${Math.min(100, memGb / 8 * 100)}%`}}/></div><small>Working set memory</small></article>
      <article><span><Icon name="activity" size={14}/> Priority</span><strong>{live ? monitor.priority : '—'}</strong><small>Operating-system process class</small></article>
      <article><span><Icon name="monitor" size={14}/> Process</span><strong>{live ? `PID ${monitor.pid}` : 'Not running'}</strong><small>{monitor.attached ? 'Attached to Vellium' : live ? 'Detected automatically' : 'Launch Roblox to begin'}</small></article>
    </div>
    <section className="monitor-detail-card">
      <div className="monitor-detail-title"><span><Icon name="layers" size={15}/> Runtime details</span><em>{monitor.offsets_ok ? 'healthy' : 'attention'}</em></div>
      <dl>
        <div><dt>Roblox version</dt><dd>{monitor.version || 'Not detected'}</dd></div>
        <div><dt>Active offsets</dt><dd>{monitor.offsets_version || 'Loading definitions'}</dd></div>
        <div><dt>Known flags</dt><dd>{Number(monitor.offset_count || 0).toLocaleString()}</dd></div>
        <div><dt>Session time</dt><dd>{live ? formatTime(monitor.session_seconds) : '—'}</dd></div>
        <div><dt>Offset health</dt><dd className={monitor.offsets_ok ? 'good' : 'warn'}>{monitor.offsets_ok ? 'Version matched · ready' : 'Not ready or version mismatch'}</dd></div>
      </dl>
      <div className="monitor-actions"><button className="btn" onClick={() => onNavigate?.('offsets')}><Icon name="refresh" size={12}/> Manage offsets</button><button className="btn primary" onClick={() => onNavigate?.('flags')}><Icon name="layers" size={12}/> Open FastFlags</button></div>
    </section>
  </div>;
}
