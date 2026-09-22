import { useEffect, useMemo, useState } from 'react';
import { Icon } from '../components/Icons';
import Modal from '../components/Modal';
import { callDesktop } from '../lib/desktopApi';

const STORE = 'vellium.flagMetadata.v1';

export default function DatabaseView({ notify }) {
  const [rows, setRows] = useState([]);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [warningOpen, setWarningOpen] = useState(false);
  const [meta, setMeta] = useState(() => {
    try { return JSON.parse(localStorage.getItem(STORE) || '{}'); }
    catch { return {}; }
  });

  useEffect(() => {
    callDesktop('get_available_flags', '', 0, 500)
      .then(value => setRows(Array.isArray(value) ? value : []));
  }, []);

  const visible = useMemo(() => rows.filter(row =>
    `${row.name} ${meta[row.name]?.nickname || ''} ${meta[row.name]?.description || ''}`
      .toLowerCase().includes(query.toLowerCase())
  ), [rows, meta, query]);

  const update = (key, value) => {
    const next = { ...meta, [selected.name]: { ...meta[selected.name], [key]: value } };
    setMeta(next);
    localStorage.setItem(STORE, JSON.stringify(next));
  };

  return <div className="database-view view">
    <header>
      <div><span>FLAG CATALOG</span><h1>Database</h1><p>Organize FastFlags with your own names and documentation.</p></div>
      <div className="database-header-actions"><button className="btn" onClick={() => setWarningOpen(true)}><Icon name="shield" size={12}/> Memory safety</button><strong>{rows.length.toLocaleString()} entries</strong></div>
    </header>
    <div className="database-grid">
      <section>
        <label><Icon name="search" size={14}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search flags, nicknames, or descriptions…"/></label>
        <div className="database-list">{visible.slice(0, 300).map(row => <button key={row.name} className={selected?.name === row.name ? 'active' : ''} onClick={() => setSelected(row)}><span><strong>{meta[row.name]?.nickname || row.name}</strong><small>{meta[row.name]?.nickname ? row.name : (row.source_category === 'roblox_offsets' ? 'Roblox offset' : 'FFlags.hpp')}</small></span><em>{row.reference_only ? 'RVA' : row.expected_type}</em></button>)}</div>
      </section>
      <aside>{selected ? <>
        <div className="database-detail-head"><span><Icon name={selected.reference_only ? 'code' : 'flag'} size={17}/></span><div><small>{selected.reference_only ? 'ROBLOX OFFSET' : 'FFLAGS.HPP FLAG'}</small><strong>{selected.name}</strong></div></div>
        <label>Nickname<input value={meta[selected.name]?.nickname || ''} onChange={e => update('nickname', e.target.value)} placeholder="Friendly display name"/></label>
        <label>Description<textarea value={meta[selected.name]?.description || ''} onChange={e => update('description', e.target.value)} placeholder="What does this flag do?" rows="5"/></label>
        <dl><div><dt>Type</dt><dd>{selected.expected_type}</dd></div><div><dt>Source</dt><dd>{selected.reference_only ? 'Roblox offsets' : 'FFlags.hpp'}</dd></div>{selected.offset_value && <div><dt>Address · read only</dt><dd><code>{selected.offset_value}</code></dd></div>}</dl>
        <button className="btn primary" onClick={() => notify('Flag metadata saved locally')}><Icon name="save" size={12}/> Save metadata</button>
      </> : <div className="database-empty"><Icon name="database" size={24}/><strong>Select an entry</strong><span>Edit its nickname and description here.</span></div>}</aside>
    </div>
    <Modal open={warningOpen} onClose={() => setWarningOpen(false)} title="Memory address safety" width="430px" tone="danger">
      <div className="memory-safety-copy"><Icon name="warning" size={24}/><p>Roblox memory addresses are version-specific. Editing the wrong address can crash Roblox, stop injection from working, corrupt data, or increase detection and account-action risk.</p><p>Vellium therefore keeps internal memory addresses read-only. You can safely add nicknames and descriptions without changing runtime memory.</p></div>
      <div className="modal-actions"><button className="btn primary" onClick={() => setWarningOpen(false)}>I understand</button></div>
    </Modal>
  </div>;
}
