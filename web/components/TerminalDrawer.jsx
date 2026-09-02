import { useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from './Icons';
import { callDesktop, hasDesktopApi } from '../lib/desktopApi';

export default function TerminalDrawer({ open, onClose }) {
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState('');
  const [logs, setLogs] = useState([]);
  const [attached, setAttached] = useState(false);
  const cursor = useRef({ index: 0, epoch: 0 });
  const outputRef = useRef(null);

  useEffect(() => {
    if (!open || !hasDesktopApi()) return undefined;
    let active = true;
    const poll = async () => {
      const [result, status] = await Promise.all([
        callDesktop('get_logs', cursor.current.index, cursor.current.epoch),
        callDesktop('get_attachment_targets'),
      ]);
      if (!active) return;
      if (status) setAttached(Boolean(status.attached));
      if (result?.logs?.length) {
        setLogs((current) => {
          const next = current.slice(-600);
          result.logs.forEach((entry) => entry.replace && next.length ? next.splice(-1, 1, entry.msg) : next.push(entry.msg));
          return next;
        });
      }
      if (result) cursor.current = { index: result.total ?? cursor.current.index, epoch: result.tail_epoch ?? cursor.current.epoch };
    };
    poll();
    const timer = window.setInterval(poll, 900);
    return () => { active = false; window.clearInterval(timer); };
  }, [open]);

  const visibleLogs = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? logs.filter((line) => line.toLowerCase().includes(needle)) : logs;
  }, [logs, query]);

  useEffect(() => {
    if (!collapsed && outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [visibleLogs, collapsed]);

  const clear = async () => {
    const result = await callDesktop('clear_logs');
    setLogs([]);
    if (result) cursor.current = { index: result.total ?? 0, epoch: result.tail_epoch ?? 0 };
  };

  if (!open) return null;
  return (
    <section className={`terminal-drawer${collapsed ? ' collapsed' : ''}`} aria-label="Toggle terminal">
      <header className="terminal-drawer-head">
        <strong><Icon name="terminal" size={14} /> Terminal</strong>
        {!collapsed && <label className="terminal-search"><Icon name="search" size={13} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search output" /></label>}
        <div className="terminal-head-actions">
          {!collapsed && <button onClick={clear} title="Clear terminal"><Icon name="trash" size={13} /></button>}
          <button onClick={() => setCollapsed((value) => !value)} title={collapsed ? 'Expand terminal' : 'Collapse terminal'}><Icon name="chevron" size={13} className={collapsed ? 'terminal-chevron-up' : ''} /></button>
          <button onClick={onClose} title="Close terminal"><Icon name="x" size={13} /></button>
        </div>
      </header>
      {!collapsed && <>
        <div className="terminal-output" ref={outputRef}>
          {visibleLogs.length ? visibleLogs.map((line, index) => <div key={`${index}-${line}`}>{line}</div>) : <span>{query ? 'No matching output.' : 'Vellium Tweaker ready, waiting for a client.'}</span>}
        </div>
        <footer className="terminal-statusbar">
          <span>Ln {Math.max(visibleLogs.length, 1)}, Col 1</span><span>UTF-8</span><span>Vellium Tweaker</span>
          <em className={attached ? 'online' : ''}><i />{attached ? 'Attached' : 'No client'}</em>
        </footer>
      </>}
    </section>
  );
}
