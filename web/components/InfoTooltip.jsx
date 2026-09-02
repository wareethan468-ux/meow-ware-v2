import { cloneElement, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export default function InfoTooltip({ children, content, width = 290 }) {
  const anchorRef = useRef(null);
  const openTimer = useRef(null);
  const closeTimer = useRef(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0, side: 'right' });

  const cancel = timer => { if (timer.current) window.clearTimeout(timer.current); timer.current = null; };
  const place = () => {
    const rect = anchorRef.current?.getBoundingClientRect();
    if (!rect) return;
    const spaceRight = window.innerWidth - rect.right;
    const side = spaceRight >= width + 16 ? 'right' : 'left';
    const left = side === 'right' ? rect.right + 8 : Math.max(8, rect.left - width - 8);
    const top = Math.min(Math.max(8, rect.top - 8), window.innerHeight - 210);
    setPosition({ left, top, side });
  };
  const requestOpen = () => {
    cancel(closeTimer);
    if (open) return;
    cancel(openTimer);
    openTimer.current = window.setTimeout(() => { place(); setOpen(true); }, 260);
  };
  const requestClose = () => {
    cancel(openTimer);
    cancel(closeTimer);
    closeTimer.current = window.setTimeout(() => setOpen(false), 220);
  };

  useEffect(() => {
    if (!open) return undefined;
    const reposition = () => place();
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);
    return () => {
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', reposition, true);
    };
  }, [open]);
  useEffect(() => () => { cancel(openTimer); cancel(closeTimer); }, []);

  return <>
    <span ref={anchorRef} className="info-tooltip-anchor" onPointerEnter={requestOpen} onPointerLeave={requestClose} onFocusCapture={requestOpen} onBlurCapture={requestClose}>
      {cloneElement(children, { 'aria-describedby': open ? 'active-info-tooltip' : undefined })}
    </span>
    {open && createPortal(
      <aside id="active-info-tooltip" role="tooltip" className={`info-tooltip info-tooltip-${position.side}`} style={{ left: position.left, top: position.top, width }} onPointerEnter={() => cancel(closeTimer)} onPointerLeave={requestClose}>
        {content}
      </aside>, document.body)}
  </>;
}
