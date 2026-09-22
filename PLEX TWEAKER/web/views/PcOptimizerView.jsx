import { useEffect, useState } from 'react';
import { Icon } from '../components/Icons';
import Modal from '../components/Modal';
import { callDesktop } from '../lib/desktopApi';

export default function PcOptimizerView({ notify }) {
  const [status, setStatus] = useState(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [launching, setLaunching] = useState(false);
  const refresh = async () => setStatus(await callDesktop('get_plex_optimizer_status'));
  useEffect(() => { refresh(); const timer = setInterval(refresh, 2500); return () => clearInterval(timer); }, []);
  const launch = async () => {
    setLaunching(true);
    const result = await callDesktop('launch_plex_optimizer');
    setLaunching(false); setConfirmOpen(false);
    notify(result?.ok ? result.message : { title: 'Optimizer unavailable', message: result?.error || 'The optimizer could not start.', type: 'error' });
    refresh();
  };
  const features = [
    ['gauge', 'Optimization profiles', 'Curated Windows, network, responsiveness, and gaming adjustments.'],
    ['activity', 'System scan', 'Inspect the PC and show relevant recommendations before making changes.'],
    ['gamepad', 'Game profiles', 'Manage game-specific performance settings from the optimizer.'],
    ['refresh', 'History and restore', 'Track transactions and restore previously changed values.'],
    ['shield', 'Repair tools', 'Use the engine’s built-in Windows repair workflows.'],
  ];
  return <div className="pc-optimizer-view view">
    <header className="optimizer-hero">
      <div><span>PLEX SYSTEM LAB</span><h1>Plex Optimizer</h1><p>The complete optimizer engine with scanning, reversible transactions, repair tools, and game profiles.</p></div>
      <div><button className="btn" onClick={refresh}><Icon name="refresh" size={13}/> Refresh</button><button className="btn primary" disabled={!status?.available} onClick={() => setConfirmOpen(true)}><Icon name="rocket" size={13}/> Open optimizer</button></div>
    </header>
    <section className="optimizer-stats">
      <article><Icon name="cpu" size={16}/><span><small>ENGINE</small><strong>{status?.engine || 'Checking…'}</strong></span></article>
      <article><Icon name="shield" size={16}/><span><small>SAFETY</small><strong>Transactional restore</strong></span></article>
      <article><Icon name="activity" size={16}/><span><small>STATUS</small><strong>{status?.running ? 'Running' : status?.available ? 'Ready' : 'Unavailable'}</strong></span></article>
      <article><Icon name="monitor" size={16}/><span><small>PLATFORM</small><strong>Windows 10 / 11</strong></span></article>
    </section>
    <section className="optimizer-layout">
      <div className="optimizer-main">
        <div className="optimizer-section-head"><div><span>Full optimization suite</span><small>This launches the real optimizer instead of Plex's former placeholder tweaks.</small></div><b>REAL ENGINE</b></div>
        <div className="optimizer-action-list">{features.map(([icon, name, detail]) => <div className="optimizer-engine-row" key={name}><i><Icon name={icon} size={15}/></i><span><strong>{name}</strong><small>{detail}</small></span><Icon name="check" size={13}/></div>)}</div>
      </div>
      <aside className="optimizer-side">
        <div className="optimizer-safety"><Icon name="shield" size={18}/><strong>Review before applying</strong><p>The optimizer shows confirmation and progress screens. Some actions require the genuine Windows administrator prompt.</p></div>
        <div className="optimizer-credit"><small>OPEN-SOURCE ENGINE</small><strong>66mods Tweaker</strong><p>{status?.attribution || 'Powered by the MIT-licensed 66mods Tweaker engine.'}</p></div>
        {status?.error && <div className="optimizer-warning"><Icon name="warning" size={16}/><p>{status.error}</p></div>}
      </aside>
    </section>
    <Modal open={confirmOpen} onClose={() => !launching && setConfirmOpen(false)} title="Open Plex Optimizer" subtitle="Launch the complete optimizer workspace" width="470px" footer={<><button className="btn" disabled={launching} onClick={() => setConfirmOpen(false)}>Cancel</button><button className="btn primary" disabled={launching} onClick={launch}>{launching ? 'Opening…' : 'Open optimizer'}</button></>}>
      <p className="modal-body-text">Plex will open the full 66mods-based optimizer in a separate window. Review every selected change before applying it.</p>
    </Modal>
  </div>;
}
