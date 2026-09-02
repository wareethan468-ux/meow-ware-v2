import { useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from './Icons';

const hexToRgb = hex => { const clean=String(hex).replace('#',''); const n=/^[0-9a-f]{6}$/i.test(clean)?parseInt(clean,16):0; return {r:n>>16,g:(n>>8)&255,b:n&255}; };
const rgbToHex = ({r,g,b}) => `#${[r,g,b].map(v=>Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,'0')).join('')}`;
const rgbToHsv = ({r,g,b}) => { r/=255;g/=255;b/=255; const max=Math.max(r,g,b),min=Math.min(r,g,b),d=max-min; let h=0; if(d)h=max===r?60*(((g-b)/d)%6):max===g?60*((b-r)/d+2):60*((r-g)/d+4); return {h:(h+360)%360,s:max?d/max:0,v:max}; };
const hsvToRgb = ({h,s,v}) => { const c=v*s,x=c*(1-Math.abs((h/60)%2-1)),m=v-c; const [r,g,b]=h<60?[c,x,0]:h<120?[x,c,0]:h<180?[0,c,x]:h<240?[0,x,c]:h<300?[x,0,c]:[c,0,x]; return {r:(r+m)*255,g:(g+m)*255,b:(b+m)*255}; };

export default function ColorPicker({label,value,onChange,allowTransparent=false,fallback='#161616'}) {
  const [open,setOpen]=useState(false); const rootRef=useRef(null); const planeRef=useRef(null);
  const transparent=value==='transparent';
  const activeColor=transparent?fallback:value;
  const hsv=useMemo(()=>rgbToHsv(hexToRgb(activeColor)),[activeColor]);
  useEffect(()=>{const close=e=>!rootRef.current?.contains(e.target)&&setOpen(false);document.addEventListener('pointerdown',close);return()=>document.removeEventListener('pointerdown',close)},[]);
  const updatePlane=e=>{const rect=planeRef.current?.getBoundingClientRect();if(!rect)return;const s=Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width));const v=1-Math.max(0,Math.min(1,(e.clientY-rect.top)/rect.height));onChange(rgbToHex(hsvToRgb({h:hsv.h,s,v})));};
  const updateHex=next=>{const clean=next.replace(/[^0-9a-f]/gi,'').slice(0,6);if(clean.length===6)onChange(`#${clean}`);};
  return <div className="theme-color-picker" ref={rootRef}>
    <button type="button" className="theme-color-trigger" onClick={()=>setOpen(v=>!v)} aria-expanded={open}><i className={transparent?'transparent-swatch':''} style={{background:transparent?undefined:value}}/><span><small>{label}</small><strong>{transparent?'Transparent':value}</strong></span><Icon name="chevron" size={12}/></button>
    <div className={`theme-color-popover custom-picker${open?' is-visible':''}`} aria-hidden={!open}>
      {allowTransparent&&<div className="paint-mode-menu"><button type="button" className={!transparent?'active':''} onClick={()=>transparent&&onChange(fallback)}><Icon name="palette" size={14}/><span><strong>Color</strong><small>Use the color picker</small></span>{!transparent&&<Icon name="check" size={11}/>}</button><button type="button" className={transparent?'active':''} onClick={()=>onChange('transparent')}><Icon name="x" size={14}/><span><strong>Transparent</strong><small>Remove this surface color</small></span>{transparent&&<Icon name="check" size={11}/>}</button></div>}
      {!transparent&&<><div className="color-plane" ref={planeRef} style={{'--picker-hue':`hsl(${hsv.h} 100% 50%)`}} onPointerDown={e=>{e.currentTarget.setPointerCapture(e.pointerId);updatePlane(e)}} onPointerMove={e=>e.buttons===1&&updatePlane(e)}><i style={{left:`${hsv.s*100}%`,top:`${(1-hsv.v)*100}%`}}/></div><input className="color-hue" aria-label="Hue" type="range" min="0" max="360" value={Math.round(hsv.h)} onChange={e=>onChange(rgbToHex(hsvToRgb({...hsv,h:Number(e.target.value)})))}/><div className="color-picker-values"><span className="color-current" style={{background:value}}/><label className="theme-hex-field"><span>#</span><input value={value.replace('#','')} maxLength={6} onChange={e=>updateHex(e.target.value)}/></label></div></>}
    </div>
  </div>;
}
