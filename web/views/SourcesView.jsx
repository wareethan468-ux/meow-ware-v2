import { useEffect, useMemo, useState } from 'react';
import Checkbox from '../components/Checkbox';
import { Icon } from '../components/Icons';
import Modal from '../components/Modal';
import { callDesktop } from '../lib/desktopApi';

export default function SourcesView({ notify }) {
  const [sourceType, setSourceType] = useState('offsets');
  const [query, setQuery] = useState('');
  const [sources, setSources] = useState([]);
  const [configDir, setConfigDir] = useState('');
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [activeUrl, setActiveUrl] = useState('');
  const [confirmDisableTarget, setConfirmDisableTarget] = useState(null);

  const loadSources = async () => {
    const res = await callDesktop('get_offset_sources');
    if (res?.ok && Array.isArray(res.sources)) {
      setSources(res.sources);
      if (res.config_dir) setConfigDir(res.config_dir);
    }
  };

  useEffect(() => {
    loadSources();
  }, []);

  const sourceKind = item => item.kind || (/fflags?\.(?:hpp|h)(?:$|[?#])/i.test(item.url) ? 'fflags' : 'offsets');
  const visible = useMemo(() =>
    sources.filter(item => sourceKind(item) === sourceType && `${item.name} ${item.url}`.toLowerCase().includes(query.toLowerCase())),
    [sources, query, sourceType]
  );

  const handleToggleClick = (item) => {
    if (item.enabled !== false) {
      // Currently enabled -> confirm before disabling
      setConfirmDisableTarget(item);
    } else {
      // Currently disabled -> enable immediately
      performToggle(item, true);
    }
  };

  const performToggle = async (item, enableState) => {
    const nextSources = sources.map(s => s.url === item.url ? { ...s, enabled: enableState } : s);
    setSources(nextSources);
    await callDesktop('save_offset_sources', nextSources);
    notify(`${item.name} ${enableState ? 'enabled' : 'disabled'}`);
    setConfirmDisableTarget(null);
  };

  const activateSource = async (item) => {
    if (!item.url.startsWith('https://')) {
      return notify('Cannot activate offline baseline directly');
    }
    notify(`Activating source: ${item.name}…`);
    const result = await callDesktop('activate_offset_url', item.url);
    if (result?.ok === false) {
      notify(result.error || 'Failed to activate source');
    } else {
      setActiveUrl(item.url);
      notify(result?.message || `Activated offsets from ${item.name}`);
    }
  };

  const add = async () => {
    if (!name.trim() || !/^https:\/\//i.test(url)) return notify('Enter a name and HTTPS URL');
    notify('Validating custom source…');
    const result = await callDesktop('activate_offset_url', url.trim());
    if (result?.ok === false) return notify(result.error || 'Source rejected');

    const nextSources = [...sources, { name: name.trim(), url: url.trim(), enabled: true, kind: sourceType }];
    setSources(nextSources);
    await callDesktop('save_offset_sources', nextSources);
    setActiveUrl(url.trim());
    setName('');
    setUrl('');
    notify(result?.message || 'Custom source added to sources.json and activated');
  };

  const refresh = async () => {
    await loadSources();
    const result = await callDesktop('sync_offsets_selection', 'latest', '');
    notify(result?.ok === false ? result.error : result?.message || 'Sources refreshed');
  };

  const openFolder = async () => {
    await callDesktop('open_config_folder');
  };

  return (
    <div className="manager-view view">
      <header className="manager-header">
        <div>
          <span>{sourceType === 'offsets' ? 'Roblox offset providers' : 'FastFlag header providers'}</span>
          <h1>Sources</h1>
          <p>Managed in {configDir || '%LOCALAPPDATA%\\MeowWare'}\sources.json</p>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="btn" onClick={openFolder}>
            <Icon name="settings" size={13}/> Open config folder
          </button>
          <button className="btn primary" onClick={refresh}>
            <Icon name="refresh" size={13}/> Refresh sources
          </button>
        </div>
      </header>
      <div className="sources-workspace">
        <section className="manager-panel sources-list">
          <div className="source-type-switch" role="tablist" aria-label="Source type">
            <button type="button" role="tab" aria-selected={sourceType === 'offsets'} className={sourceType === 'offsets' ? 'active' : ''} onClick={() => { setSourceType('offsets'); setQuery(''); }}>
              <Icon name="layers" size={13}/> Roblox Offsets
            </button>
            <button type="button" role="tab" aria-selected={sourceType === 'fflags'} className={sourceType === 'fflags' ? 'active' : ''} onClick={() => { setSourceType('fflags'); setQuery(''); }}>
              <Icon name="copy" size={13}/> FFlags.hpp
            </button>
          </div>
          <div className="source-type-content" key={sourceType}>
            <label className="source-search">
              <Icon name="search" size={14}/>
              <input value={query} onChange={e => setQuery(e.target.value)} placeholder={`Search ${sourceType === 'offsets' ? 'Roblox offset' : 'FFlags.hpp'} sources…`}/>
            </label>
            <div>
            {visible.map(item => {
              const isEnabled = item.enabled !== false;
              const isActive = activeUrl === item.url;
              return (
                <div
                  className={`source-row ${isActive ? 'is-active-source' : ''}`}
                  key={`${sourceKind(item)}-${item.url}`}
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px' }}
                >
                  <button
                    type="button"
                    style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'transparent', border: 0, color: 'inherit', textAlign: 'left', flex: 1, cursor: 'pointer', minWidth: 0 }}
                    onClick={() => handleToggleClick(item)}
                  >
                    <Checkbox checked={isEnabled} onChange={() => handleToggleClick(item)} ariaLabel={`Toggle ${item.name}`}/>
                    <span style={{ minWidth: 0, overflow: 'hidden' }}>
                      <strong style={{ display: 'block', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                        {item.name}
                      </strong>
                      <small style={{ display: 'block', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', opacity: 0.7 }}>
                        {item.url}
                      </small>
                    </span>
                  </button>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, marginLeft: 10 }}>
                    {item.url.startsWith('https://') && (
                      <button
                        type="button"
                        className={`btn ${isActive ? 'primary' : ''}`}
                        style={{ height: 26, fontSize: 11, padding: '0 10px', borderRadius: 9999 }}
                        onClick={() => activateSource(item)}
                        title={`Use offsets from ${item.name}`}
                      >
                        {isActive ? 'Active' : 'Use'}
                      </button>
                    )}
                    <button
                      type="button"
                      className={`source-status-pill ${isEnabled ? 'enabled' : 'disabled'}`}
                      onClick={() => handleToggleClick(item)}
                      title={isEnabled ? 'Click to disable source' : 'Click to enable source'}
                    >
                      <span className="pill-dot" />
                      {isEnabled ? 'Enabled' : 'Disabled'}
                    </button>
                  </div>
                </div>
              );
            })}
            {!visible.length && <div className="source-list-empty">No {sourceType === 'offsets' ? 'Roblox offset' : 'FFlags.hpp'} sources match this view.</div>}
            </div>
          </div>
        </section>
        <aside className="manager-panel compact source-add source-type-aside" key={`aside-${sourceType}`}>
          <span className="panel-kicker">Custom {sourceType === 'offsets' ? 'Roblox offset' : 'FastFlag'} source</span>
          <h2>Add {sourceType === 'offsets' ? 'Offset Source' : 'FFlags.hpp Source'}</h2>
          <p>Saved directly to your local config sources.json.</p>
          <input className="input" value={name} onChange={e => setName(e.target.value)} placeholder="Source name"/>
          <input className="input" value={url} onChange={e => setUrl(e.target.value)} placeholder={sourceType === 'offsets' ? 'https://example.com/Offsets.hpp' : 'https://example.com/FFlags.hpp'}/>
          <button className="btn primary" onClick={add}>Add and sync source</button>
          <small>Use an HTTPS URL that returns a compatible {sourceType === 'offsets' ? 'Roblox offset' : 'FastFlag'} header.</small>
        </aside>
      </div>

      {/* Disable Confirmation Modal */}
      <Modal
        open={Boolean(confirmDisableTarget)}
        onClose={() => setConfirmDisableTarget(null)}
        title="Disable Offset Source"
        width="420px"
        footer={<>
          <button className="btn" onClick={() => setConfirmDisableTarget(null)}>Cancel</button>
          <button className="btn danger" onClick={() => performToggle(confirmDisableTarget, false)}>
            Disable Source
          </button>
        </>}
      >
        <p className="modal-body-text">
          Are you sure you want to disable <strong>"{confirmDisableTarget?.name}"</strong>?
        </p>
        <p className="modal-body-text" style={{ color: 'var(--text-3)', fontSize: '11px', marginTop: '6px' }}>
          Disabling this offset source may prevent Vellium Tweaker from finding the latest memory offsets for Roblox FastFlags.
        </p>
      </Modal>
    </div>
  );
}
