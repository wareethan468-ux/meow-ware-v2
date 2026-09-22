import { useMemo, useState } from 'react';
import { Icon } from '../Icons';

const tabs=[['layers','Flags'],['list','Presets'],['terminal','Console'],['settings','Themes']];
const flags=[['FFlagDebugGraphicsPreferD3D11','Boolean','True'],['DFIntDebugFRMQualityLevelOverride','Integer','1'],['FIntDebugForceMSAASamples','Integer','4'],['FFlagDisablePostFx','Boolean','False'],['DFIntTextureQualityOverride','Integer','2']];

function EmptyView({ icon, title, text, children }) { return <div className="empty"><Icon name={icon} size={25}/><h3>{title}</h3><p>{text}</p>{children||<button>Open workspace</button>}</div> }

export default function ProductDemo() {
  const [tab,setTab]=useState('Flags'); const [query,setQuery]=useState(''); const [statusOpen,setStatusOpen]=useState(false);
  const results=useMemo(()=>flags.filter(([name])=>name.toLowerCase().includes(query.toLowerCase())),[query]);
  return <div className="demo" aria-label="Interactive Meow Ware demo">
    <header><span><img src="/meow-ware-icon.png" alt=""/><b>Meow Ware</b><small>FastFlag Manager</small></span><i/><i/><i/></header>
    <div className="work"><aside>{tabs.map(([icon,label])=><button key={label} className={tab===label?'active':''} onClick={()=>setTab(label)} aria-label={label}><Icon name={icon}/><span>{label}</span></button>)}</aside><main>
      <nav><span><small>WORKSPACE</small><b>{tab}</b></span><button onClick={()=>setStatusOpen(!statusOpen)}><i/> Waiting for Roblox <Icon name={statusOpen?'minus':'plus'} size={11}/></button>{statusOpen&&<menu><b>No client attached</b><small>Launch Roblox to connect</small><button><Icon name="refresh" size={12}/> Scan again</button><button><Icon name="process" size={12}/> Select process</button></menu>}</nav>
      {tab==='Flags'&&<div className="flags"><section><label><Icon name="search" size={13}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search known flags"/></label><small>RESULTS <b>{results.length}</b></small>{results.map(flag=><button key={flag[0]}><code>{flag[0]}</code><em>{flag[1]}</em><Icon name="plus" size={10}/></button>)}</section><article><div><span><small>CONFIGURATION</small><h3>Your FastFlags</h3></span><button><Icon name="plus" size={11}/> Add flag</button></div>{results.slice(0,4).map((flag,index)=><p key={flag[0]}><span>{index<2&&<Icon name="check" size={9}/>}</span><code>{flag[0]}</code><em>{flag[1]}</em><b>{flag[2]}</b></p>)}<footer><button>Import JSON</button><button>Apply Flags</button></footer></article></div>}
      {tab==='Presets'&&<EmptyView icon="list" title="Preset library" text="Organize configurations by game, device, or goal."/>}
      {tab==='Console'&&<div className="console"><p><span>[13:45:17]</span> Meow Ware v1.3 initialized.</p><p><span>[13:45:18]</span> Loaded 14,265 known flags.</p><p><span>[13:45:18]</span> Theme and workspace restored.</p><p><span>[ready]</span> Waiting for a Roblox client.</p></div>}
      {tab==='Themes'&&<EmptyView icon="settings" title="Theme studio" text="Palettes, backgrounds, SVG icons, CSS, and per-button shapes."><div className="demo-swatches"><i/><i/><i/><i/></div></EmptyView>}
    </main></div>
    <footer>{tabs.map(([icon,label])=><button key={label} className={tab===label?'active':''} onClick={()=>setTab(label)}><Icon name={icon} size={13}/>{label}</button>)}<i/><span><i/> Injector idle</span></footer>
  </div>;
}
