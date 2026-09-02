import { useEffect, useState } from 'react';
import { Icon } from '../components/Icons';
import Modal from '../components/Modal';
import CustomSelect from '../components/CustomSelect';
import OperationProgressModal from '../components/OperationProgressModal';
import { callDesktop, hasDesktopApi } from '../lib/desktopApi';
const BOOLEAN_OPTIONS = [{ value: 'True', label: 'True' }, { value: 'False', label: 'False' }];

const PRESET_COLORS = [
  '#a855f7', // Purple
  '#ec4899', // Pink
  '#3b82f6', // Blue
  '#10b981', // Emerald
  '#f59e0b', // Amber
  '#ef4444', // Red
  '#06b6d4', // Cyan
  '#8b5cf6', // Indigo
];

function parseFlagsFromPayload(text) {
  if (!text || !text.trim()) return [];
  const trimmed = text.trim();
  const results = [];

  // Try JSON parsing
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) {
      parsed.forEach(item => {
        if (typeof item === 'object' && item && item.name) {
          results.push({
            name: String(item.name).trim(),
            value: String(item.value ?? 'True'),
            type: item.type || 'string',
            enabled: item.enabled !== false,
          });
        }
      });
      if (results.length) return results;
    } else if (typeof parsed === 'object' && parsed !== null) {
      Object.entries(parsed).forEach(([key, val]) => {
        if (key && !key.startsWith('_')) {
          results.push({
            name: String(key).trim(),
            value: String(val),
            type: typeof val === 'boolean' ? 'bool' : typeof val === 'number' ? 'int' : 'string',
            enabled: true,
          });
        }
      });
      if (results.length) return results;
    }
  } catch {}

  // Try line-by-line parsing (key=value, key:value, key value)
  const lines = trimmed.split(/\r?\n/);
  for (const line of lines) {
    const clean = line.trim();
    if (!clean || clean.startsWith('#') || clean.startsWith('//')) continue;
    const match = clean.match(/^([A-Za-z0-9_]+)\s*[:=]\s*(.+)$/) || clean.match(/^([A-Za-z0-9_]+)\s+([^\s]+)$/);
    if (match) {
      results.push({
        name: match[1].trim(),
        value: match[2].trim(),
        type: 'string',
        enabled: true,
      });
    }
  }
  return results;
}

export default function PresetsView({ refreshFlags, notify }) {
  const [presets, setPresets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState('All');

  // Modal State
  const [modalOpen, setModalOpen] = useState(false);
  const [editingPresetId, setEditingPresetId] = useState(null);
  const [presetName, setPresetName] = useState('');
  const [presetCategory, setPresetCategory] = useState('RIVALS');
  const [presetColor, setPresetColor] = useState('#ef4444');
  const [presetTab, setPresetTab] = useState('rows'); // 'rows' | 'paste'
  const [presetRows, setPresetRows] = useState([{ id: 1, name: '', value: '', type: 'string' }]);
  const [presetText, setPresetText] = useState('');

  // Delete Confirm Modal
  const [deleteTarget, setDeleteTarget] = useState(null);

  // Operation Progress State
  const [opState, setOpState] = useState({
    open: false,
    title: '',
    subtitle: '',
    steps: [],
  });

  const loadPresets = async () => {
    setLoading(true);
    try {
      const data = await callDesktop('get_presets');
      if (Array.isArray(data)) {
        setPresets(data);
      }
    } catch {}
    setLoading(false);
  };

  useEffect(() => {
    loadPresets();
  }, []);

  const openCreateModal = () => {
    setEditingPresetId(null);
    setPresetName('');
    setPresetCategory(activeCategory !== 'All' ? activeCategory : 'RIVALS');
    setPresetColor(activeCategory === 'RIVALS' ? '#ef4444' : PRESET_COLORS[Math.floor(Math.random() * PRESET_COLORS.length)]);
    setPresetTab('rows');
    setPresetRows([{ id: 1, name: '', value: '', type: 'string' }]);
    setPresetText('');
    setModalOpen(true);
  };

  const openEditModal = (preset) => {
    setEditingPresetId(preset.id);
    setPresetName(preset.name || '');
    setPresetCategory(preset.category || 'Other');
    setPresetColor(preset.color || '#a855f7');
    setPresetTab('rows');
    const flags = preset.flags || [];
    if (Array.isArray(flags) && flags.length > 0) {
      setPresetRows(flags.map((f, i) => ({
        id: i + 1,
        name: f.name || '',
        value: String(f.value ?? ''),
        type: f.type || 'string',
      })));
      setPresetText(JSON.stringify(
        flags.reduce((acc, f) => { acc[f.name] = f.value; return acc; }, {}),
        null,
        2
      ));
    } else {
      setPresetRows([{ id: 1, name: '', value: '', type: 'string' }]);
      setPresetText('');
    }
    setModalOpen(true);
  };

  const addPresetRow = () => {
    setPresetRows(cur => [...cur, { id: Date.now() + Math.random(), name: '', value: '', type: 'string' }]);
  };

  const removePresetRow = (id) => {
    setPresetRows(cur => cur.length > 1 ? cur.filter(r => r.id !== id) : [{ id: 1, name: '', value: '', type: 'string' }]);
  };

  const updatePresetRow = (id, field, val) => {
    setPresetRows(cur => cur.map(r => r.id === id ? { ...r, [field]: val } : r));
  };

  const saveCurrentWorkspaceAsPreset = async () => {
    const defaultName = `Workspace Preset (${new Date().toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })})`;
    const res = await callDesktop('import_preset_from_config', defaultName, '#a855f7', activeCategory !== 'All' ? activeCategory : 'Other');
    if (res?.ok) {
      notify(`Saved workspace as "${defaultName}"`);
      await loadPresets();
    } else {
      notify(res?.error || 'Failed to save workspace preset');
    }
  };

  const handleImportFile = async () => {
    const res = await callDesktop('import_preset_from_file');
    if (res?.ok) {
      notify(`Imported preset "${res.preset?.name || 'File'}"`);
      await loadPresets();
    } else if (res?.error && res.error !== 'Cancelled') {
      notify(res.error || 'Failed to import preset file');
    }
  };

  const handleSavePresetModal = async () => {
    const trimmedName = presetName.trim();
    if (!trimmedName) return notify('Please enter a preset name');

    let flags = [];
    if (presetTab === 'rows') {
      flags = presetRows
        .filter(r => r.name.trim())
        .map(r => ({
          name: r.name.trim(),
          value: r.value.trim(),
          type: r.type === 'auto' ? 'string' : r.type,
          enabled: true,
        }));
    } else {
      flags = parseFlagsFromPayload(presetText);
    }

    if (!flags.length) {
      return notify('Please add at least one FastFlag to this preset');
    }

    const cat = presetCategory.trim() || 'Other';

    if (editingPresetId) {
      const res = await callDesktop('update_custom_preset', editingPresetId, trimmedName, flags, presetColor, cat);
      if (res?.ok === false) return notify(res.error || 'Could not update preset');
      notify(`Updated preset "${trimmedName}" (${cat})`);
    } else {
      const res = await callDesktop('create_custom_preset', trimmedName, flags, presetColor, cat);
      if (res?.ok === false) return notify(res.error || 'Could not create preset');
      notify(`Created preset "${trimmedName}" (${cat}) with ${flags.length} flags`);
    }

    setModalOpen(false);
    await loadPresets();
  };

  const handleApplyPreset = async (preset) => {
    setOpState({
      open: true,
      title: `Applying ${preset.name}`,
      subtitle: `Switching active flags to preset bundle (${preset.flags?.length || 0} flags)`,
      steps: [
        'Reverting unshared active memory flags...',
        'Staging ClientAppSettings.json...',
        'Writing preset FastFlags to memory...',
        'Syncing active workspace...',
      ],
    });

    try {
      const res = await callDesktop('apply_preset', preset.id);
      await new Promise(r => setTimeout(r, 600));
      if (res?.ok === false) {
        notify(res.error || 'Failed to apply preset');
      } else {
        notify(`Applied preset "${preset.name}" (${preset.flags?.length || 0} flags)`);
        await refreshFlags();
      }
    } catch (e) {
      notify(`Apply error: ${e}`);
    } finally {
      setOpState(cur => ({ ...cur, open: false }));
    }
  };

  const handleMergePreset = async (preset) => {
    const res = await callDesktop('merge_preset', preset.id);
    if (res?.ok) {
      notify(`Merged preset "${preset.name}" (+${res.added || 0} added)`);
      await refreshFlags();
    } else {
      notify(res?.error || 'Merge failed');
    }
  };

  const handleExportPreset = async (preset) => {
    const res = await callDesktop('export_preset_to_file', preset.name, 'json-with-binds');
    if (res?.ok) {
      notify(`Exported preset "${preset.name}"`);
    } else if (res?.error && res.error !== 'cancelled') {
      notify(res.error || 'Export failed');
    }
  };

  const handleDeletePreset = async (preset) => {
    const res = await callDesktop('delete_preset', preset.id);
    if (res) {
      notify(`Deleted preset "${preset.name}"`);
      await loadPresets();
    }
    setDeleteTarget(null);
  };

  const parsedFlagsCount = parseFlagsFromPayload(presetText).length;

  const categories = ['All', 'RIVALS', 'Other'];
  const visiblePresets = presets.filter(p => {
    if (activeCategory === 'All') return true;
    return (p.category || 'Other').toUpperCase() === activeCategory.toUpperCase();
  });

  return (
    <div className="presets-view view">
      <div className="presets-container">
        {/* View Header */}
        <div className="presets-header-bar">
          <div>
            <div className="view-title" style={{ marginBottom: 4 }}>FastFlag Presets</div>
            <div className="view-sub" style={{ marginBottom: 0 }}>Save, customize, and switch flag configuration bundles</div>
          </div>
          <div className="presets-top-actions">
            <button className="btn" onClick={saveCurrentWorkspaceAsPreset} title="Save loaded flags as a new preset">
              <Icon name="save" size={13} /> Save Workspace
            </button>
            <button className="btn" onClick={handleImportFile} title="Import .json or .txt preset file">
              <Icon name="import" size={13} /> Import File
            </button>
            <button className="btn primary" onClick={openCreateModal}>
              <Icon name="plus" size={13} /> + Create Preset
            </button>
          </div>
        </div>

        {/* Category Tabs */}
        <div className="presets-category-tabs">
          {categories.map(cat => {
            const count = cat === 'All'
              ? presets.length
              : presets.filter(p => (p.category || 'Other').toUpperCase() === cat.toUpperCase()).length;
            return (
              <button
                key={cat}
                type="button"
                className={`preset-cat-tab ${activeCategory.toUpperCase() === cat.toUpperCase() ? 'active' : ''}`}
                onClick={() => setActiveCategory(cat)}
              >
                <span>{cat}</span>
                <span className="cat-count">{count}</span>
              </button>
            );
          })}
        </div>

        {/* Presets List */}
        {loading ? (
          <div className="presets-loading">Loading presets...</div>
        ) : visiblePresets.length === 0 ? (
          <div className="presets-empty-card">
            <Icon name="presets" size={32} />
            <strong>No {activeCategory !== 'All' ? activeCategory : ''} presets found</strong>
            <p>Create a custom preset bundle, save your active workspace, or import a JSON preset to get started.</p>
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button className="btn" onClick={saveCurrentWorkspaceAsPreset}>Save Workspace</button>
              <button className="btn primary" onClick={openCreateModal}>+ Create Custom Preset</button>
            </div>
          </div>
        ) : (
          <div className="presets-grid">
            {visiblePresets.map((preset) => {
              const flags = preset.flags || [];
              const color = preset.color || '#a855f7';
              const cat = preset.category || 'Other';
              return (
                <div className="custom-preset-card" key={preset.id} style={{'--preset-color':color}}>
                  <div className="preset-card-top">
                    <div className="preset-title-wrap">
                      <span className="preset-color-dot" style={{ backgroundColor: color, boxShadow: `0 0 8px ${color}66` }} />
                      <strong className="preset-title-text">{preset.name}</strong>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span className={`preset-category-tag ${cat.toUpperCase() === 'RIVALS' ? 'rivals' : ''}`}>{cat}</span>
                      <span className="preset-badge">{flags.length} {flags.length === 1 ? 'flag' : 'flags'}</span>
                    </div>
                  </div>

                  {/* Flag chips preview */}
                  <div className="preset-flags-chips">
                    {flags.slice(0, 5).map((f, idx) => (
                      <span className="preset-flag-chip" key={idx} title={`${f.name} = ${f.value}`}>
                        <span className="chip-name">{f.name}</span>
                        <span className="chip-val">{String(f.value)}</span>
                      </span>
                    ))}
                    {flags.length > 5 && (
                      <span className="preset-flag-chip-more">+{flags.length - 5} more</span>
                    )}
                  </div>

                  {/* Action buttons */}
                  <div className="preset-card-footer">
                    <div className="preset-actions-left">
                      <button
                        className="btn primary btn-apply-preset action-success"
                        onClick={() => handleApplyPreset(preset)}
                      >
                        Apply Preset
                      </button>
                      <button
                        className="btn btn-subtle-preset preset-hover-label"
                        title="Edit preset flags and settings"
                        onClick={() => openEditModal(preset)}
                      >
                        <Icon name="edit" size={12} /><span>Edit</span>
                      </button>
                      <button
                        className="btn btn-subtle-preset preset-hover-label"
                        title="Merge preset flags into active workspace"
                        onClick={() => handleMergePreset(preset)}
                      >
                        <Icon name="branch" size={12} /><span>Merge</span>
                      </button>
                    </div>
                    <div className="preset-actions-right">
                      <button
                        className="btn-icon-preset"
                        title="Export preset to JSON file"
                        onClick={() => handleExportPreset(preset)}
                      >
                        <Icon name="export" size={13} /><span>Export</span>
                      </button>
                      <button
                        className="btn-icon-preset danger"
                        title="Delete preset"
                        onClick={() => setDeleteTarget(preset)}
                      >
                        <Icon name="trash" size={13} /><span>Delete</span>
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Preset Create / Edit Modal */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editingPresetId ? 'Edit FastFlag Preset' : 'Create Custom FastFlag Preset'}
        width="560px"
        footer={<>
          <button className="btn" onClick={() => setModalOpen(false)}>Cancel</button>
          <button className="btn primary" onClick={handleSavePresetModal}>
            {editingPresetId ? 'Save Changes' : 'Create Preset'}
          </button>
        </>}
      >
        <div className="modal-field">
          <label className="label">Preset Name</label>
          <input
            className="input"
            placeholder="e.g. Blurry Textures, Competitive FPS Boost..."
            value={presetName}
            onChange={e => setPresetName(e.target.value)}
            autoFocus
          />
        </div>

        <div className="modal-field">
          <label className="label">Category</label>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {['RIVALS', 'Other'].map(c => (
              <button
                key={c}
                type="button"
                className={`btn ${presetCategory === c ? 'primary' : ''}`}
                style={{ height: 28, fontSize: 11, padding: '0 12px', borderRadius: 9999 }}
                onClick={() => setPresetCategory(c)}
              >
                {c}
              </button>
            ))}
            <input
              className="input"
              style={{ flex: 1, height: 28, fontSize: 11 }}
              placeholder="Or enter custom category..."
              value={presetCategory}
              onChange={e => setPresetCategory(e.target.value)}
            />
          </div>
        </div>

        <div className="modal-field">
          <label className="label">Accent Color</label>
          <div className="preset-color-picker">
            {PRESET_COLORS.map(c => (
              <button
                key={c}
                type="button"
                className={`preset-color-swatch ${presetColor === c ? 'active' : ''}`}
                style={{ backgroundColor: c }}
                onClick={() => setPresetColor(c)}
              />
            ))}
          </div>
        </div>

        <div className="modal-tabs" style={{ marginBottom: 12 }}>
          <button
            className={`modal-tab ${presetTab === 'rows' ? 'active' : ''}`}
            onClick={() => setPresetTab('rows')}
          >
            Single Rows
          </button>
          <button
            className={`modal-tab ${presetTab === 'paste' ? 'active' : ''}`}
            onClick={() => setPresetTab('paste')}
          >
            Paste JSON / Bloxstrap
          </button>
        </div>

        {presetTab === 'rows' ? (
          <div>
            <div className="bulk-rows-list">
              {presetRows.map((row, idx) => (
                <div className="bulk-row-item" key={row.id}>
                  <input
                    className="input"
                    placeholder="FFlag / FString / DFInt name"
                    value={row.name}
                    onChange={e => updatePresetRow(row.id, 'name', e.target.value)}
                    autoFocus={idx === presetRows.length - 1}
                  />
                  {row.type === 'bool' ? (
                    <CustomSelect compact value={String(row.value).toLowerCase()==='false'?'False':'True'} options={BOOLEAN_OPTIONS} onChange={value=>updatePresetRow(row.id,'value',value)} />
                  ) : (
                    <input
                      className="input"
                      placeholder={row.type === 'number' ? '120' : 'Text / String'}
                      value={row.value}
                      onChange={e => updatePresetRow(row.id, 'value', e.target.value)}
                    />
                  )}
                  <select
                    className="type-select-dropdown"
                    value={row.type || 'string'}
                    onChange={e => {
                      const t = e.target.value;
                      updatePresetRow(row.id, 'type', t);
                      if (t === 'bool' && !['true', 'false'].includes(String(row.value).toLowerCase())) {
                        updatePresetRow(row.id, 'value', 'True');
                      }
                    }}
                  >
                    <option value="string">String</option>
                    <option value="number">Number</option>
                    <option value="bool">Bool</option>
                    <option value="auto">Auto</option>
                  </select>
                  <button
                    type="button"
                    className="btn-remove-bulk-row"
                    title="Remove row"
                    onClick={() => removePresetRow(row.id)}
                  >
                    <Icon name="x" size={12} />
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              className="btn-add-row-transparent"
              onClick={addPresetRow}
            >
              <Icon name="plus" size={12} /> Add flag
            </button>
          </div>
        ) : (
          <div>
            <p className="modal-body-text" style={{ marginBottom: 8 }}>
              Paste JSON or key=value flags to bundle into this preset:
            </p>
            <textarea
              className="bulk-textarea"
              placeholder={`{\n  "FFlagDebugCheck": "True",\n  "DFIntTargetFps": "144"\n}`}
              value={presetText}
              onChange={e => setPresetText(e.target.value)}
              autoFocus
            />
            <div className="bulk-stats-bar">
              <span>Detected: <strong className="bulk-stats-badge">{parsedFlagsCount} valid flags</strong></span>
            </div>
          </div>
        )}
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        title="Delete FastFlag Preset"
        tone="danger"
        width="380px"
        footer={<>
          <button className="btn" onClick={() => setDeleteTarget(null)}>Cancel</button>
          <button className="btn danger" onClick={() => handleDeletePreset(deleteTarget)}>Delete Preset</button>
        </>}
      >
        <div className="modal-icon danger"><Icon name="trash" size={18} /></div>
        <p className="modal-body-text">
          Are you sure you want to delete preset <strong>"{deleteTarget?.name}"</strong>?
          This cannot be undone.
        </p>
      </Modal>

      {/* Operation Loading Modal */}
      <OperationProgressModal
        open={opState.open}
        title={opState.title}
        subtitle={opState.subtitle}
        steps={opState.steps}
      />
    </div>
  );
}
