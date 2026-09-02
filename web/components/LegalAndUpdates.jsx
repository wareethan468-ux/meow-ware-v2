import Modal from './Modal';
import { APP_VERSION, RELEASE_NOTES } from '../data/releaseInfo';

export function TermsModal({ open, required, onAccept, onClose }) {
  return (
    <Modal
      open={open}
      onClose={required ? () => {} : onClose}
      title="Vellium Tweaker Terms of Service"
      subtitle="Please review these terms before using the application."
      width="620px"
      footer={<><button className="btn" onClick={onClose} disabled={required}>Close</button><button className="btn primary" onClick={onAccept}>{required ? 'Accept & Continue' : 'I Understand'}</button></>}
    >
      <div className="legal-copy">
        <section><h3>Use at your own risk</h3><p>Vellium Tweaker modifies local Roblox configuration and may interact with running Roblox processes. Changes can affect stability, performance, account access, or compatibility after Roblox updates.</p></section>
        <section><h3>No affiliation or warranty</h3><p>Vellium Tweaker is an independent tool and is not affiliated with, endorsed by, or supported by Roblox Corporation. The software is provided as-is without guarantees of availability, safety, or fitness for a particular purpose.</p></section>
        <section><h3>Your responsibility</h3><p>You are responsible for complying with Roblox rules and applicable law, reviewing flags before applying them, keeping backups, and accepting the consequences of custom versions or downgrades.</p></section>
        <section><h3>Local data and networking</h3><p>Settings and acceptance state are stored locally. Features such as update checks and offset syncing connect to their configured remote sources. Do not import files or offsets you do not trust.</p></section>
        <section><h3>Changes</h3><p>These terms and application behavior may change in future releases. A materially revised terms version will require acceptance again.</p></section>
      </div>
    </Modal>
  );
}

export function UpdateLogModal({ open, onClose }) {
  return (
    <Modal open={open} onClose={onClose} title={`What’s New in Vellium Tweaker ${APP_VERSION}`} subtitle="This appears once after each update. You can reopen it from the title bar." width="560px" footer={<button className="btn primary" onClick={onClose}>Got it</button>}>
      <div className="release-list">
        {RELEASE_NOTES.map((note, index) => <article key={note.title}><span>{String(index + 1).padStart(2, '0')}</span><div><h3>{note.title}</h3><p>{note.detail}</p></div></article>)}
      </div>
    </Modal>
  );
}
