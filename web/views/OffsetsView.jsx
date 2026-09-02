import { useEffect, useMemo, useState } from 'react';
import CustomSelect from '../components/CustomSelect';
import { Icon } from '../components/Icons';
import { callDesktop } from '../lib/desktopApi';

const short = value => value ? value.replace(/^version-/, '').slice(0, 12) : 'Not detected';

export default function OffsetsView({ notify }) {
  const [data, setData] = useState({ versions: [] });
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState('latest');
  const [version, setVersion] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setLoading(true);
    const next = await callDesktop('get_offset_sync_options');
    if (next?.ok !== false) setData(next || { versions: [] });
    setLoading(false);
  };

  useEffect(() => {
    refresh();
  }, []);

  const versions = useMemo(() => (data.versions || []).map(item => {
    const value = typeof item === 'string' ? item : item.version;
    return { value, label: value, detail: typeof item === 'object' && item.created_at ? new Date(item.created_at).toLocaleDateString() : '' };
  }), [data.versions]);

  const sync = async () => {
    setBusy(true);
    const result = await callDesktop('sync_offsets_selection', mode, mode === 'custom' ? version : '');
    setBusy(false);
    notify(result?.ok === false ? result.error : result?.message || 'Offsets synced');
    if (result?.ok !== false) refresh();
  };

  const upload = async () => {
    const result = await callDesktop('upload_offsets');
    if (!result?.cancelled) notify(result?.ok === false ? result.error : `Loaded ${result?.count || 0} offsets`);
    refresh();
  };

  const openConfigFolder = async () => {
    await callDesktop('open_config_folder');
  };

  return (
    <div className="manager-view view">
      {/* ── TOP SECTION: Current Offsets Status & Sync ── */}
      <header className="manager-header">
        <div>
          <span>FastFlag data</span>
          <h1>Offsets</h1>
          <p>Keep Vellium Tweaker aligned with the Roblox build you are running.</p>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="btn" onClick={openConfigFolder}>
            <Icon name="settings" size={13}/> Open config folder
          </button>
          <button className="btn" onClick={refresh}>
            <Icon name="refresh" size={13}/> Refresh status
          </button>
        </div>
      </header>

      <div className="offset-status-grid">
        <section>
          <small>Active offsets</small>
          <strong>{short(data.active_offset_version)}</strong>
          <em>{data.active_offset_version || 'No dump loaded'}</em>
        </section>
        <section>
          <small>Installed Roblox</small>
          <strong>{short(data.installed_version)}</strong>
          <em>{data.installed_version || 'No install detected'}</em>
        </section>
        <section>
          <small>Latest production</small>
          <strong>{short(data.latest_production)}</strong>
          <em>{data.latest_production || 'Checking channel'}</em>
        </section>
      </div>

      <div className="offset-workspace" style={{ marginBottom: 30 }}>
        <section className="manager-panel">
          <div className="panel-heading">
            <span className="discovery-icon"><Icon name="refresh" size={15}/></span>
            <div>
              <strong>Sync offset dump</strong>
              <small>Select newest, installed, or an exact Roblox version.</small>
            </div>
          </div>
          <div className="offset-choice-row" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))' }}>
            {[
              { id: 'latest', title: 'Newest available', sub: 'Recommended' },
              { id: 'current', title: 'Match installed', sub: data.installed_version || 'Not detected' },
              { id: 'custom', title: 'Version hash', sub: 'Historical' },
            ].map(item => (
              <button key={item.id} className={mode === item.id ? 'active' : ''} onClick={() => setMode(item.id)}>
                <i/>
                <span>
                  <strong>{item.title}</strong>
                  <small>{item.sub}</small>
                </span>
              </button>
            ))}
          </div>

          {mode === 'custom' && (
            <div className="offset-custom">
              <label>Version hash</label>
              <CustomSelect searchable value={version} onChange={setVersion} options={versions} label="Choose a Roblox version" />
            </div>
          )}

          <button
            className="btn primary manager-action"
            disabled={busy || loading || (mode === 'custom' && !version)}
            onClick={sync}
          >
            {busy ? 'Syncing…' : 'Sync offsets'}
          </button>
        </section>

        <aside className="manager-panel compact">
          <span className="panel-kicker">Local source</span>
          <h2>Import FFlags.hpp</h2>
          <p>Load a trusted C++ offset header directly from your computer.</p>
          <button className="btn" onClick={upload}>
            <Icon name="upload" size={13}/> Choose header file
          </button>
        </aside>
      </div>

    </div>
  );
}
