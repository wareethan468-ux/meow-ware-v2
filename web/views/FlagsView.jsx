import { useEffect, useMemo, useRef, useState } from 'react';
import Checkbox from '../components/Checkbox';
import { Icon } from '../components/Icons';
import Modal from '../components/Modal';
import CustomSelect from '../components/CustomSelect';
import NumberInput from '../components/NumberInput';
import OperationProgressModal from '../components/OperationProgressModal';
import { callDesktop, hasDesktopApi } from '../lib/desktopApi';
import RobloxAccountCard from '../components/RobloxAccountCard';
import InfoTooltip from '../components/InfoTooltip';
const BOOLEAN_OPTIONS = [{ value: 'True', label: 'True' }, { value: 'False', label: 'False' }];

/* ── small helpers ── */
function shortVersion(v) {
  if (!v) return '—';
  // "version-abc123def456" → "abc123…"
  const m = v.match(/version-([a-f0-9]+)/i);
  return m ? m[1].slice(0, 12) : v;
}

function flagKind(name, value) {
  if (/^(?:D?FFlag)/i.test(name) || /^(?:true|false)$/i.test(value)) return 'bool';
  if (/^(?:D?FInt)/i.test(name) || /^-?\d+$/.test(value)) return 'int';
  if (/^(?:D?FLog)/i.test(name)) return 'log';
  if (/^(?:FString)/i.test(name)) return 'text';
  return 'value';
}

function flagDescription(flag) {
  const type = flag.expected_type || 'unknown';
  const prefix = flag.prefix || 'FastFlag';
  if (type === 'bool') return `A Boolean Roblox feature switch. Use True to enable it or False to disable it.`;
  if (type === 'int') return `A whole-number Roblox configuration value. Its ${prefix} prefix indicates an integer setting.`;
  if (type === 'float') return `A decimal Roblox configuration value used for fine-grained tuning.`;
  if (type === 'string') return `A text-based Roblox configuration value.`;
  return `A known Roblox FastFlag discovered from the active offset and flag sources.`;
}

function FlagValueEditor({ name, value, onCommit }) {
  const kind = flagKind(name, value);
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  if (kind === 'bool') {
    const enabled = String(value).toLowerCase() === 'true';
    return <div className="flag-bool-control" role="group" aria-label={`Value for ${name}`}>
      <button className={enabled ? 'active' : ''} onClick={() => !enabled && onCommit('True')}>True</button>
      <button className={!enabled ? 'active' : ''} onClick={() => enabled && onCommit('False')}>False</button>
    </div>;
  }
  const commit = () => draft !== value && onCommit(draft);
  return <label className={`flag-value-editor ${kind}`}>
    <span>{kind === 'int' ? '#' : kind === 'log' ? 'LOG' : 'TXT'}</span>
    <input value={draft} onChange={event => setDraft(event.target.value)} onBlur={commit} onKeyDown={event => event.key === 'Enter' && event.currentTarget.blur()} aria-label={`Value for ${name}`} />
  </label>;
}

/* ── Sync offsets modal (its own component so hooks are isolated) ── */
function SyncModal({ open, onClose, notify }) {
  const [status,  setStatus]  = useState(null);   // null = loading
  const [err,     setErr]     = useState('');
  const [mode,    setMode]    = useState('latest');
  const [custom,  setCustom]  = useState('');
  const [syncing, setSyncing] = useState(false);
  const [syncErr, setSyncErr] = useState('');

  useEffect(() => {
    if (!open) return;
    setStatus(null); setErr(''); setMode('latest'); setCustom(''); setSyncErr('');
    callDesktop('get_offset_sync_options').then(r => {
      if (!r || r.ok === false) setErr(r?.error || 'Could not load sync info');
      else setStatus(r);
    });
  }, [open]);

  const doSync = async () => {
    setSyncing(true); setSyncErr('');
    const r = await callDesktop('sync_offsets_selection', mode, mode === 'custom' ? custom : '');
    setSyncing(false);
    if (!r || r.ok === false) {
      setSyncErr(r?.error || 'Sync failed');
    } else {
      notify(r.message || 'Offsets synced');
      onClose();
    }
  };

  const MODES = [
    {
      id: 'latest',
      name: 'Latest production',
      desc: status ? `CDN: ${shortVersion(status.latest_production)}` : 'Most recent Roblox CDN build',
    },
    {
      id: 'current',
      name: 'Match installed Roblox',
      desc: status?.installed_version
        ? `Installed: ${shortVersion(status.installed_version)}`
        : 'No Roblox install detected',
      disabled: !status?.installed_version,
    },
    {
      id: 'custom',
      name: 'Specific version',
      desc: 'Enter a version hash manually',
    },
  ];

  const activeMatches = status?.active_offset_version &&
    status?.installed_version &&
    status.active_offset_version === status.installed_version;

  const canSync = !syncing && (!syncErr || true) &&
    (mode !== 'custom' || custom.trim().length > 0) &&
    (mode !== 'current' || status?.installed_version);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Sync Offsets"
      subtitle="Update the flag offset data used for memory injection"
      width="460px"
      footer={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={doSync} disabled={!canSync}>
            {syncing ? 'Syncing…' : 'Sync'}
          </button>
        </>
      }
    >
      {err ? (
        <p className="sync-loading" style={{ color: 'var(--red)' }}>{err}</p>
      ) : !status ? (
        <p className="sync-loading">Loading version info…</p>
      ) : (
        <>
          {/* Version info grid */}
          <div className="sync-info-grid">
            <div className="sync-info-cell">
              <div className="sync-info-label">Active offsets</div>
              <div className={`sync-info-val ${activeMatches ? 'match' : status.active_offset_version ? 'stale' : 'dim'}`}>
                {shortVersion(status.active_offset_version) || '—'}
              </div>
            </div>
            <div className="sync-info-cell">
              <div className="sync-info-label">Installed Roblox</div>
              <div className={`sync-info-val ${activeMatches ? 'match' : 'stale'}`}>
                {shortVersion(status.installed_version) || '—'}
              </div>
            </div>
            <div className="sync-info-cell">
              <div className="sync-info-label">Latest CDN</div>
              <div className="sync-info-val">{shortVersion(status.latest_production) || '—'}</div>
            </div>
            <div className="sync-info-cell">
              <div className="sync-info-label">Versions available</div>
              <div className="sync-info-val">{status.versions?.length ?? 0}</div>
            </div>
          </div>

          {/* Mode picker */}
          <div className="sync-mode-list">
            {MODES.map(m => (
              <button
                key={m.id}
                className={`sync-mode-option${mode === m.id ? ' selected' : ''}`}
                onClick={() => !m.disabled && setMode(m.id)}
                disabled={m.disabled}
                style={m.disabled ? { opacity: 0.45, cursor: 'not-allowed' } : {}}
              >
                <div className="sync-dot" />
                <div className="sync-mode-text">
                  <span className="sync-mode-name">{m.name}</span>
                  <span className="sync-mode-desc">{m.desc}</span>
                </div>
              </button>
            ))}
          </div>

          {/* Custom version input */}
          {mode === 'custom' && (
            <div className="sync-custom-wrap">
              <label className="label">Version hash</label>
              {status.versions?.length > 0 ? (
                <select
                  className="input"
                  style={{ height: 32 }}
                  value={custom}
                  onChange={e => setCustom(e.target.value)}
                >
                  <option value="">Select a version…</option>
                  {status.versions.map(v => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              ) : (
                <input
                  className="input"
                  placeholder="version-abc123…"
                  value={custom}
                  onChange={e => setCustom(e.target.value)}
                />
              )}
            </div>
          )}

          {syncErr && <p className="sync-err">{syncErr}</p>}
        </>
      )}
    </Modal>
  );
}

/* ── Main FlagsView ── */
export default function FlagsView({ flags, refreshFlags, notify }) {
  const [query,    setQuery]    = useState('');
  const [catalogQuery, setCatalogQuery] = useState('');
  const [catalogFlags, setCatalogFlags] = useState([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [killed,   setKilled]   = useState(false);
  const [applying, setApplying] = useState(false);

  const [modal, setModal] = useState(null);
  const [launchTargets, setLaunchTargets] = useState([]);
  const [launchTarget, setLaunchTarget] = useState('');
  const [launchLoading, setLaunchLoading] = useState(false);
  const [addName, setAddName] = useState('');
  const [addVal,  setAddVal]  = useState('True');
  const [valMode, setValMode] = useState('auto');
  const [addSuggestions, setAddSuggestions] = useState([]);
  const [showAddSuggestions, setShowAddSuggestions] = useState(false);
  const [addSearching, setAddSearching] = useState(false);
  const [addError, setAddError] = useState('');
  const [deleteFilter, setDeleteFilter] = useState('');
  const [impTab,  setImpTab]  = useState('file');
  const [impText, setImpText] = useState('');

  // Bulk add state
  const [bulkTab, setBulkTab] = useState('rows'); // 'rows' or 'paste'
  const [bulkRows, setBulkRows] = useState([{ id: 1, name: '', value: '', type: 'string' }]);
  const [bulkText, setBulkText] = useState('');
  const [bulkActiveRow, setBulkActiveRow] = useState(null);
  const [bulkSuggestions, setBulkSuggestions] = useState([]);
  const [bulkSearching, setBulkSearching] = useState(false);
  const [pasteSuggestions, setPasteSuggestions] = useState([]);
  const [pasteSearching, setPasteSearching] = useState(false);
  const bulkEditorRef = useRef(null);

  const addBulkRow = () => {
    setBulkRows(cur => [...cur, { id: Date.now() + Math.random(), name: '', value: '', type: 'string' }]);
  };

  const removeBulkRow = (id) => {
    setBulkRows(cur => cur.length > 1 ? cur.filter(r => r.id !== id) : [{ id: 1, name: '', value: '', type: 'string' }]);
  };

  const updateBulkRow = (id, field, val) => {
    setBulkRows(cur => cur.map(r => r.id === id ? { ...r, [field]: val } : r));
  };

  useEffect(() => {
    if (modal !== 'bulk_add' || !bulkActiveRow || !hasDesktopApi()) return undefined;
    const row = bulkRows.find(item => item.id === bulkActiveRow);
    const query = row?.name?.trim();
    if (!query) {
      setBulkSuggestions([]);
      return undefined;
    }
    setBulkSearching(true);
    const timer = window.setTimeout(async () => {
      try {
        const result = await callDesktop('get_available_flags', query, 0, 8);
        setBulkSuggestions(Array.isArray(result) ? result : []);
      } catch {
        setBulkSuggestions([]);
      } finally {
        setBulkSearching(false);
      }
    }, 120);
    return () => window.clearTimeout(timer);
  }, [bulkRows, bulkActiveRow, modal]);

  const selectBulkSuggestion = (row, flag) => {
    updateBulkRow(row.id, 'name', flag.name);
    if (!row.value) updateBulkRow(row.id, 'value', flag.expected_type === 'bool' ? 'True' : ['int', 'float'].includes(flag.expected_type) ? '0' : '');
    setBulkActiveRow(null);
  };

  const bulkTypeOptions = [
    { value: 'string', label: 'String' },
    { value: 'number', label: 'Number' },
    { value: 'bool', label: 'Boolean' },
    { value: 'auto', label: 'Auto' },
  ];

  // Edit modal state
  const [editFlag, setEditFlag] = useState({ name: '', value: '', originalName: '', mode: 'auto' });

  // Operation loading modal state
  const [opState, setOpState] = useState({
    open: false,
    title: '',
    subtitle: '',
    steps: [],
  });

  const startOp = (title, subtitle, steps) => {
    setOpState({ open: true, title, subtitle, steps });
  };

  const endOp = async () => {
    await new Promise(r => setTimeout(r, 480));
    setOpState(prev => ({ ...prev, open: false }));
  };

  const parseBulkInput = (text) => {
    const raw = text.trim();
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.filter(item => item && (item.name || item[0])).map(item => [
          String(item.name || item[0]),
          String(item.value !== undefined ? item.value : item[1] !== undefined ? item[1] : 'True')
        ]);
      }
      if (typeof parsed === 'object' && parsed !== null) {
        return Object.entries(parsed).map(([k, v]) => [k, String(v)]);
      }
    } catch {}

    const list = [];
    const lines = raw.split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#') || trimmed.startsWith('//')) continue;
      const eqIdx = trimmed.indexOf('=');
      const colonIdx = trimmed.indexOf(':');
      if (eqIdx > 0) {
        list.push([trimmed.slice(0, eqIdx).trim(), trimmed.slice(eqIdx + 1).trim()]);
      } else if (colonIdx > 0) {
        list.push([trimmed.slice(0, colonIdx).trim(), trimmed.slice(colonIdx + 1).trim().replace(/^["']|["']$/g, '')]);
      } else {
        const parts = trimmed.split(/\s+/);
        if (parts.length >= 2) {
          list.push([parts[0], parts.slice(1).join(' ')]);
        } else if (parts.length === 1) {
          list.push([parts[0], 'True']);
        }
      }
    }
    return list;
  };

  const parsedBulkFlags = useMemo(() => parseBulkInput(bulkText), [bulkText]);
  const bulkJsonStatus = useMemo(() => {
    if (!bulkText.trim()) return { kind: 'empty', message: 'Start typing or pick a JSON file' };
    try { JSON.parse(bulkText); return { kind: 'valid', message: 'Valid JSON' }; }
    catch (error) { return { kind: parsedBulkFlags.length ? 'loose' : 'error', message: parsedBulkFlags.length ? 'List format detected — JSON formatting can be repaired' : String(error.message || 'Invalid JSON') }; }
  }, [bulkText, parsedBulkFlags]);
  const validBulkRowCount = useMemo(() => bulkRows.filter(r => r.name.trim().length > 0).length, [bulkRows]);

  useEffect(() => {
    if (modal !== 'bulk_add' || bulkTab !== 'paste' || !hasDesktopApi()) return undefined;
    const cursor = bulkEditorRef.current?.selectionStart ?? bulkText.length;
    const token = bulkText.slice(0, cursor).match(/["']?([A-Za-z][A-Za-z0-9_]{2,})$/)?.[1];
    if (!token) { setPasteSuggestions([]); return undefined; }
    setPasteSearching(true);
    const timer = window.setTimeout(async () => {
      try { const result = await callDesktop('get_available_flags', token, 0, 7); setPasteSuggestions(Array.isArray(result) ? result : []); }
      catch { setPasteSuggestions([]); }
      finally { setPasteSearching(false); }
    }, 120);
    return () => window.clearTimeout(timer);
  }, [bulkText, bulkTab, modal]);

  const repairBulkJson = () => {
    let repaired = bulkText.replace(/[“”]/g, '"').replace(/[‘’]/g, "'").replace(/\bTrue\b/g, 'true').replace(/\bFalse\b/g, 'false').replace(/\bNone\b/g, 'null');
    repaired = repaired.replace(/([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)/g, '$1"$2"$3').replace(/'([^'\n]*)'\s*:/g, '"$1":').replace(/:\s*'([^'\n]*)'/g, ': "$1"').replace(/,\s*([}\]])/g, '$1');
    try { setBulkText(JSON.stringify(JSON.parse(repaired), null, 2)); notify('JSON formatting repaired'); return; } catch {}
    const parsed = parseBulkInput(repaired);
    if (parsed.length) { setBulkText(JSON.stringify(Object.fromEntries(parsed), null, 2)); notify('Converted list to valid JSON'); }
    else notify('Could not repair this JSON automatically');
  };

  const insertPasteSuggestion = flag => {
    const editor = bulkEditorRef.current; const cursor = editor?.selectionStart ?? bulkText.length; const before = bulkText.slice(0,cursor); const match = before.match(/["']?([A-Za-z][A-Za-z0-9_]*)$/); if (!match) return;
    const start = cursor-match[0].length; const value = flag.expected_type==='bool'?'true':['int','float'].includes(flag.expected_type)?'0':'""';
    const insertion = `"${flag.name}": ${value}`; setBulkText(bulkText.slice(0,start)+insertion+bulkText.slice(cursor)); setPasteSuggestions([]);
    requestAnimationFrame(()=>editor?.focus());
  };

  const pickBulkJson = async () => { const result=await callDesktop('pick_bulk_json_file'); if(result?.ok){setBulkText(result.text||'');notify(`Loaded ${result.name}`)}else if(!result?.cancelled)notify(result?.error||'Could not load JSON file') };

  const open  = id => {
    if (id === 'add') {
      setShowAddSuggestions(false);
      setValMode('auto');
      setAddError('');
    }
    if (id === 'pick_delete') {
      setDeleteFilter('');
    }
    if (id === 'bulk_add') {
      setBulkTab('rows');
      setBulkRows([{ id: 1, name: '', value: '', type: 'string' }]);
      setBulkText('');
    }
    setModal(id);
  };
  const close = ()  => {
    setShowAddSuggestions(false);
    setAddError('');
    setModal(null);
  };

  useEffect(() => {
    if (modal !== 'launch' || !hasDesktopApi()) return;
    let active = true;
    setLaunchLoading(true);
    callDesktop('get_launch_targets').then((result) => {
      if (!active) return;
      const targets = result?.targets || [];
      setLaunchTargets(targets);
      setLaunchTarget(result?.selected_path || targets.find(item => item.selected)?.path || targets[0]?.path || '');
    }).catch(() => {
      if (active) setLaunchTargets([]);
    }).finally(() => active && setLaunchLoading(false));
    return () => { active = false; };
  }, [modal]);

  const deleteSingleFlag = async (name) => {
    const res = await callDesktop('remove_flags', [name]);
    if (res?.ok === false) notify(res.error || 'Failed to delete flag');
    else {
      notify(`Removed ${name}`);
      await refreshFlags();
    }
  };

  const startEditFlag = (name, value) => {
    const kind = flagKind(name, value);
    setEditFlag({
      originalName: name,
      name,
      value: String(value),
      mode: kind === 'bool' ? 'bool' : kind === 'int' ? 'number' : 'text',
    });
    setModal('edit_flag');
  };

  const doSaveEditFlag = async () => {
    const trimmed = editFlag.name.trim();
    if (!trimmed) return notify('Flag name cannot be empty');
    if (trimmed !== editFlag.originalName) {
      await callDesktop('remove_flags', [editFlag.originalName]);
      const res = await callDesktop('add_flag', trimmed, editFlag.value);
      if (res?.ok === false) return notify(res.error || 'Failed to rename flag');
    } else {
      const res = await callDesktop('update_flag', trimmed, editFlag.value);
      if (res?.ok === false) return notify(res.error || 'Failed to update flag');
    }
    await refreshFlags();
    close();
    notify(`Updated ${trimmed}`);
  };

  const doBulkAdd = async () => {
    const list = bulkTab === 'rows'
      ? bulkRows.filter(r => r.name.trim().length > 0).map(r => [r.name.trim(), r.value])
      : parsedBulkFlags;

    if (!list.length) return notify('No valid flags to add');
    notify(`Adding ${list.length} flags…`);
    let added = 0;
    for (const [k, v] of list) {
      let r = await callDesktop('add_flag', k, v);
      if (r?.ok === false && String(r.error).includes('already')) {
        r = await callDesktop('update_flag', k, v);
      }
      if (r?.ok !== false) added++;
    }
    refreshFlags();
    close();
    notify(`Added ${added} of ${list.length} flags`);
  };

  const visible = useMemo(() =>
    flags.map((f, i) => ({ f, i }))
         .filter(({ f }) => f[0].toLowerCase().includes(query.toLowerCase())),
    [flags, query]
  );

  const filteredWorkspaceFlags = useMemo(() => {
    const q = deleteFilter.trim().toLowerCase();
    return q ? flags.filter(([name]) => name.toLowerCase().includes(q)) : flags;
  }, [flags, deleteFilter]);

  const allSel  = visible.length > 0 && visible.every(({ i }) => selected.has(i));
  const someSel = visible.length > 0 && visible.some(({ i }) => selected.has(i)) && !allSel;

  useEffect(() => {
    callDesktop('get_killswitch_state').then(s => s && setKilled(Boolean(s.active)));
  }, []);

  useEffect(() => {
    if (!hasDesktopApi()) return undefined;
    const timer = window.setTimeout(async () => {
      setCatalogLoading(true);
      try {
        const result = await callDesktop('get_available_flags', catalogQuery, 0, 60);
        setCatalogFlags(Array.isArray(result) ? result : []);
      } finally {
        setCatalogLoading(false);
      }
    }, 180);
    return () => window.clearTimeout(timer);
  }, [catalogQuery]);

  useEffect(() => {
    if (!hasDesktopApi() || modal !== 'add') return undefined;
    const q = addName.trim();
    if (!q) {
      setAddSuggestions([]);
      setAddSearching(false);
      return undefined;
    }
    setAddSearching(true);
    const timer = window.setTimeout(async () => {
      try {
        const result = await callDesktop('get_available_flags', q, 0, 15);
        setAddSuggestions(Array.isArray(result) ? result : []);
      } catch {
        setAddSuggestions([]);
      } finally {
        setAddSearching(false);
      }
    }, 100);
    return () => window.clearTimeout(timer);
  }, [addName, modal]);

  const chooseCatalogFlag = flag => {
    setAddName(flag.name);
    setAddVal(flag.expected_type === 'bool' ? 'True' : ['int', 'float'].includes(flag.expected_type) ? '0' : '');
    setAddError('');
    open('add');
  };

  const selectAddSuggestion = flag => {
    setAddName(flag.name);
    setAddVal(flag.expected_type === 'bool' ? 'True' : ['int', 'float'].includes(flag.expected_type) ? '0' : '');
    setShowAddSuggestions(false);
    setAddError('');
  };

  const detectedKind = useMemo(() => {
    return flagKind(addName, addVal) || 'bool';
  }, [addName, addVal]);

  const effectiveType = useMemo(() => {
    if (valMode === 'auto') {
      if (detectedKind === 'bool') return 'bool';
      if (detectedKind === 'int' || detectedKind === 'float') return 'number';
      return 'text';
    }
    return valMode;
  }, [valMode, detectedKind]);

  const valTypeOptions = useMemo(() => [
    { value: 'auto', label: `Auto detect (${detectedKind})` },
    { value: 'bool', label: 'Boolean (True / False)' },
    { value: 'number', label: 'Numerical (Number)' },
    { value: 'text', label: 'Text (String)' },
  ], [detectedKind]);

  const directFlags = catalogFlags.filter(flag => flag.match_kind !== 'related');
  const relatedFlags = catalogFlags.filter(flag => flag.match_kind === 'related');
  const renderCatalogFlag = flag => {
    const added = flags.some(([name]) => name === flag.name);
    return (
      <InfoTooltip key={flag.name} content={<div className="flag-info-card"><div className="flag-info-head"><span><Icon name="flag" size={13}/></span><div><strong>{flag.name}</strong><small>FastFlag details</small></div></div><p>{flagDescription(flag)}</p><dl><div><dt>Value type</dt><dd>{flag.expected_type || 'Unknown'}</dd></div><div><dt>Prefix</dt><dd>{flag.prefix || 'Unknown'}</dd></div><div><dt>Search match</dt><dd>{flag.match_kind === 'related' ? 'Related' : 'Direct'}</dd></div><div><dt>Workspace</dt><dd>{added ? 'Already added' : 'Available'}</dd></div></dl><span className="flag-info-hint">Move the pointer here to keep this open</span></div>}>
        <button className={`catalog-item${added ? ' added' : ''}`} onClick={() => chooseCatalogFlag(flag)}>
          <span><strong>{flag.name}</strong><small>{flag.expected_type || 'value'} · {flag.prefix || 'flag'}</small></span>
          <em>{added ? 'Added' : '+'}</em>
        </button>
      </InfoTooltip>
    );
  };

  const toggleAll = checked =>
    setSelected(checked ? new Set(visible.map(({ i }) => i)) : new Set());
  const toggleRow = i =>
    setSelected(cur => { const n = new Set(cur); n.has(i) ? n.delete(i) : n.add(i); return n; });

  const editValue = async (i, v) => {
    const r = await callDesktop('update_flag', flags[i][0], v);
    if (r?.ok === false) notify(r.error || 'Update failed');
    refreshFlags();
  };

  const doAdd = async () => {
    const trimmed = addName.trim();
    if (!trimmed) return;
    setAddError('');
    const r = await callDesktop('add_flag', trimmed, addVal);
    if (r?.ok === false) {
      const err = r.error || 'Invalid FastFlag: flag not found in database.';
      setAddError(err);
      notify(err);
      return;
    }
    notify('Flag added');
    close();
    setAddName('');
    setAddVal('True');
    setAddError('');
    refreshFlags();
  };

  const doRemove = async () => {
    const names = [...selected].map(i => flags[i][0]);
    await callDesktop('remove_flags', names);
    setSelected(new Set()); close();
    notify(`Removed ${names.length} flag${names.length !== 1 ? 's' : ''}`);
    refreshFlags();
  };

  const doDeleteOne = async flagName => {
    await callDesktop('remove_flags', [flagName]);
    notify(`Removed ${flagName}`);
    refreshFlags();
    close();
  };

  const doClear = async () => {
    close();
    startOp('Clearing Workspace', 'Resetting active configuration', [
      'Removing flag definitions...',
      'Flushing memory patches...',
      'Finalizing reset...',
    ]);
    try {
      await callDesktop('clear_all');
      setSelected(new Set());
      notify('All flags cleared');
      refreshFlags();
    } finally {
      await endOp();
    }
  };

  const doImportFile = async () => {
    close();
    startOp('Importing FastFlags', 'Parsing configuration file', [
      'Reading JSON file...',
      'Validating flag keys & types...',
      'Merging into local workspace...',
      'Finalizing import...',
    ]);
    try {
      const r = await callDesktop('import_flags');
      if (r !== false) {
        notify('Flags imported');
        refreshFlags();
      }
    } finally {
      await endOp();
    }
  };

  const doImportText = async () => {
    if (!impText.trim()) return;
    close();
    startOp('Importing FastFlags', 'Parsing text input', [
      'Parsing JSON/text content...',
      'Validating flag entries...',
      'Adding to workspace...',
      'Done',
    ]);
    try {
      const r = await callDesktop('import_flags_from_text', impText);
      if (r?.ok === false) {
        notify(r.error || 'Import failed');
        return;
      }
      setImpText('');
      notify(`Imported ${r?.added ?? 0} flags (${r?.skipped ?? 0} skipped)`);
      refreshFlags();
    } finally {
      await endOp();
    }
  };

  const doExport = async () => {
    close();
    startOp('Exporting FastFlags', 'Saving configuration file', [
      'Collecting active flag table...',
      'Formatting JSON schema...',
      'Writing to destination file...',
      'Export complete',
    ]);
    try {
      await callDesktop('export_flags');
      notify('Exported');
    } finally {
      await endOp();
    }
  };

  const doLaunch = async () => {
    if (!launchTarget) return notify('Choose a Roblox installation first');
    close();
    startOp('Launching Roblox', 'Starting client with FastFlags attached', [
      'Writing startup configurations...',
      'Launching Roblox application...',
      'Attaching process monitor...',
      'Done',
    ]);
    try {
      notify('Launching Roblox…');
      await callDesktop('set_launch_target', launchTarget);
      await callDesktop('launch_and_apply', launchTarget);
    } finally {
      await endOp();
    }
  };

  const doUpload = async () => {
    close();
    startOp('Uploading Offsets', 'Importing offset definitions', [
      'Reading offset dump file...',
      'Parsing binary offsets...',
      'Updating local catalog...',
    ]);
    try {
      const r = await callDesktop('upload_offsets');
      if (!r?.cancelled) {
        notify(r?.ok === false ? (r.error || 'Upload failed') : `Loaded ${r?.count ?? 0} offsets`);
      }
    } finally {
      await endOp();
    }
  };

  const doInject = async () => {
    close();
    const isRestore = killed;
    startOp(
      isRestore ? 'Restoring FastFlags' : 'Uninjecting FastFlags',
      isRestore ? 'Re-enabling active configurations' : 'Safely resetting Roblox flags',
      [
        'Locating Roblox instances...',
        'Updating FastFlag state...',
        'Syncing runtime changes...',
        'Done',
      ]
    );
    try {
      if (isRestore) {
        const r = await callDesktop('restore_flags');
        if (r?.ok === false) return notify(r.error || 'Restore failed');
        setKilled(false);
        notify('Flags restored');
      } else {
        const r = await callDesktop('disable_all_flags');
        if (r?.ok === false) return notify(r.error || 'Uninject failed');
        setKilled(true);
        notify('Flags uninjected');
      }
    } finally {
      await endOp();
    }
  };

  const doApply = async () => {
    close();
    setApplying(true);
    startOp('Applying FastFlags', 'Injecting FastFlag settings into Roblox', [
      'Scanning active Roblox processes...',
      'Writing ClientAppSettings.json...',
      'Applying live memory patches...',
      'Finalizing injection...',
    ]);
    try {
      await callDesktop('inject_user');
      notify('FastFlags applied successfully');
    } catch {
      notify('Apply failed');
    } finally {
      setApplying(false);
      await endOp();
      refreshFlags();
    }
  };

  return (
    <div className="flags-layout view">

      <aside className="flag-discovery">
        <div className="discovery-heading">
          <span className="discovery-icon"><Icon name="search" size={15} /></span>
          <div><strong>FastFlag Search</strong><small>Browse known offset flags</small></div>
        </div>
        <label className="discovery-search">
          <Icon name="search" size={14} />
          <input value={catalogQuery} onChange={event => setCatalogQuery(event.target.value)} placeholder="Search known flags…" />
        </label>
        <div className="discovery-results">
          {catalogLoading ? <div className="discovery-message">Searching…</div> : catalogFlags.length ? <>
            <div className="discovery-group"><span>{catalogQuery ? 'Best matches' : 'Suggestions'}</span><em>{directFlags.length}</em></div>
            {directFlags.map(renderCatalogFlag)}
            {relatedFlags.length > 0 && <>
              <div className="discovery-divider" />
              <div className="discovery-group"><span>Related flags</span><em>{relatedFlags.length}</em></div>
              {relatedFlags.map(renderCatalogFlag)}
            </>}
          </> : <div className="discovery-message">{hasDesktopApi() ? 'No matching flags' : 'Available in the desktop app'}</div>}
        </div>
        <button className="btn discovery-manual" onClick={() => { setAddName(''); setAddVal('True'); open('add'); }}><Icon name="plus" size={12} /> Add manually</button>
        <RobloxAccountCard />
      </aside>

      {/* ── Main column ── */}
      <div className="flag-col">
        <div className="flag-col-header">
          <div>
            <div className="view-title">Flag configuration</div>
            <div className="view-sub">Review values before applying them to Roblox</div>
          </div>
          <div className="flag-header-meta">
            <span>{selected.size ? `${selected.size} selected` : 'No selection'}</span>
            <strong className="flag-count-badge">
              <Icon name="flag" size={11} />
              <span>{flags.length}</span>
            </strong>
          </div>
        </div>

        {flags.length > 0 && (
          <div className="search">
            <Icon name="search" size={14} />
            <input
              placeholder="Search flags…"
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
          </div>
        )}

        {flags.length > 0 && (
          <div className="flag-thead">
            <Checkbox checked={allSel} indeterminate={someSel} onChange={toggleAll} ariaLabel="Select all" />
            <span>Flag</span>
            <span>Value</span>
            <span style={{ textAlign: 'right' }}>Actions</span>
          </div>
        )}

        <div className="flag-list">
          {flags.length === 0 ? (
            <div className="empty">
              <div className="empty-icon"><Icon name="flag" size={20} /></div>
              <span className="empty-title">No flags imported</span>
              <span className="empty-desc">Add a flag manually, use bulk add, or import a JSON configuration to get started.</span>
              <div className="empty-actions">
                <button className="btn" onClick={() => open('add')}>
                  <Icon name="plus" size={12} /> Add Flag
                </button>
                <button className="btn" onClick={() => open('bulk_add')}>
                  <Icon name="list" size={12} /> Bulk Add
                </button>
                <button className="btn" onClick={() => open('import')}>
                  <Icon name="download" size={12} /> Import
                </button>
              </div>
            </div>
          ) : visible.length === 0 ? (
            <div className="empty">
              <div className="empty-icon"><Icon name="search" size={20} /></div>
              <span className="empty-title">No flags</span>
              <span className="empty-desc">No flags match &ldquo;{query}&rdquo;</span>
            </div>
          ) : visible.map(({ f, i }) => (
            <div className="flag-row" key={f[0]}>
              <Checkbox checked={selected.has(i)} onChange={() => toggleRow(i)} ariaLabel={f[0]} />
              <div className="flag-identity"><strong title={f[0]}>{f[0]}</strong><span>{flagKind(f[0], f[1])}</span></div>
              <FlagValueEditor name={f[0]} value={f[1]} onCommit={value => editValue(i, value)} />
              <div className="row-actions">
                <button
                  type="button"
                  className="expandable-btn"
                  title="Edit flag"
                  onClick={() => startEditFlag(f[0], f[1])}
                >
                  <Icon name="edit" size={11} />
                  <span>Edit</span>
                </button>
                <button
                  type="button"
                  className="expandable-btn danger"
                  title="Delete flag"
                  onClick={() => deleteSingleFlag(f[0])}
                >
                  <Icon name="trash" size={11} />
                  <span>Delete</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Sidebar ── */}
      <div className="flag-sidebar">
        <section className="sidebar-section"><span className="sidebar-label">Edit</span>
          <button className="sidebar-action" onClick={() => open('add')}><Icon name="plus" size={13} /><span><strong>Add flag</strong><small>Create one manually</small></span></button>
          <button className="sidebar-action" onClick={() => open('bulk_add')}><Icon name="list" size={13} /><span><strong>Bulk add</strong><small>Paste multiple flags</small></span></button>
          <button className="sidebar-action danger" onClick={() => selected.size ? open('remove') : flags.length ? open('pick_delete') : notify('No flags in workspace')}><Icon name="trash" size={13} /><span><strong>Remove</strong><small>{selected.size ? `${selected.size} selected` : 'Pick or select'}</small></span></button>
          <button className="sidebar-text-action danger" onClick={() => flags.length ? open('clear') : notify('Nothing to clear')}>Clear configuration</button>
        </section>
        <section className="sidebar-section"><span className="sidebar-label">Data</span>
          <button className="sidebar-action" onClick={() => open('import')}><Icon name="download" size={13} /><span><strong>Import</strong><small>JSON or text</small></span></button>
          <button className="sidebar-action" onClick={() => flags.length ? open('export') : notify('No flags to export')}><Icon name="upload" size={13} /><span><strong>Export</strong><small>Save configuration</small></span></button>
        </section>
        <section className="sidebar-section"><span className="sidebar-label">Session</span>
          <button className="sidebar-action" onClick={() => open('launch')} onContextMenu={event => { event.preventDefault(); open('launch'); }}><Icon name="play" size={13} /><span><strong>Launch Roblox</strong><small>Choose installation · apply on startup</small></span></button>
          <button className="sidebar-action" onClick={() => open('sync')}><Icon name="refresh" size={13} /><span><strong>Sync offsets</strong><small>Update definitions</small></span></button>
          <button className="sidebar-action danger subtle" onClick={() => open('inject')}><Icon name={killed ? 'refresh' : 'minus'} size={13}/><span><strong>{killed ? 'Reinject' : 'Uninject'}</strong><small>Live process state</small></span></button>
        </section>

        <button className="btn primary apply-btn" disabled={applying}
          onClick={() => flags.length ? open('apply') : notify('No flags to apply')}>
          {applying ? 'Applying…' : 'Apply Flags'}
        </button>
      </div>

      {/* ═══ MODALS ═══ */}

      {/* Add flag with live autocomplete & validation */}
      <Modal open={modal === 'add'} onClose={close} title="Add FastFlag" width="440px"
        footer={<>
          <button className="btn" onClick={close}>Cancel</button>
          <button className="btn primary" onClick={doAdd} disabled={!addName.trim()}>Add Flag</button>
        </>}>
        <div className="modal-field">
          <label className="label">Flag name</label>
          <div className="flag-autocomplete-wrap">
            <input className="input" placeholder="FFlagDebugGraphicsPreferD3D11"
              value={addName}
              onChange={e => {
                setAddName(e.target.value);
                setShowAddSuggestions(true);
                setAddError('');
              }}
              onFocus={() => {
                if (addName.trim()) setShowAddSuggestions(true);
              }}
              onKeyDown={e => {
                if (e.key === 'Enter') doAdd();
                if (e.key === 'Escape') setShowAddSuggestions(false);
              }}
              autoFocus />
            {showAddSuggestions && addName.trim().length > 0 && (
              <div className="flag-autocomplete-dropdown">
                {addSuggestions.length > 0 ? (
                  addSuggestions.map(flag => (
                    <button
                      key={flag.name}
                      type="button"
                      className="flag-autocomplete-item"
                      onMouseDown={e => { e.preventDefault(); selectAddSuggestion(flag); }}
                    >
                      <div className="flag-item-main">
                        <strong>{flag.name}</strong>
                        <span className="flag-type-badge">{flag.expected_type || 'flag'}</span>
                      </div>
                      <small className="flag-item-sub">{flag.prefix || 'Roblox'}</small>
                    </button>
                  ))
                ) : (
                  <div className="flag-autocomplete-empty">
                    <Icon name="x" size={12} />
                    <span>{addSearching ? 'Searching database…' : 'No matching FastFlags in database'}</span>
                  </div>
                )}
              </div>
            )}
          </div>
          {addError ? (
            <div className="modal-error-pill">
              <Icon name="alert" size={12} />
              <span>{addError}</span>
            </div>
          ) : (
            <span className="hint">Must exist in the Roblox FastFlag database (e.g. FFlag, DFInt, FInt, FString).</span>
          )}
        </div>
        <div className="modal-field">
          <div className="val-field-head">
            <label className="label">Value</label>
            <CustomSelect
              compact
              value={valMode}
              options={valTypeOptions}
              onChange={m => {
                setValMode(m);
                if (m === 'bool' && !['true', 'false'].includes(String(addVal).toLowerCase())) setAddVal('True');
                if (m === 'number' && isNaN(Number(addVal))) setAddVal('0');
                setAddError('');
              }}
            />
          </div>
          {effectiveType === 'bool' ? (
            <CustomSelect value={String(addVal).toLowerCase()==='false'?'False':'True'} options={BOOLEAN_OPTIONS} onChange={value=>{setAddVal(value);setAddError('')}} />
          ) : effectiveType === 'number' ? (
            <NumberInput
              value={addVal}
              placeholder="0"
              onChange={val => { setAddVal(val); setAddError(''); }}
              onKeyDown={e => e.key === 'Enter' && doAdd()}
            />
          ) : (
            <input
              type="text"
              className="input"
              placeholder="Value"
              value={addVal}
              onChange={e => { setAddVal(e.target.value); setAddError(''); }}
              onKeyDown={e => e.key === 'Enter' && doAdd()}
            />
          )}
        </div>
      </Modal>

      {/* Bulk Add FastFlags */}
      <Modal open={modal === 'bulk_add'} onClose={close} title="Bulk Add FastFlags" width="700px"
        footer={<>
          <button className="btn" onClick={close}>Cancel</button>
          <button
            className="btn primary"
            onClick={doBulkAdd}
            disabled={bulkTab === 'rows' ? !validBulkRowCount : !parsedBulkFlags.length}
          >
            Add {bulkTab === 'rows' ? (validBulkRowCount ? `${validBulkRowCount} flags` : 'flags') : (parsedBulkFlags.length ? `${parsedBulkFlags.length} flags` : 'flags')}
          </button>
        </>}>
        <div className="modal-tabs" style={{ marginBottom: 12 }}>
          <button className={`modal-tab${bulkTab === 'rows'  ? ' active' : ''}`} onClick={() => setBulkTab('rows')}>Single Rows</button>
          <button className={`modal-tab${bulkTab === 'paste' ? ' active' : ''}`} onClick={() => setBulkTab('paste')}>Paste JSON / List</button>
        </div>

        {bulkTab === 'rows' ? (
          <div>
            <div className="bulk-rows-list">
              {bulkRows.map((row, idx) => (
                <div className="bulk-row-item" key={row.id}>
                  <div className="bulk-name-wrap">
                    <input
                      className="input"
                      placeholder="FFlag / FString / DFInt name"
                      value={row.name}
                      onChange={e => { updateBulkRow(row.id, 'name', e.target.value); setBulkActiveRow(row.id); }}
                      onFocus={() => setBulkActiveRow(row.id)}
                      onKeyDown={e => e.key === 'Escape' && setBulkActiveRow(null)}
                      autoFocus={idx === bulkRows.length - 1}
                    />
                    {bulkActiveRow === row.id && row.name.trim() && (
                      <div className="bulk-suggestion-menu">
                        {bulkSuggestions.length ? bulkSuggestions.map(flag => (
                          <button type="button" key={flag.name} onMouseDown={e => { e.preventDefault(); selectBulkSuggestion(row, flag); }}>
                            <span><strong>{flag.name}</strong><small>{flag.expected_type || 'flag'}</small></span>
                            <em>{flag.prefix || 'Roblox'}</em>
                          </button>
                        )) : <div className="bulk-suggestion-empty">{bulkSearching ? 'Searching flags…' : 'No matching flags'}</div>}
                      </div>
                    )}
                  </div>
                  {row.type === 'bool' ? (
                    <CustomSelect compact value={String(row.value).toLowerCase()==='false'?'False':'True'} options={BOOLEAN_OPTIONS} onChange={value=>updateBulkRow(row.id,'value',value)} />
                  ) : row.type === 'number' ? (
                    <NumberInput
                      value={row.value}
                      placeholder="0"
                      onChange={v => updateBulkRow(row.id, 'value', v)}
                    />
                  ) : (
                    <input
                      className="input"
                      placeholder={row.type === 'string' ? 'Text / String' : 'Value'}
                      value={row.value}
                      onChange={e => updateBulkRow(row.id, 'value', e.target.value)}
                    />
                  )}
                  <CustomSelect
                    compact
                    className="bulk-type-select"
                    value={row.type || 'string'}
                    options={bulkTypeOptions}
                    onChange={t => {
                      updateBulkRow(row.id, 'type', t);
                      if (t === 'bool' && !['true', 'false'].includes(String(row.value).toLowerCase())) {
                        updateBulkRow(row.id, 'value', 'True');
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="btn-remove-bulk-row"
                    title="Remove row"
                    onClick={() => removeBulkRow(row.id)}
                  >
                    <Icon name="x" size={12} />
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              className="btn-add-row-transparent"
              onClick={addBulkRow}
            >
              <Icon name="plus" size={12} /> Add flag
            </button>
          </div>
        ) : (
          <div>
            <p className="modal-body-text" style={{ marginBottom: 8 }}>
              Paste multiple flags below as JSON, Bloxstrap format, or key-value pairs (e.g. <code>FFlagExample=True</code> or <code>FStringCustom=hello</code>):
            </p>
            <div className="bulk-code-toolbar"><span><Icon name="code" size={12}/> FastFlag JSON editor</span><div><button className="btn" type="button" onClick={pickBulkJson}><Icon name="folder" size={12}/> Pick JSON file</button><button className="btn" type="button" onClick={repairBulkJson} disabled={!bulkText.trim()}><Icon name="sparkles" size={12}/> Auto-fix JSON</button></div></div>
            <div className="bulk-code-editor">
              <div className="bulk-code-gutter">{Array.from({length:Math.max(1,bulkText.split(/\r?\n/).length)},(_,index)=><span key={index}>{index+1}</span>)}</div>
              <textarea
                ref={bulkEditorRef}
                className="bulk-textarea"
                spellCheck="false"
                placeholder={`{\n  "FFlagDebugCheck": true,\n  "DFIntTargetFps": 144,\n  "FStringCustomTitle": "MyString"\n}`}
                value={bulkText}
                onChange={e => setBulkText(e.target.value)}
                autoFocus
              />
              {(pasteSuggestions.length>0||pasteSearching)&&<div className="bulk-code-suggestions">{pasteSuggestions.map(flag=><button type="button" key={flag.name} onMouseDown={event=>{event.preventDefault();insertPasteSuggestion(flag)}}><Icon name="flag" size={12}/><span><strong>{flag.name}</strong><small>{flagDescription(flag)}</small></span><em>{flag.expected_type||'value'}</em></button>)}{pasteSearching&&!pasteSuggestions.length&&<div>Searching FastFlags…</div>}</div>}
            </div>
            <div className="bulk-stats-bar">
              <span className={`bulk-json-status ${bulkJsonStatus.kind}`}><Icon name={bulkJsonStatus.kind==='valid'?'check':bulkJsonStatus.kind==='error'?'alert':'info'} size={11}/>{bulkJsonStatus.message}</span>
              <span>Detected: <strong className="bulk-stats-badge">{parsedBulkFlags.length} valid flags</strong></span>
              <span style={{ fontSize: 10 }}>Duplicates will update existing values</span>
            </div>
          </div>
        )}
      </Modal>

      {/* Edit Single FastFlag */}
      <Modal open={modal === 'edit_flag'} onClose={close} title="Edit FastFlag" width="440px"
        footer={<>
          <button className="btn" onClick={close}>Cancel</button>
          <button className="btn primary" onClick={doSaveEditFlag} disabled={!editFlag.name.trim()}>
            Save Changes
          </button>
        </>}>
        <div className="modal-field">
          <label className="label">Flag name</label>
          <input
            className="input"
            value={editFlag.name}
            onChange={e => setEditFlag(cur => ({ ...cur, name: e.target.value }))}
          />
        </div>
        <div className="modal-field">
          <div className="val-field-head">
            <label className="label">Value</label>
            <CustomSelect
              compact
              value={editFlag.mode || 'auto'}
              options={[
                { value: 'auto', label: 'Auto detect' },
                { value: 'bool', label: 'Boolean (True / False)' },
                { value: 'number', label: 'Numerical (Number)' },
                { value: 'text', label: 'String (Text)' },
              ]}
              onChange={m => {
                setEditFlag(cur => ({
                  ...cur,
                  mode: m,
                  value: m === 'bool' && !['true', 'false'].includes(String(cur.value).toLowerCase()) ? 'True' :
                         m === 'number' && isNaN(Number(cur.value)) ? '0' : cur.value,
                }));
              }}
            />
          </div>
          {(editFlag.mode === 'bool' || (editFlag.mode === 'auto' && flagKind(editFlag.name, editFlag.value) === 'bool')) ? (
            <CustomSelect value={String(editFlag.value).toLowerCase()==='false'?'False':'True'} options={BOOLEAN_OPTIONS} onChange={value=>setEditFlag(cur=>({...cur,value}))} />
          ) : (editFlag.mode === 'number' || (editFlag.mode === 'auto' && (flagKind(editFlag.name, editFlag.value) === 'int' || flagKind(editFlag.name, editFlag.value) === 'float'))) ? (
            <NumberInput
              value={editFlag.value}
              onChange={val => setEditFlag(cur => ({ ...cur, value: val }))}
              onKeyDown={e => e.key === 'Enter' && doSaveEditFlag()}
            />
          ) : (
            <input
              type="text"
              className="input"
              placeholder="String / Text value"
              value={editFlag.value}
              onChange={e => setEditFlag(cur => ({ ...cur, value: e.target.value }))}
              onKeyDown={e => e.key === 'Enter' && doSaveEditFlag()}
            />
          )}
        </div>
      </Modal>

      {/* Pick flag to delete when none selected */}
      <Modal open={modal === 'pick_delete'} onClose={close} title="Delete FastFlag" width="440px"
        footer={<button className="btn" onClick={close}>Close</button>}>
        <p className="modal-body-text" style={{ marginBottom: 10 }}>
          Select a flag from your workspace to remove:
        </p>
        <div className="modal-field">
          <input className="input" placeholder="Search workspace flags to delete…"
            value={deleteFilter} onChange={e => setDeleteFilter(e.target.value)} autoFocus />
        </div>
        <div className="pick-delete-list">
          {filteredWorkspaceFlags.length ? filteredWorkspaceFlags.map(([name, val]) => (
            <div className="pick-delete-row" key={name}>
              <div className="pick-delete-info">
                <span className="pick-delete-name" title={name}>{name}</span>
                <span className="pick-delete-val">{val}</span>
              </div>
              <button className="btn danger" style={{ height: 26, fontSize: 11 }} onClick={() => doDeleteOne(name)}>
                <Icon name="trash" size={11} /> Delete
              </button>
            </div>
          )) : (
            <p className="modal-body-text" style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-3)' }}>
              {deleteFilter ? 'No matching flags in workspace.' : 'No flags configured in current workspace.'}
            </p>
          )}
        </div>
      </Modal>

      {/* Remove selected */}
      <Modal open={modal === 'remove'} onClose={close} title="Remove Selected" width="360px"
        footer={<>
          <button className="btn" onClick={close}>Cancel</button>
          <button className="btn danger" onClick={doRemove}>Remove {selected.size} flag{selected.size !== 1 ? 's' : ''}</button>
        </>}>
        <div className="modal-icon danger"><Icon name="trash" size={18} /></div>
        <p className="modal-body-text">
          Permanently remove <strong>{selected.size}</strong> selected flag{selected.size !== 1 ? 's' : ''}?
          This cannot be undone.
        </p>
      </Modal>

      {/* Clear all */}
      <Modal open={modal === 'clear'} onClose={close} title="Clear All Flags" width="360px" tone="danger"
        footer={<>
          <button className="btn" onClick={close}>Cancel</button>
          <button className="btn danger" onClick={doClear}>Clear All</button>
        </>}>
        <div className="modal-icon danger"><Icon name="trash" size={18} /></div>
        <p className="modal-body-text">
          Remove all <strong>{flags.length}</strong> configured flags? Your configuration will be empty.
          This cannot be undone.
        </p>
      </Modal>

      {/* Import */}
      <Modal open={modal === 'import'} onClose={close} title="Import Flags" width="460px"
        footer={impTab === 'file'
          ? <><button className="btn" onClick={close}>Cancel</button><button className="btn primary" onClick={doImportFile}>Choose File…</button></>
          : <><button className="btn" onClick={close}>Cancel</button><button className="btn primary" onClick={doImportText} disabled={!impText.trim()}>Import</button></>
        }>
        <div className="modal-tabs">
          <button className={`modal-tab${impTab === 'file'  ? ' active' : ''}`} onClick={() => setImpTab('file')}>From File</button>
          <button className={`modal-tab${impTab === 'paste' ? ' active' : ''}`} onClick={() => setImpTab('paste')}>Paste JSON</button>
        </div>
        {impTab === 'file'
          ? <p className="modal-body-text">
              Opens a file picker. Supports <strong>.json</strong> and <strong>.txt</strong> in any of these formats:<br />
              JSON list, Bloxstrap dict, or base64 preset.
            </p>
          : <div className="modal-field">
              <label className="label">Paste flag data</label>
              <textarea className="textarea" rows={6}
                placeholder={'[{"name": "FFlagExample", "value": "True"}]'}
                value={impText} onChange={e => setImpText(e.target.value)} />
              <span className="hint">Accepts JSON array, Bloxstrap dict, or base64 preset.</span>
            </div>
        }
      </Modal>

      {/* Export */}
      <Modal open={modal === 'export'} onClose={close} title="Export Flags" width="360px"
        footer={<>
          <button className="btn" onClick={close}>Cancel</button>
          <button className="btn primary" onClick={doExport}>Save File…</button>
        </>}>
        <p className="modal-body-text">
          Saves your <strong>{flags.length} flags</strong> to a .json file. Hotkey bindings are preserved.
          The file can be re-imported here or shared with others.
        </p>
      </Modal>

      {/* Launch */}
      <Modal open={modal === 'launch'} onClose={close} title="Launch Roblox" subtitle="Select an installed Roblox player or bootstrapper path" width="560px"
        footer={<>
          <button className="btn" onClick={close}>Cancel</button>
          <button className="btn primary" disabled={launchLoading || !launchTarget} onClick={doLaunch}><Icon name="play" size={12} /> Launch selected</button>
        </>}>
        <p className="modal-body-text">Your selected installation is remembered. Right-click <strong>Launch Roblox</strong> any time to select another one.</p>
        <div className="launch-target-list">
          {launchLoading ? <div className="launch-target-empty">Finding Roblox installations…</div> : launchTargets.map(target => (
            <button type="button" key={target.path} className={`launch-target${launchTarget === target.path ? ' selected' : ''}`} onClick={() => setLaunchTarget(target.path)}>
              <Icon name="play" size={15} />
              <span><strong>{target.launcher} · {target.name}</strong><small>{target.exe || target.path}</small></span>
              {launchTarget === target.path && <Icon name="check" size={15} />}
            </button>
          ))}
          {!launchLoading && !launchTargets.length && <div className="launch-target-empty">No Roblox player installations were found. Install or launch Roblox once, then try again.</div>}
        </div>
      </Modal>

      {/* Sync offsets — full rich modal */}
      <SyncModal open={modal === 'sync'} onClose={close} notify={notify} />

      {/* Upload offsets */}
      <Modal open={modal === 'upload'} onClose={close} title="Upload Offset File" width="400px"
        footer={<>
          <button className="btn" onClick={close}>Cancel</button>
          <button className="btn primary" onClick={doUpload}>Choose File…</button>
        </>}>
        <p className="modal-body-text">
          Select a <strong>.hpp</strong> or <strong>.h</strong> C++ header containing a FastFlag
          offset dump. This replaces the currently loaded offset data.
        </p>
      </Modal>

      {/* Uninject / Reinject */}
      <Modal open={modal === 'inject'} onClose={close}
        title={killed ? 'Reinject Flags' : 'Uninject Flags'} width="400px"
        footer={<>
          <button className="btn" onClick={close}>Cancel</button>
          <button className={`btn ${killed ? 'primary' : 'danger'}`} onClick={doInject}>
            {killed ? 'Reinject' : 'Uninject'}
          </button>
        </>}>
        <div className={`modal-icon ${killed ? 'warning' : 'danger'}`}>
          <Icon name={killed ? 'refresh' : 'x'} size={18} />
        </div>
        <p className="modal-body-text">
          {killed
            ? 'Re-enables your flags and reapplies them to live Roblox memory. The auto-apply watchdog will resume monitoring.'
            : 'Disables all active flags, reverts live memory patches, and clears ClientAppSettings.json. Your flags remain saved and can be reinjected at any time.'}
        </p>
      </Modal>

      {/* Apply */}
      <Modal open={modal === 'apply'} onClose={close} title="Apply Flags" width="360px"
        footer={<>
          <button className="btn" onClick={close}>Cancel</button>
          <button className="btn primary" onClick={doApply}>Apply {flags.length} flags</button>
        </>}>
        <div className="modal-icon warning"><Icon name="layers" size={18} /></div>
        <p className="modal-body-text">
          Writes <strong>{flags.length} flag{flags.length !== 1 ? 's' : ''}</strong> to
          ClientAppSettings.json and patches live Roblox process memory if a session is attached.
        </p>
      </Modal>

      {/* Operation Progress Modal */}
      <OperationProgressModal
        open={opState.open}
        title={opState.title}
        subtitle={opState.subtitle}
        steps={opState.steps}
      />
    </div>
  );
}
