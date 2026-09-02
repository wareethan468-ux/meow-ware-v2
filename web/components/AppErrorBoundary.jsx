import React from 'react';
import { Icon } from './Icons';
import { callDesktop } from '../lib/desktopApi';

export default class AppErrorBoundary extends React.Component {
  state = { crashed: false, message: '' };

  static getDerivedStateFromError(error) {
    return { crashed: true, message: error?.message || 'The interface encountered an unexpected error.' };
  }

  componentDidCatch(error, info) {
    callDesktop('record_ui_crash', error?.message || String(error), info?.componentStack || error?.stack || '').catch(() => {});
  }

  recover = () => {
    try {
      const cached = JSON.parse(window.localStorage.getItem('meowware-theme') || '{}');
      if (cached && typeof cached === 'object') {
        cached.customCss = '';
        window.localStorage.setItem('meowware-theme', JSON.stringify(cached));
      }
    } catch { /* recovery must continue even if storage is unavailable */ }
    window.location.reload();
  };

  render() {
    if (!this.state.crashed) return this.props.children;
    return <main className="crash-recovery"><section><span><Icon name="shield" size={22}/></span><small>ANTI-CRASH RECOVERY</small><h1>Vellium Tweaker recovered the window.</h1><p>{this.state.message}</p><div><button className="btn primary" onClick={this.recover}><Icon name="refresh" size={13}/> Reload safely</button><button className="btn" onClick={()=>callDesktop('open_config_folder')}><Icon name="folder" size={13}/> Open recovery files</button></div><em>The backend remains running. A local report was saved to ui-crash.log.</em></section></main>;
  }
}
