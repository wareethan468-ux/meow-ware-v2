import { useEffect, useState } from 'react';
import appIcon from '../assets/meow-ware-icon.png';
import { callDesktop } from '../lib/desktopApi';
import { Icon } from './Icons';
import DiscordAccountMenu from './DiscordAccountMenu';
import LicenseKeyMenu from './LicenseKeyMenu';
import Modal from './Modal';

export default function TitleBar() {
  const [disguised, setDisguised] = useState(false);
  const [exitOpen, setExitOpen] = useState(false);

  useEffect(() => {
    callDesktop('get_settings').then(settings => settings && setDisguised(Boolean(settings.disguise_mode)));
    const update = event => setDisguised(Boolean(event.detail));
    window.addEventListener('vellium:disguise', update);
    return () => window.removeEventListener('vellium:disguise', update);
  }, []);

  const handlePointerDown = async (e) => {
    if (e.target.closest('button, a, input, select, textarea, .modal-overlay, .wc-group, .titlebar-links, .license-key-menu-wrap, .discord-account-menu-wrap')) {
      return;
    }
    if (e.button !== 0) return;

    // Trigger Win32 message
    callDesktop('start_drag');

    // Direct screen-space pointer tracking for seamless movement
    const startScreenX = e.screenX;
    const startScreenY = e.screenY;
    let initialRect = null;
    try {
      initialRect = await callDesktop('get_window_rect');
    } catch {}

    if (!initialRect) return;

    let isMoving = false;
    const onPointerMove = (moveEv) => {
      const dx = moveEv.screenX - startScreenX;
      const dy = moveEv.screenY - startScreenY;
      if (!isMoving && Math.abs(dx) < 2 && Math.abs(dy) < 2) return;
      isMoving = true;
      callDesktop('set_window_rect', initialRect.x + dx, initialRect.y + dy, initialRect.w, initialRect.h);
    };

    const onPointerUp = () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
  };

  const handleDoubleClick = (e) => {
    if (e.target.closest('button, a, input, select, textarea, .modal-overlay, .wc-group, .titlebar-links, .license-key-menu-wrap, .discord-account-menu-wrap')) {
      return;
    }
    animateWindowAction('maximize', 'toggle_maximize');
  };

  const animateWindowAction = (kind, method) => {
    const root = document.documentElement;
    const className = `window-${kind}-transition`;
    root.classList.remove('window-minimize-transition', 'window-maximize-transition');
    root.classList.add(className);
    window.setTimeout(() => callDesktop(method), kind === 'minimize' ? 120 : 70);
    window.setTimeout(() => root.classList.remove(className), kind === 'minimize' ? 360 : 260);
  };

  const confirmExit = async () => {
    setExitOpen(false);
    document.documentElement.classList.add('window-exit-transition');
    window.setTimeout(() => callDesktop('close_window'), 150);
  };

  return (
    <header
      className={`titlebar pywebview-drag-region${disguised ? ' disguised' : ''}`}
      onPointerDown={handlePointerDown}
      onDoubleClick={handleDoubleClick}
    >
      {disguised ? <div className="brand-logo spotify">S</div> : <img className="brand-image" src={appIcon} alt="" />}
      <span className="titlebar-name">{disguised ? 'Spotify' : 'Vellium Tweaker'}</span>
      <div className="titlebar-sep" />
      <span className="titlebar-context">{disguised ? 'Music Player' : 'FastFlag Injector'}</span>
      <div className="titlebar-links">
        <button onClick={() => window.dispatchEvent(new Event('vellium:show-terms'))}>Terms</button>
      </div>
      <div className="wc-group">
        <LicenseKeyMenu />
        <DiscordAccountMenu />
        <button className="wc-btn discord" title="Discord Server" onClick={() => callDesktop('open_url', 'https://discord.com')}><Icon name="discord" size={15} /></button>
        <button className="wc-btn" aria-label="Minimize" onClick={() => animateWindowAction('minimize', 'minimize_window')}><Icon name="minus" size={12} /></button>
        <button className="wc-btn" aria-label="Maximize" onClick={() => animateWindowAction('maximize', 'toggle_maximize')}><Icon name="maximize" size={11} /></button>
        <button className="wc-btn close" aria-label="Close" onClick={() => setExitOpen(true)}><Icon name="x" size={12} /></button>
      </div>
      <Modal open={exitOpen} onClose={() => setExitOpen(false)} title="Exit Vellium Tweaker" width="390px"
        footer={<>
          <button className="btn" onClick={() => setExitOpen(false)}>Cancel</button>
          <button className="btn danger" onClick={confirmExit}><Icon name="x" size={12} /> Exit</button>
        </>}>
        <div className="modal-icon danger"><Icon name="x" size={18} /></div>
        <p className="modal-body-text">Are you sure you want to close Vellium Tweaker? Active Roblox processes will keep running.</p>
      </Modal>
    </header>
  );
}
