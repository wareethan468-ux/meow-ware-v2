export default function Checkbox({
  checked = false,
  onChange,
  label,
  ariaLabel,
  disabled = false,
  indeterminate = false,
  children,
  className = '',
}) {
  const visibleText = children || (ariaLabel ? null : label);
  const accessibleLabel = ariaLabel || (typeof label === 'string' ? label : undefined);

  const cls = ['checkbox', checked && 'checked', indeterminate && 'indeterminate', disabled && 'disabled', className]
    .filter(Boolean).join(' ');

  return (
    <button
      type="button"
      className={cls}
      role="checkbox"
      aria-checked={indeterminate ? 'mixed' : checked}
      aria-label={accessibleLabel}
      onClick={() => !disabled && onChange?.(!checked)}
      onKeyDown={e => (e.key === ' ' || e.key === 'Enter') && e.preventDefault() || (!disabled && onChange?.(!checked))}
    >
      <span className="cb-box">
        {checked && !indeterminate && (
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        )}
        {indeterminate && (
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round">
            <path d="M5 12h14" />
          </svg>
        )}
      </span>
      {visibleText && (
        <span className="cb-label">{visibleText}</span>
      )}
    </button>
  );
}
