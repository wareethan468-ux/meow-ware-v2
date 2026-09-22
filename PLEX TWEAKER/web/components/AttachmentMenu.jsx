import { useEffect, useRef } from 'react';
import { Icon } from './Icons';

export default function AttachmentMenu({
  open,
  processes = [],
  selectedPid = 0,
  attached = false,
  busyPid = 0,
  error = '',
  onChoose,
  onDetach,
  onEndProcess,
  onClose,
}) {
  const menuRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        onClose?.();
      }
    };
    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="apm-card" ref={menuRef} role="dialog" aria-label="Roblox Attachment Targets">

      {/* Header */}
      <div className="apm-header">
        <div className="apm-header-left">
          <div className="apm-status-dot" data-connected={attached} />
          <div>
            <div className="apm-title">Roblox Attachment</div>
            <div className="apm-subtitle">
              {processes.length
                ? `${processes.length} client${processes.length > 1 ? 's' : ''} running`
                : 'No client detected'}
            </div>
          </div>
        </div>
        <span className="apm-state-badge" data-connected={attached}>
          {attached ? 'Active' : 'Idle'}
        </span>
      </div>

      {/* Error */}
      {error && (
        <div className="apm-error">
          <Icon name="alert" size={11} />
          <span>{error}</span>
        </div>
      )}

      {/* Process list */}
      <div className="apm-body">
        {processes.length === 0 ? (
          <div className="apm-empty">
            <div className="apm-empty-icon">
              <Icon name="roblox" size={18} />
            </div>
            <span className="apm-empty-label">No Roblox client found</span>
            <span className="apm-empty-hint">Launch Roblox to begin injection</span>
          </div>
        ) : (
          <div className="apm-list">
            {processes.map((proc) => {
              const isSelected = proc.attached || proc.pid === selectedPid;
              const isBusy = busyPid === proc.pid;

              return (
                <button
                  key={proc.pid}
                  type="button"
                  className={`apm-process${isSelected ? ' is-active' : ''}`}
                  onClick={() => onChoose?.(proc.pid)}
                  disabled={busyPid !== 0}
                >
                  <div className="apm-proc-icon">
                    <Icon name="roblox" size={14} />
                  </div>
                  <div className="apm-proc-info">
                    <span className="apm-proc-name">RobloxPlayerBeta.exe</span>
                    <span className="apm-proc-pid">PID {proc.pid}</span>
                  </div>
                  <div className="apm-proc-right">
                    {isBusy
                      ? <div className="apm-spinner" />
                      : isSelected
                        ? <span className="apm-proc-check"><Icon name="check" size={10} /> Connected</span>
                        : <span className="apm-proc-attach">Attach</span>}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer actions */}
      {attached && (
        <div className="apm-footer">
          <button
            type="button"
            className="apm-btn apm-btn--ghost"
            disabled={busyPid !== 0}
            onClick={onDetach}
          >
            <Icon name="logout" size={12} />
            Detach
          </button>
          <button
            type="button"
            className="apm-btn apm-btn--danger"
            disabled={busyPid !== 0}
            onClick={() => onEndProcess?.(selectedPid)}
          >
            <Icon name="power" size={12} />
            End Client
          </button>
        </div>
      )}
    </div>
  );
}
