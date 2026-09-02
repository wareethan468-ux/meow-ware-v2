import { useEffect, useRef, useState } from 'react';
import { Icon } from './Icons';

export default function Modal({ open, onClose, title, subtitle, width = '420px', children, footer, tone = '' }) {
  const [mounted, setMounted] = useState(false);
  const [closing, setClosing] = useState(false);
  const ref = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    if (open) {
      clearTimeout(timerRef.current);
      setMounted(true);
      setClosing(false);
    } else if (mounted) {
      setClosing(true);
      timerRef.current = setTimeout(() => {
        setMounted(false);
        setClosing(false);
      }, 240);
    }
    return () => clearTimeout(timerRef.current);
  }, [open]);

  useEffect(() => {
    if (!mounted || closing) return;
    const h = e => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', h);
    return () => document.removeEventListener('keydown', h);
  }, [mounted, closing, onClose]);

  useEffect(() => {
    if (mounted && !closing && ref.current) {
      const el = ref.current.querySelector('input, select, textarea, button:not(.modal-x)');
      el?.focus();
    }
  }, [mounted, closing]);

  if (!mounted) return null;

  return (
    <div
      className={`modal-overlay${closing ? ' out' : ' in'}`}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={`modal-box${tone ? ` tone-${tone}` : ''}${closing ? ' out' : ' in'}`}
        style={{ maxWidth: width }}
        onClick={e => e.stopPropagation()}
        ref={ref}
      >
        <div className="modal-hd">
          <div>
            <div className="modal-title">{title}</div>
            {subtitle && <div className="modal-subtitle">{subtitle}</div>}
          </div>
          <button className="modal-x" onClick={onClose} aria-label="Close">
            <Icon name="x" size={14} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
