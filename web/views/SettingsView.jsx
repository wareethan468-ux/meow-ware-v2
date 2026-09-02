import { useEffect, useState } from 'react';
import Toggle from '../components/Toggle';
import { callDesktop } from '../lib/desktopApi';

const SETTINGS = [
  {
    group: 'Performance',
    key: 'fps',
    settingKey: 'fps_unlocker_enabled',
    method: 'set_fps_unlocker',
    name: 'FPS Unlocker',
    desc: 'Removes the frame-rate cap and keeps the setting unlocked',
  },
  {
    group: 'Injection',
    key: 'auto',
    settingKey: 'auto_apply',
    method: 'set_auto_apply',
    name: 'Auto-Reapply',
    desc: 'Watches Roblox memory every 5s and reapplies any flag that gets reset',
  },
  {
    group: 'Appearance',
    key: 'disguise',
    settingKey: 'disguise_mode',
    method: 'set_disguise_mode',
    name: 'Disguise Mode',
    desc: 'Renames the app window to "Spotify" for privacy',
  },
  {
    group: 'Integrations',
    key: 'discord_rpc',
    settingKey: 'discord_rpc_enabled',
    method: 'set_discord_rpc',
    name: 'Discord Rich Presence',
    desc: 'Shows Vellium Tweaker status and activity on your Discord profile',
  },
  {
    group: 'Workspace',
    key: 'save_workspace_state',
    settingKey: 'save_workspace_state',
    method: 'set_save_workspace_state',
    name: 'Save Workspace State',
    desc: 'Saves your active flags when closing. When disabled, starts with a clean empty workspace',
  },
  {
    group: 'System',
    key: 'tray',
    settingKey: 'close_to_tray',
    method: 'set_close_to_tray',
    name: 'Minimize to Tray',
    desc: 'Closes to system tray instead of exiting',
  },
];

export default function SettingsView({ notify }) {
  const [state, setState] = useState({
    auto: true,
    fps: true,
    disguise: false,
    discord_rpc: true,
    tray: false,
    save_workspace_state: true,
  });

  useEffect(() => {
    callDesktop('get_settings').then(s => {
      if (!s) return;
      setState({
        auto: Boolean(s.auto_apply),
        fps: Boolean(s.fps_unlocker_enabled),
        disguise: Boolean(s.disguise_mode),
        discord_rpc: s.discord_rpc_enabled !== undefined ? Boolean(s.discord_rpc_enabled) : true,
        tray: Boolean(s.close_to_tray),
        save_workspace_state: s.save_workspace_state !== undefined ? Boolean(s.save_workspace_state) : true,
      });
    });
  }, []);

  const update = async (def, val) => {
    setState(cur => ({ ...cur, [def.key]: val }));
    await callDesktop(def.method, val);
    if (def.key === 'disguise')
      window.dispatchEvent(new CustomEvent('vellium:disguise', { detail: val }));
    notify(`${def.name} ${val ? 'enabled' : 'disabled'}`);
  };

  const groups = [...new Set(SETTINGS.map(s => s.group))];

  return (
    <div className="settings-view view">
      <div className="settings-container">
        <div className="view-title" style={{ marginBottom: 4 }}>Settings</div>
        <div className="view-sub" style={{ marginBottom: 16 }}>App preferences</div>
        <div className="settings-body">
          {groups.map(group => (
            <div key={group}>
              <div className="settings-group">{group}</div>
              {SETTINGS.filter(s => s.group === group).map(def => (
                <div className="setting-row" key={def.key}>
                  <div className="setting-info">
                    <span className="setting-name">{def.name}</span>
                    <span className="setting-desc">{def.desc}</span>
                  </div>
                  <Toggle
                    checked={state[def.key]}
                    onChange={val => update(def, val)}
                    label={def.name}
                  />
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
