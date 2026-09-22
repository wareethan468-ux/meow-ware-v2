import {useEffect,useState} from 'react';
import Toggle from '../components/Toggle';
import {Icon} from '../components/Icons';
import {callDesktop} from '../lib/desktopApi';

const definitions=[
 ['Runtime','enabled','Proxy enabled','Allows Vellium Proxy profiles to be started and applied.'],
 ['Runtime','run_as_admin','Run proxy as administrator','Requests Windows administrator permission whenever the Fleasion proxy starts.'],
 ['Scraper','scraper_enabled','Live asset scraper','Shows assets captured from Roblox in the Scraper tab.'],
 ['Profiles','auto_sync','Automatically sync changes','Writes profile edits to the local proxy configuration automatically.'],
 ['Storage','preserve_cache','Preserve captured assets','Keeps Fleasion cached assets available for previews and later sessions.'],
 ['Traffic','traffic_preserve','Preserve proxy traffic','Keeps request and response rows available in the Traffic tab between launches.'],
];

export default function ProxySettingsView({notify}){
 const [state,setState]=useState({enabled:true,run_as_admin:true,scraper_enabled:true,auto_sync:true,preserve_cache:true,traffic_preserve:true}),[admin,setAdmin]=useState(false),[loaded,setLoaded]=useState(false);
 useEffect(()=>{callDesktop('get_proxy_settings').then(result=>{if(result?.settings)setState(result.settings);setAdmin(Boolean(result?.is_admin));setLoaded(true)})},[]);
 const update=async(key,value,name)=>{setState(current=>({...current,[key]:value}));const result=await callDesktop('set_proxy_setting',key,value);notify(result?.ok?`${name} ${value?'enabled':'disabled'}`:result?.error||'Could not save proxy setting')};
 const groups=[...new Set(definitions.map(item=>item[0]))];
 return <div className="settings-view view proxy-settings-view"><div className="settings-container"><header className="proxy-settings-header"><span><Icon name="settings" size={17}/></span><div><h1>Proxy settings</h1><p>Runtime, scraper, profiles, and local storage preferences.</p></div><div className={`proxy-admin-status${admin?' active':''}`}><i/><span><strong>{admin?'Administrator session':'Standard session'}</strong><small>{state.run_as_admin?'Proxy requests elevation':'Elevation disabled'}</small></span></div></header><div className="settings-body">{groups.map(group=><div key={group}><div className="settings-group">{group}</div>{definitions.filter(item=>item[0]===group).map(([,key,name,desc])=><div className="setting-row" key={key}><div className="setting-info"><span className="setting-name">{name}</span><span className="setting-desc">{desc}</span></div><Toggle checked={Boolean(state[key])} disabled={!loaded} onChange={value=>update(key,value,name)} label={name}/></div>)}</div>)}</div></div></div>
}
