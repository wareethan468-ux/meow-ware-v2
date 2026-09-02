import { useRef } from 'react';
import { Icon } from './Icons';

export default function RangeSlider({ label, value, min=0, max=100, suffix='', onChange }) {
  const trackRef=useRef(null);
  const percent=((value-min)/(max-min))*100;
  const update=event=>{const rect=trackRef.current?.getBoundingClientRect();if(!rect)return;const ratio=Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width));onChange(Math.round(min+ratio*(max-min)))};
  const step=amount=>onChange(Math.max(min,Math.min(max,value+amount)));
  return <div className="custom-range"><div className="custom-range-head"><span>{label}</span><b>{value}{suffix}</b></div><div className="custom-range-row"><button type="button" onClick={()=>step(-1)} aria-label={`Decrease ${label}`}><Icon name="minus" size={10}/></button><div ref={trackRef} className="custom-range-track" role="slider" tabIndex={0} aria-label={label} aria-valuemin={min} aria-valuemax={max} aria-valuenow={value} onPointerDown={event=>{event.currentTarget.setPointerCapture(event.pointerId);update(event)}} onPointerMove={event=>event.buttons===1&&update(event)} onKeyDown={event=>{if(event.key==='ArrowLeft'||event.key==='ArrowDown')step(-1);if(event.key==='ArrowRight'||event.key==='ArrowUp')step(1)}}><i style={{width:`${percent}%`}}/><em style={{left:`${percent}%`}}/></div><button type="button" onClick={()=>step(1)} aria-label={`Increase ${label}`}><Icon name="plus" size={10}/></button></div></div>;
}
