import { useEffect, useRef, useState } from 'react';
import { callDesktop, hasDesktopApi } from '../lib/desktopApi';
import { Icon } from './Icons';
import Modal from './Modal';
import AttachmentMenu from './AttachmentMenu';

export default function AttachmentStatus({ product = 'injector' }) {
  const [state, setState] = useState({ attached: false, selected_pid: 0, processes: [] });
  const [open, setOpen] = useState(false);
  const [busyPid, setBusyPid] = useState(0);
  const [error, setError] = useState('');
  const [endConfirmPid, setEndConfirmPid] = useState(0);
  const rootRef = useRef(null);

  const refresh = async () => {
    if (!hasDesktopApi()) return;
    if (product === 'executor') {
      const res = await callDesktop('executor_status');
      if (res) setState({ attached: Boolean(res.attached), selected_pid: 0, processes: [] });
      return;
    }
    const next = await callDesktop('get_attachment_targets');
    if (next) setState(next);
  };

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 1500);
    return () => window.clearInterval(timer);
  }, [product]);

  const choose = async (pid) => {
    setBusyPid(pid);
    setError('');
    const result = await callDesktop('attach_to_process', pid);
    setBusyPid(0);
    if (!result?.ok) {
      setError(result?.error || 'Could not attach');
      return;
    }
    await refresh();
    setOpen(false);
  };

  const detach = async () => {
    setBusyPid(state.selected_pid || -1);
    setError('');
    const result = await callDesktop('detach_from_process');
    setBusyPid(0);
    if (!result?.ok) setError(result?.error || 'Could not detach');
    await refresh();
  };

  const endProcess = async () => {
    const pid = endConfirmPid || state.selected_pid;
    if (!pid) return;
    setEndConfirmPid(0);
    setBusyPid(pid);
    setError('');
    const result = await callDesktop('end_roblox_process', pid);
    setBusyPid(0);
    if (!result?.ok) {
      setError(result?.error || 'Could not end process');
      return;
    }
    await refresh();
  };

  const isStatic = product === 'proxy' || product === 'executor';
  const roleLabel = product === 'proxy' ? 'Proxy' : product === 'executor' ? 'Executor' : 'Injector';
  const primaryText = state.attached
    ? (state.selected_pid ? `Attached · ${state.selected_pid}` : 'Attached')
    : (product === 'injector' ? 'Waiting for Roblox' : 'Not attached');
  const titleText = product === 'proxy' ? 'Asset Proxy status' : product === 'executor' ? 'Executor status' : 'Select Roblox process';

  return (
    <div className="attachment-status" ref={rootRef}>
      <button
        className={`attachment-trigger ${state.attached ? 'is-attached' : ''}${isStatic ? ' is-static' : ''}`}
        onClick={() => { if (!isStatic) { setOpen((value) => !value); refresh(); } }}
        aria-expanded={open}
        title={titleText}
      >
        <span className="attachment-dot" />
        <span className="attachment-copy">
          <span>{primaryText}</span>
          <em>{state.attached ? `${roleLabel} active` : `${roleLabel} idle`}</em>
        </span>
        {!isStatic && <Icon name="chevron" size={12} />}
      </button>

      {!isStatic && <AttachmentMenu
        open={open}
        processes={state.processes}
        selectedPid={state.selected_pid}
        attached={state.attached}
        busyPid={busyPid}
        error={error}
        onChoose={choose}
        onDetach={detach}
        onEndProcess={(pid) => setEndConfirmPid(pid)}
        onClose={() => setOpen(false)}
      />}
      <Modal open={Boolean(endConfirmPid)} onClose={() => setEndConfirmPid(0)} title="End Roblox Process" width="390px"
        footer={<>
          <button className="btn" onClick={() => setEndConfirmPid(0)}>Cancel</button>
          <button className="btn danger" onClick={endProcess}><Icon name="x" size={12} /> End process</button>
        </>}>
        <div className="modal-icon danger"><Icon name="alert" size={18} /></div>
        <p className="modal-body-text">End Roblox process <strong>{endConfirmPid}</strong>? Unsaved game progress may be lost.</p>
      </Modal>
    </div>
  );
}
