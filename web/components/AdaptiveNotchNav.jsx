import { useEffect, useRef, useState } from 'react';
import { Icon } from './Icons';
import AttachmentStatus from './AttachmentStatus';

const items = [
  ['flags', 'layers', 'FastFlags'],
  ['presets', 'list', 'Presets'],
  ['console', 'terminal', 'Console'],
  ['settings', 'settings', 'Settings'],
  ['offsets', 'refresh', 'Offsets'],
  ['sources', 'copy', 'Flags.hpp'],
  ['themes', 'brush', 'Themes'],
];

export default function AdaptiveNotchNav({ activeView, onChange, terminalOpen, onToggleTerminal }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const active = items.find(([id]) => id === activeView) || items[0];

  useEffect(() => {
    const close = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const select = (id) => {
    onChange(id);
    setOpen(false);
  };

  return (
    <div className="top-notch-band" ref={rootRef}>
      <nav className="adaptive-notch-nav" aria-label="Main navigation">
        <div className="notch-desktop-tabs" role="tablist" aria-orientation="horizontal">
          {items.map(([id, icon, label]) => (
            <button
              key={id}
              role="tab"
              aria-selected={activeView === id}
              className={activeView === id ? 'active' : ''}
              onClick={() => select(id)}
            >
              {activeView === id && <span className="notch-active-pill" />}
              <span className="notch-item-content"><Icon name={icon} size={15} />{label}</span>
            </button>
          ))}
        </div>

        <div className="nav-attachment">
          <AttachmentStatus />
        </div>
        <button className={`nav-terminal-toggle${terminalOpen ? ' active' : ''}`} onClick={onToggleTerminal} title="Toggle terminal" aria-pressed={terminalOpen}>
          <Icon name="terminal" size={14} />
        </button>

        <button className="notch-mobile-trigger" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-haspopup="listbox">
          <Icon name={active[1]} size={15} />
          <span>{active[2]}</span>
          <Icon name="chevron" size={14} className={open ? 'open' : ''} />
        </button>

        <div className={`notch-dropdown${open ? ' open' : ''}`} role="listbox" aria-label="Navigation options">
          {items.map(([id, icon, label]) => (
            <button key={id} role="option" aria-selected={activeView === id} className={activeView === id ? 'active' : ''} onClick={() => select(id)}>
              <span><Icon name={icon} size={15} />{label}</span>
              {activeView === id && <Icon name="check" size={14} className="notch-check" />}
            </button>
          ))}
        </div>
      </nav>
    </div>
  );
}
