import { useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from './Icons';
import CustomScrollbar from './CustomScrollbar';

const menus = {
  injector: [
    ['flags', 'layers', 'Flags', 'Configure and apply FastFlags'],
    ['presets', 'list', 'Presets', 'Open saved flag configurations'],
    ['monitor', 'activity', 'Roblox Monitor', 'View live CPU, memory, and offsets'],
    ['database', 'database', 'Flag Database', 'Edit flag nicknames and descriptions'],
    ['builds', 'download', 'Roblox Builds', 'Manage downloaded client versions'],
    ['console', 'terminal', 'Console', 'Inspect runtime output'],
    ['offsets', 'refresh', 'Offsets', 'Manage Roblox offset sources'],
    ['sources', 'copy', 'Sources', 'Configure data sources'],
    ['themes', 'brush', 'Themes', 'Customize the interface'],
    ['settings', 'settings', 'Settings', 'Change app preferences'],
    ['about', 'info', 'About Vellium', 'Build and platform information'],
  ],
  proxy: [
    ['assetProxy', 'route', 'Replacements', 'Manage asset replacement profiles'],
    ['scraper', 'database', 'Asset Scraper', 'Browse captured Roblox assets'],
    ['proxyTraffic', 'activity', 'Proxy Traffic', 'Inspect preserved requests'],
    ['proxyThemes', 'brush', 'Themes', 'Customize the interface'],
    ['proxySettings', 'settings', 'Proxy Settings', 'Configure the proxy runtime'],
    ['about', 'info', 'About Vellium', 'Build and platform information'],
  ],
  bootstrapper: [
    ['bootstrapper', 'rocket', 'Launcher', 'Launch Roblox with flags applied'],
    ['flags', 'layers', 'Flags', 'Configure the FastFlags applied on launch'],
    ['builds', 'download', 'Roblox Builds', 'Manage downloaded client versions'],
    ['console', 'terminal', 'Console', 'Inspect runtime output'],
    ['themes', 'brush', 'Themes', 'Customize the interface'],
    ['settings', 'settings', 'Settings', 'Change app preferences'],
    ['about', 'info', 'About Vellium', 'Build and platform information'],
  ],
  optimizer: [
    ['optimizer', 'gauge', 'PC Optimizer', 'Tune Windows with reversible gaming profiles'],
    ['monitor', 'activity', 'System Monitor', 'View live process performance'],
    ['themes', 'brush', 'Themes', 'Customize the interface'],
    ['settings', 'settings', 'Settings', 'Change app preferences'],
    ['about', 'info', 'About Vellium', 'Build and platform information'],
  ],
};

// FastFlag actions surfaced in the palette. Each id maps 1:1 to a FlagsView action
// (routed through App → the `vellium:flags-action` handler), mirroring the sidebar buttons.
const flagActions = [
  ['apply', 'bolt', 'Apply FastFlags', 'Inject the current flags into Roblox'],
  ['add', 'plus', 'Add flag', 'Create a FastFlag manually'],
  ['bulk_add', 'list', 'Bulk add flags', 'Paste multiple flags at once'],
  ['remove', 'trash', 'Remove flags', 'Delete selected flags, or pick some'],
  ['clear', 'trash', 'Clear configuration', 'Remove every flag from the workspace'],
  ['import', 'download', 'Import flags', 'Load flags from JSON or text'],
  ['export', 'upload', 'Export flags', 'Save the configuration to a file'],
  ['sync', 'refresh', 'Sync offsets', 'Update flag definitions'],
  ['launch', 'play', 'Launch Roblox', 'Start Roblox with flags applied'],
  ['inject', 'minus', 'Uninject / Reinject', 'Toggle the live process state'],
];

const products = [
  ['injector', 'layers', 'FastFlag Injector'],
  ['proxy', 'route', 'Plex Proxy'],
  ['bootstrapper', 'rocket', 'Plex Bootstrapper'],
  ['optimizer', 'gauge', 'Plex Optimizer'],
];

export default function CommandPalette({ open, onClose, product, onNavigate, onProductChange, onRunAction, capabilities }) {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  // Keep the palette mounted through its exit animation so closing is smooth (DESIGN_GUIDE.md).
  const [render, setRender] = useState(open);
  const [closing, setClosing] = useState(false);
  const inputRef = useRef(null);
  const reduceMotion = typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  const commands = useMemo(() => {
    const navigation = (menus[product] || []).map(([id, icon, label, detail]) => ({
      id: `go-${id}`, icon, label, detail, group: 'Go to', run: () => onNavigate(id),
    }));
    const actions = product === 'injector' ? flagActions.map(([id, icon, label, detail]) => ({
      id: `action-${id}`, icon, label, detail, group: 'Actions', run: () => onRunAction?.(id),
    })) : [];
    const switching = products.filter(([id]) => id !== product).map(([id, icon, label]) => ({
      id: `switch-${id}`, icon, label: `Switch to ${label}`,
      detail: capabilities[id] === false ? 'Only available on Windows' : 'Change Plex workspace',
      group: 'Switch product', disabled: capabilities[id] === false,
      run: () => onProductChange(id),
    }));
    return [...navigation, ...actions, ...switching];
  }, [product, capabilities, onNavigate, onProductChange, onRunAction]);
  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return term ? commands.filter(item => `${item.label} ${item.detail} ${item.group}`.toLowerCase().includes(term)) : commands;
  }, [commands, query]);

  // Drive the mount lifecycle: mount on open, keep mounted briefly while the exit animation runs.
  useEffect(() => {
    if (open) { setRender(true); setClosing(false); return undefined; }
    if (!render) return undefined;
    setClosing(true);
    const timer = setTimeout(() => { setRender(false); setClosing(false); }, reduceMotion ? 0 : 210);
    return () => clearTimeout(timer);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return;
    setQuery(''); setSelected(0);
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);
  useEffect(() => setSelected(index => Math.min(index, Math.max(filtered.length - 1, 0))), [filtered.length]);

  if (!render) return null;
  const choose = item => { if (!item || item.disabled) return; item.run(); onClose(); };
  let lastGroup = '';
  return <div className={`command-palette-overlay${closing ? ' is-closing' : ''}`} role="presentation" onMouseDown={event => event.target === event.currentTarget && onClose()}>
    <section className={`command-palette${closing ? ' is-closing' : ''}`} role="dialog" aria-modal="true" aria-label="Command menu">
      <label className="command-search">
        <Icon name="search" size={17}/>
        <input ref={inputRef} value={query} onChange={event => { setQuery(event.target.value); setSelected(0); }}
          onKeyDown={event => {
            if (event.key === 'Escape') onClose();
            if (event.key === 'ArrowDown') { event.preventDefault(); setSelected(value => Math.min(value + 1, filtered.length - 1)); }
            if (event.key === 'ArrowUp') { event.preventDefault(); setSelected(value => Math.max(value - 1, 0)); }
            if (event.key === 'Enter') { event.preventDefault(); choose(filtered[selected]); }
          }} placeholder="Search menus and commands…" aria-label="Search commands"/>
        <kbd>ESC</kbd>
      </label>
      <CustomScrollbar className="command-results">
        {filtered.length ? filtered.map((item, index) => {
          const heading = item.group !== lastGroup; lastGroup = item.group;
          return <div key={item.id}>
            {heading && <div className="command-group-label">{item.group}</div>}
            <button className={`command-item${index === selected ? ' selected' : ''}`} disabled={item.disabled}
              onMouseEnter={() => setSelected(index)} onClick={() => choose(item)}>
              <span className="command-item-icon"><Icon name={item.icon} size={16}/></span>
              <span><strong>{item.label}</strong><small>{item.detail}</small></span>
              {index === selected && !item.disabled && <kbd>ENTER</kbd>}
            </button>
          </div>;
        }) : <div className="command-empty"><Icon name="search" size={20}/><strong>No matching commands</strong><span>Try searching for a menu name.</span></div>}
      </CustomScrollbar>
      <footer className="command-footer"><span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span><span><kbd>↵</kbd> Open</span><span><kbd>ESC</kbd> Close</span></footer>
    </section>
  </div>;
}
