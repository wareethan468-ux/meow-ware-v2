import { useEffect, useState } from 'react';
import appIcon from '../assets/meow-ware-icon.png';
import { Icon } from '../components/Icons';
import { callDesktop } from '../lib/desktopApi';

export default function AboutView() {
  const [info, setInfo] = useState({ name: 'Plex', version: '1.3.0-beta.1', channel: 'beta', beta: true, platform: 'desktop', key_required: false, repository: 'https://github.com/wareethan468-ux/meow-ware-v2' });
  useEffect(() => { callDesktop('get_build_info').then(value => value && setInfo(value)); }, []);
  return <div className="about-view view">
    <section className="about-hero">
      <div className="about-logo-wrap"><img src={appIcon} alt="" /></div>
      <div><span className="eyebrow">PLEX DESKTOP</span><h1>{info.name}</h1><p>A focused desktop workspace for Roblox FastFlags, runtime health, presets, and supported companion tools.</p><div className="about-badges"><span>v{info.version}</span><span className={info.beta ? 'beta' : ''}>{info.channel}</span><span>{info.platform}</span></div></div>
    </section>
    <div className="about-grid">
      <article><Icon name="layers" size={17}/><div><strong>FastFlag workspace</strong><p>Search, organize, import, export, and apply Roblox configuration flags.</p></div></article>
      <article><Icon name="activity" size={17}/><div><strong>Runtime monitor</strong><p>See process health, resource usage, versions, and offset readiness live.</p></div></article>
      <article><Icon name="shield" size={17}/><div><strong>{info.beta ? 'Beta access' : 'Release access'}</strong><p>{info.beta ? 'This beta build does not require a license key. Discord and terms onboarding still apply.' : 'Stable builds require an active Plex license key.'}</p></div></article>
      <article><Icon name="monitor" size={17}/><div><strong>Platform aware</strong><p>Windows includes all products. macOS focuses on safe file-based FastFlag configuration.</p></div></article>
    </div>
    <section className="about-footer-card"><div><strong>Open-source project</strong><p>View the source, report problems, or follow new automatic builds on GitHub.</p></div><button className="btn primary" onClick={() => callDesktop('open_url', info.repository)}><Icon name="globe" size={13}/> Open GitHub</button></section>
    <p className="about-disclaimer">Independent software. Not affiliated with or endorsed by Roblox Corporation.</p>
  </div>;
}
