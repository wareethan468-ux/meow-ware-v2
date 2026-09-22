import { useCallback, useEffect, useMemo, useState } from 'react';
import { Icon } from '../components/Icons';
import CustomSelect from '../components/CustomSelect';              
import { DowngradeNotice, VersionBadge } from '../components/VersionStatus';
import { callDesktop } from '../lib/desktopApi';

const short = value => value ? String(value).replace(/^version-/, '').slice(0, 12) : '—';
const sections = [
  ['integrations', 'plus', 'Integrations'], ['bootstrapper', 'rocket', 'Bootstrapper'],
  ['mods', 'settings', 'Mods'], ['engine', 'flag', 'Engine Settings'],
  ['appearance', 'brush', 'Appearance'], ['shortcuts', 'box', 'Shortcuts'],
];

function Switch({ value, onChange, disabled = false }) {
  return <button type="button" role="switch" aria-checked={value} disabled={disabled} className={`plex-switch${value ? ' on' : ''}`} onClick={() => onChange(!value)}><i /></button>;
}
function Setting({ title, description, children }) {
  return <div className="plex-boot-setting"><span><strong>{title}</strong><small>{description}</small></span><div>{children}</div></div>;
}

export default function BootstrapperView({ notify, monitor, onNavigate }) {
  const [section, setSection] = useState('bootstrapper');
  const [builds, setBuilds] = useState({ versions: [] });
  const [targets, setTargets] = useState({ targets: [], selected_path: '' });
  const [handler, setHandler] = useState(false);
  const [settings, setSettings] = useState({});
  const [target, setTarget] = useState('');
  const [ack, setAck] = useState(false);
  const [progress, setProgress] = useState(null);
  const [busy, setBusy] = useState(false);
  const [prefs, setPrefs] = useState(() => {
    try { return { analytics: false, joining: true, account: true, cursor: 'default', oldBackground: false, oldSounds: false, emoji: 'default', style: 'plex', icon: 'plex', title: 'Plex Bootstrapper', compact: false, ...(JSON.parse(localStorage.getItem('plex:bootstrapper') || '{}')) }; }
    catch { return {}; }
  });
  const savePref = (key, value) => setPrefs(current => { const next = { ...current, [key]: value }; localStorage.setItem('plex:bootstrapper', JSON.stringify(next)); return next; });

  const refresh = useCallback(async () => {
    const [options, automatic, currentSettings, launchTargets] = await Promise.all([
      callDesktop('get_roblox_build_options'), callDesktop('get_auto_launch'), callDesktop('get_settings'), callDesktop('get_launch_targets'),
    ]);
    if (options?.ok !== false) setBuilds(options || { versions: [] });
    setHandler(Boolean(automatic)); setSettings(currentSettings || {}); setTargets(launchTargets || { targets: [] });
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (progress?.state !== 'running') return undefined;
    const timer = setInterval(async () => {
      const next = await callDesktop('get_roblox_fix_progress'); if (!next) return;
      setProgress(next);
      if (next.state === 'done') { clearInterval(timer); notify(next.message || 'Roblox installed.'); refresh(); }
      if (['failed', 'cancelled'].includes(next.state)) { clearInterval(timer); notify({ title: 'Install stopped', message: next.message || 'The build could not be installed.', type: 'error' }); }
    }, 600);
    return () => clearInterval(timer);
  }, [progress?.state, notify, refresh]);

  const versions = useMemo(() => (builds.versions || []).map(item => ({ value: typeof item === 'string' ? item : item.version, label: short(typeof item === 'string' ? item : item.version), detail: item.created_at ? new Date(item.created_at).toLocaleDateString() : '' })), [builds.versions]);
  const older = Boolean(target && builds.latest_production && target !== builds.latest_production);
  const setBackend = (key, value, method) => { setSettings(current => ({ ...current, [key]: value })); callDesktop(method, value); };
  const launch = async () => { setBusy(true); const result = await callDesktop('launch_and_apply'); setBusy(false); notify(result?.error ? { title: 'Launch failed', message: result.error, type: 'error' } : 'Launching Roblox through Plex…'); };
  const toggleHandler = async value => { setHandler(value); const result = await callDesktop('set_auto_launch', value); if (typeof result?.enabled === 'boolean') setHandler(result.enabled); notify(result?.message || (value ? 'Plex is now your Roblox launcher.' : 'Roblox launcher routing disabled.')); };
  const install = async () => { const result = await callDesktop('start_roblox_version_download', target ? 'custom' : 'latest', target, ack); if (['started', 'already_running'].includes(result?.state)) setProgress({ state: 'running', progress: 0, message: result.message }); else notify({ title: 'Install unavailable', message: result?.message || 'Could not start the install.', type: 'error' }); };

  const page = {
    integrations: <><PageTitle title="Integrations" text="Connect Plex to your desktop and launch companion programs with Roblox."/><Setting title="Allow activity joining" description="Let friends join your current Roblox game through Discord activity."><Switch value={prefs.joining} onChange={value => savePref('joining', value)}/></Setting><Setting title="Show Roblox account" description="Show the Roblox account currently playing in Discord presence."><Switch value={prefs.account} onChange={value => savePref('account', value)}/></Setting><Panel title="Custom integrations" text="Programs configured here can launch alongside Roblox."><div className="plex-empty"><Icon name="plus" size={22}/><strong>No custom integrations</strong><small>Integration management is coming in a later Plex build.</small></div></Panel></>,
    bootstrapper: <><PageTitle title="Bootstrapper" text="Install, configure, and launch Roblox through Plex."/><div className="plex-launch-card"><span><i className={monitor?.running ? 'live' : ''}/><div><strong>{monitor?.running ? 'Roblox is running' : 'Ready to launch'}</strong><small>Installed {short(builds.installed_version)} · Latest {short(builds.latest_production)}</small></div></span><button className="btn primary" disabled={busy} onClick={launch}><Icon name="play" size={13}/>{busy ? 'Launching…' : 'Launch Roblox'}</button></div><Setting title="Use Plex as the Roblox launcher" description="Handle browser Play links, apply FastFlags, and start the selected client."><Switch value={handler} onChange={toggleHandler}/></Setting><Setting title="Automatically update Roblox" description="Install the latest production build before launch when needed."><Switch value={Boolean(settings.auto_update)} onChange={value => setBackend('auto_update', value, 'set_auto_update')}/></Setting><Panel title="Client build" text={`${versions.length} downloadable build${versions.length === 1 ? '' : 's'} found.`}><div className="plex-build-row"><CustomSelect searchable value={target} onChange={value => { setTarget(value); setAck(false); }} options={versions} label={`Latest production · ${short(builds.latest_production)}`}/><VersionBadge kind={older ? 'downgrade' : 'latest'}/></div>{older && <DowngradeNotice compact acknowledged={ack} onAcknowledge={setAck}/>} {progress?.state === 'running' && <div className="build-progress"><div><span>{progress.message}</span><strong>{progress.progress || 0}%</strong></div><i><b style={{ width: `${Math.max(2, progress.progress || 0)}%` }}/></i></div>}<div className="plex-inline-actions"><button className="btn primary" disabled={progress?.state === 'running' || (older && !ack)} onClick={install}><Icon name="download" size={13}/>Install selected</button><button className="btn" onClick={() => onNavigate?.('builds')}><Icon name="layers" size={13}/>Manage builds</button></div></Panel></>,
    mods: <><PageTitle title="Mods" text="Personalize compatible Roblox resources while keeping controls easy to reverse."/><Setting title="Mouse cursor" description="Choose the cursor style Roblox should use."><CustomSelect compact value={prefs.cursor} onChange={value => savePref('cursor', value)} options={[{value:'default',label:'Default'},{value:'2013',label:'Classic 2013'},{value:'2006',label:'Classic 2006'}]}/></Setting><Setting title="Use old avatar editor background" description="Restore the avatar editor background used before 2020."><Switch value={prefs.oldBackground} onChange={value => savePref('oldBackground', value)}/></Setting><Setting title="Emulate old character sounds" description="Use a classic-style sound collection when available."><Switch value={prefs.oldSounds} onChange={value => savePref('oldSounds', value)}/></Setting><Setting title="Preferred emoji type" description="Choose which emoji presentation Plex requests."><CustomSelect compact value={prefs.emoji} onChange={value => savePref('emoji', value)} options={[{value:'default',label:'Default'},{value:'windows',label:'Windows'},{value:'legacy',label:'Legacy'}]}/></Setting></>,
    engine: <><PageTitle title="Engine Settings" text="Control Plex behavior around Roblox startup and FastFlag application."/><Setting title="Auto-apply FastFlags" description="Apply the current configuration whenever a Roblox process is found."><Switch value={Boolean(settings.auto_apply)} onChange={value => setBackend('auto_apply', value, 'set_auto_apply')}/></Setting><Setting title="Close Plex to tray" description="Keep the launcher available after its window closes."><Switch value={Boolean(settings.close_to_tray)} onChange={value => setBackend('close_to_tray', value, 'set_close_to_tray')}/></Setting><Setting title="Start minimized" description="Open Plex in the tray when Windows starts it."><Switch value={Boolean(settings.start_in_tray)} onChange={value => setBackend('start_in_tray', value, 'set_start_in_tray')}/></Setting><Setting title="Anonymous diagnostics" description="Store local diagnostic output to help troubleshoot failed launches."><Switch value={prefs.analytics} onChange={value => savePref('analytics', value)}/></Setting></>,
    appearance: <><PageTitle title="Appearance" text="Configure how the Plex bootstrapper should look."/><Setting title="Bootstrapper style" description="Choose the visual density of the launcher workspace."><CustomSelect compact value={prefs.style} onChange={value => savePref('style', value)} options={[{value:'plex',label:'Plex'},{value:'compact',label:'Plex Compact'},{value:'minimal',label:'Minimal'}]}/></Setting><Setting title="Window title" description="The title shown by the bootstrapper."><input className="input" value={prefs.title} onChange={event => savePref('title', event.target.value)}/></Setting><Setting title="Shared Plex theme" description="Colors, surfaces, controls, and motion follow the global theme."><button className="btn" onClick={() => onNavigate?.('themes')}><Icon name="brush" size={13}/>Open Themes</button></Setting></>,
    shortcuts: <><PageTitle title="Shortcuts" text="Quick access to Plex and Roblox."/><Setting title="Desktop shortcut" description="Create a Plex shortcut from the main Settings page."><button className="btn" onClick={() => notify('Shortcut controls are available in Plex Settings.')}><Icon name="box" size={13}/>Open instructions</button></Setting><Setting title="Command menu" description="Jump between Plex pages and actions from anywhere."><kbd>Ctrl + K</kbd></Setting><Setting title="Launch and apply" description="Open Roblox after writing the current FastFlags."><kbd>Ctrl + Shift + Enter</kbd></Setting></>,
    about: <><PageTitle title="About Plex Bootstrapper" text="A Roblox launcher integrated directly into the Plex desktop suite."/><Panel title="Plex Bootstrapper" text="Build management, protocol routing, FastFlag application, and Roblox launch controls in one interface."><div className="plex-about-mark"><Icon name="rocket" size={28}/><div><strong>Plex</strong><small>Independent software · not affiliated with Roblox Corporation</small></div></div></Panel></>,
  }[section];

  return <div className="plex-bootstrapper view">
    <aside className="plex-boot-sidebar"><header><Icon name="rocket" size={17}/><strong>Plex Bootstrapper</strong></header><nav>{sections.map(([id, icon, label]) => <button key={id} className={section === id ? 'active' : ''} onClick={() => setSection(id)}><Icon name={icon} size={15}/><span>{label}</span></button>)}</nav><footer><button className={section === 'about' ? 'active' : ''} onClick={() => setSection('about')}><Icon name="info" size={15}/>About</button><span><i className={monitor?.running ? 'live' : ''}/>{monitor?.running ? 'Roblox live' : 'Roblox idle'}</span></footer></aside>
    <main className="plex-boot-content">{page}</main>
  </div>;
}

function PageTitle({ title, text }) { return <header className="plex-boot-heading"><h1>{title}</h1><p>{text}</p></header>; }
function Panel({ title, text, children }) { return <section className="plex-boot-panel"><header><strong>{title}</strong><small>{text}</small></header>{children}</section>; }
