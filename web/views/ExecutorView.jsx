import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '../components/Icons';
import { callDesktop, hasDesktopApi, onDesktopReady } from '../lib/desktopApi';

// ─── Status machine ───────────────────────────────────────────────────────────
const S = {
  DETACHED:  'detached',   // pipe not open
  INJECTING: 'injecting',  // emulation.exe launched, waiting for pipe
  ATTACHED:  'attached',   // pipe ready
  RUNNING:   'running',    // script being sent
  ERROR:     'error',      // last operation failed
};

// ─── Status pill ──────────────────────────────────────────────────────────────
function StatusPill({ status }) {
  const map = {
    [S.DETACHED]:  { label: 'Not Attached',  icon: 'power',   cls: 'detached'  },
    [S.INJECTING]: { label: 'Injecting…',    icon: 'refresh', cls: 'injecting' },
    [S.ATTACHED]:  { label: 'Attached',      icon: 'check',   cls: 'attached'  },
    [S.RUNNING]:   { label: 'Executing…',    icon: 'refresh', cls: 'running'   },
    [S.ERROR]:     { label: 'Error',         icon: 'alert',   cls: 'err'       },
  };
  const { label, icon, cls } = map[status] ?? map[S.DETACHED];
  const spin = status === S.INJECTING || status === S.RUNNING;
  return (
    <span className={`exec-status-pill exec-status-${cls}`}>
      <Icon name={icon} size={11} className={spin ? 'exec-spin' : ''} />
      {label}
    </span>
  );
}

function EditorGutter({ script }) {
  const count = Math.max(1, script.split('\n').length);
  return (
    <div className="executor-gutter" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <span key={index}>{index + 1}</span>
      ))}
    </div>
  );
}

// ─── Output line ─────────────────────────────────────────────────────────────
function OutputLine({ line }) {
  return (
    <div className={`executor-output-line${line.type === 'error' ? ' err' : line.type === 'info' ? ' info' : ''}`}>
      {line.text}
    </div>
  );
}

// ─── Executor view ─────────────────────────────────────────────────────────────
// Runs inside the tweaker shell (product === 'executor'); the surrounding App
// supplies the title bar, resize handles, notifications and theming.
export default function ExecutorView({ notify }) {
  const [script, setScript] = useState('');
  const [output, setOutput] = useState([]);
  const [status, setStatus] = useState(S.DETACHED);
  const outputRef = useRef(null);
  const pollRef = useRef();

  // ── Auto-scroll output ────────────────────────────────────────────────────
  useEffect(() => {
    if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [output]);

  // ── Poll attach status every 3 s ─────────────────────────────────────────
  useEffect(() => {
    const poll = async () => {
      if (!hasDesktopApi()) return;
      const res = await callDesktop('executor_status');
      if (res?.attached && status === S.DETACHED) setStatus(S.ATTACHED);
      if (!res?.attached && status === S.ATTACHED) setStatus(S.DETACHED);
    };
    pollRef.current = setInterval(poll, 3000);
    onDesktopReady(poll);
    return () => clearInterval(pollRef.current);
  }, [status]);

  // ── Append line ───────────────────────────────────────────────────────────
  const appendLine = useCallback((text, type = 'log') => {
    setOutput(prev => [...prev, { text, type, id: Date.now() + Math.random() }]);
  }, []);

  // ── INJECT ────────────────────────────────────────────────────────────────
  const handleInject = useCallback(async () => {
    if (status === S.INJECTING || status === S.RUNNING) return;
    setStatus(S.INJECTING);
    appendLine('▶ Launching emulation.exe — injecting QuorumAPI.dll…', 'info');

    const res = await callDesktop('executor_attach');

    if (res?.ok) {
      setStatus(S.ATTACHED);
      appendLine('✔ QuorumAPI.dll attached — pipe ready.', 'info');
      if (res.warn) appendLine(`⚠ ${res.warn}`, 'info');
      notify('Executor attached!');
    } else {
      setStatus(S.ERROR);
      const msg = res?.error ?? 'Unknown error';
      appendLine(`✖ Inject failed: ${msg}`, 'error');
      notify({ title: 'Inject failed', message: msg, type: 'error' });
    }
  }, [status, appendLine, notify]);

  // ── EXECUTE ───────────────────────────────────────────────────────────────
  const handleRun = useCallback(async () => {
    if (!script.trim()) { notify({ title: 'Empty script', message: 'Write a script first.', type: 'error' }); return; }
    if (status === S.DETACHED || status === S.INJECTING) {
      notify({ title: 'Not attached', message: 'Click Inject first.', type: 'error' });
      return;
    }
    if (status === S.RUNNING) return;

    setStatus(S.RUNNING);
    appendLine('▶ Sending script to QuorumAPI…', 'info');

    const res = await callDesktop('executor_run', script);

    if (res?.ok) {
      setStatus(S.ATTACHED);
      appendLine(res.output ?? '✔ Script sent.', 'info');
      notify('Script executed!');
    } else {
      setStatus(S.ERROR);
      const msg = res?.error ?? 'Unknown error';
      appendLine(`✖ ${msg}`, 'error');
      notify({ title: 'Execute failed', message: msg, type: 'error' });
    }
  }, [script, status, appendLine, notify]);

  // ── Ctrl+Enter shortcut ───────────────────────────────────────────────────
  const handleKeyDown = useCallback((e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); handleRun(); }
  }, [handleRun]);

  // ── Clear ─────────────────────────────────────────────────────────────────
  const handleClear = () => { setScript(''); setOutput([]); if (status === S.ERROR) setStatus(S.DETACHED); };

  const isAttached = status === S.ATTACHED || status === S.RUNNING;
  const isBusy = status === S.INJECTING || status === S.RUNNING;
  const lineCount = Math.max(1, script.split('\n').length);
  const characterCount = script.length;

  return (
    <div className="executor-view view">

      {/* ── Toolbar ── */}
      <div className="exec-toolbar">
        <div className="exec-file-info">
          <Icon name="code" size={13} />
          <span>untitled.lua</span>
          {script.length > 0 && <i title="Unsaved changes" />}
          <StatusPill status={status} />
        </div>

        <div className="exec-toolbar-actions">
          {/* Inject */}
          <button
            className={`btn${status === S.INJECTING ? ' loading' : ''}${isAttached ? ' success-outline' : ' primary'}`}
            onClick={handleInject}
            disabled={isBusy}
            title="Run emulation.exe to inject QuorumAPI.dll into Roblox"
          >
            <Icon name="rocket" size={13} />
            {status === S.INJECTING ? 'Injecting…' : isAttached ? 'Re-Inject' : 'Inject'}
          </button>

          {/* Execute */}
          <button
            className={`btn primary${status === S.RUNNING ? ' loading' : ''}`}
            onClick={handleRun}
            disabled={isBusy || !script.trim()}
            title="Send script to QuorumAPI via named pipe (Ctrl+Enter)"
          >
            <Icon name="play" size={13} />
            {status === S.RUNNING ? 'Running…' : 'Execute'}
          </button>

          {/* Clear */}
          <button className="btn" onClick={handleClear} disabled={isBusy} title="Clear editor and output">
            <Icon name="trash" size={13} />
            Clear
          </button>
        </div>
      </div>

      <div className="executor-shell">

        {/* ── Editor ── */}
        <div className="executor-editor-panel">
          <div className="executor-editor-header">
            <span className="executor-panel-label">
              <Icon name="code" size={13} />
              Lua Script
            </span>
            <span className="exec-language-badge">Lua</span>
            <span className="exec-hint"><kbd>Ctrl</kbd><span>+</span><kbd>Enter</kbd> to execute</span>
          </div>
          <div className="executor-editor-wrap">
            <EditorGutter script={script} />
            <textarea
              className="executor-editor"
              value={script}
              onChange={e => setScript(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={"-- Paste your Lua script here\n-- Ctrl+Enter to execute\n\nprint(\"Hello from QuorumAPI!\")"}
              spellCheck={false}
              autoCorrect="off"
              autoCapitalize="off"
              disabled={isBusy}
              aria-label="Script editor"
            />
          </div>
          <footer className="executor-editor-footer">
            <span>Lua</span>
            <span>{lineCount} {lineCount === 1 ? 'line' : 'lines'}</span>
            <span>{characterCount.toLocaleString()} characters</span>
            <span className="executor-footer-mode">UTF-8</span>
          </footer>
        </div>

        {/* ── Output ── */}
        <div className="executor-output-panel">
          <div className="executor-output-header">
            <span className="executor-panel-label">
              <Icon name="terminal" size={13} />
              Output
            </span>
            <button
              className="btn ghost executor-clear-output"
              onClick={() => setOutput([])}
              disabled={output.length === 0}
              title="Clear output"
            >
              <Icon name="x" size={11} />
            </button>
          </div>
          <div className="executor-output" ref={outputRef} aria-live="polite">
            {output.length === 0
              ? <div className="executor-output-empty">
                  <span>No output</span>
                </div>
              : output.map(l => <OutputLine key={l.id} line={l} />)
            }
          </div>
        </div>

      </div>
    </div>
  );
}
