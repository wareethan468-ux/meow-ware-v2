import { useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from './Icons';

export default function CustomSelect({
  value,
  options,
  onChange,
  label = 'Select option',
  searchable = false,
  searchPlaceholder = 'Search options...',
  disabled = false,
  compact = false,
  className = '',
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [dropUp, setDropUp] = useState(false);
  const rootRef = useRef(null);
  const selected = options.find((option) => option.value === value);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return options;
    return options.filter((option) => `${option.label} ${option.detail || ''}`.toLowerCase().includes(needle));
  }, [options, query]);

  useEffect(() => {
    const close = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, []);

  const handleToggle = () => {
    if (disabled) return;
    if (!open && rootRef.current) {
      const rect = rootRef.current.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      setDropUp(spaceBelow < 210 && rect.top > 210);
    }
    setOpen((current) => !current);
  };

  const choose = (nextValue) => {
    onChange(nextValue);
    setOpen(false);
    setQuery('');
  };

  return (
    <div className={`custom-select${open ? ' open' : ''}${dropUp ? ' drop-up' : ''}${compact ? ' compact' : ''}${disabled ? ' disabled' : ''} ${className}`} ref={rootRef}>
      <button type="button" className="custom-select-trigger" onClick={handleToggle} aria-haspopup="listbox" aria-expanded={open} disabled={disabled}>
        <span><strong>{selected?.label || label}</strong>{selected?.detail && <small>{selected.detail}</small>}</span>
        <Icon name="chevron" size={compact ? 12 : 14} />
      </button>
        <div className={`custom-select-menu${open ? ' is-visible' : ''}`} aria-hidden={!open}>
          {searchable && <div className="custom-select-search"><Icon name="search" size={14} /><input autoFocus={open} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={searchPlaceholder} /></div>}
          <div className="custom-select-options" role="listbox">
            {filtered.map((option) => (
              <button
                type="button"
                role="option"
                aria-selected={option.value === value}
                className={option.value === value ? 'selected' : ''}
                key={option.value}
                onClick={() => choose(option.value)}
              >
                <span><strong>{option.label}</strong>{option.detail && <small>{option.detail}</small>}</span>
                {option.value === value && <Icon name="check" size={14} className="select-check" />}
              </button>
            ))}
            {!filtered.length && <div className="custom-select-empty">No options</div>}
          </div>
        </div>
    </div>
  );
}
