import { useEffect, useRef, useState } from 'react';
import { Icon } from '../components/Icons';
import { previewLogs } from '../data/uiData';
import { callDesktop, hasDesktopApi } from '../lib/desktopApi';

export default function ConsoleView({ notify }) {
  const [logs, setLogs] = useState(() => hasDesktopApi() ? [] : previewLogs);
  const cursor = useRef({ index: 0, epoch: 0 });
  const outRef = useRef(null);

  useEffect(() => {
    if (!hasDesktopApi()) return;
    let active = true;

    const poll = async () => {
      const r = await callDesktop('get_logs', cursor.current.index, cursor.current.epoch);
      if (!active || !r) return;
      if (r.logs?.length) {
        setLogs(cur => {
          const next = cur.slice(-600);
          r.logs.forEach(e => e.replace && next.length
            ? (next[next.length - 1] = e.msg)
            : next.push(e.msg));
          return next;
        });
      }
      cursor.current = { index: r.total ?? cursor.current.index, epoch: r.tail_epoch ?? cursor.current.epoch };
    };

    poll();
    const id = setInterval(poll, 1000);
    return () => { active = false; clearInterval(id); };
  }, []);

  useEffect(() => {
    if (outRef.current) outRef.current.scrollTop = outRef.current.scrollHeight;
  }, [logs]);

  const clearLogs = async () => {
    const r = await callDesktop('clear_logs');
    setLogs([]);
    if (r) cursor.current = { index: r.total ?? 0, epoch: r.tail_epoch ?? 0 };
    notify('Console cleared');
  };

  const copyLogs = async () => {
    try {
      await navigator.clipboard.writeText(logs.join('\n'));
      notify('Copied to clipboard');
    } catch { notify('Copy failed'); }
  };

  const formatLine = line => {
    const m = line.match(/^(\[[\d:/ ]+(?:AM|PM)?\])/);
    return m
      ? <><span className="log-ts">{m[1]}</span>{line.slice(m[1].length)}</>
      : line;
  };

  return (
    <div className="console-view view">
      <div className="console-toolbar">
        <div>
          <div className="view-title">Console</div>
          <div className="view-sub">Live runtime output</div>
        </div>
        <div className="console-toolbar-right">
          <button className="btn" onClick={clearLogs}><Icon name="trash" size={12} /> Clear</button>
          <button className="btn" onClick={copyLogs}><Icon name="copy" size={12} /> Copy</button>
        </div>
      </div>
      <pre className="console-out" ref={outRef}>
        {logs.length
          ? logs.map((line, i) => <div key={i}>{formatLine(line)}</div>)
          : <span className="log-none">No output yet.</span>}
      </pre>
    </div>
  );
}
