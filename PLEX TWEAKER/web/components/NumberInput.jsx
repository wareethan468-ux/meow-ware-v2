import { useState, useEffect } from 'react';

export default function NumberInput({
  value,
  onChange,
  onCommit,
  placeholder = '0',
  step = 1,
  min,
  max,
  className = '',
  onKeyDown,
  autoFocus = false,
}) {
  const [val, setVal] = useState(value !== undefined && value !== null ? String(value) : '');

  useEffect(() => {
    setVal(value !== undefined && value !== null ? String(value) : '');
  }, [value]);

  const handleChange = (e) => {
    const next = e.target.value;
    setVal(next);
    onChange?.(next);
  };

  const handleBlur = () => {
    onCommit?.(val);
  };

  const stepUp = () => {
    const num = Number(val || 0);
    const next = isNaN(num) ? step : num + step;
    const clamped = max !== undefined ? Math.min(max, next) : next;
    const s = String(clamped);
    setVal(s);
    onChange?.(s);
    onCommit?.(s);
  };

  const stepDown = () => {
    const num = Number(val || 0);
    const next = isNaN(num) ? -step : num - step;
    const clamped = min !== undefined ? Math.max(min, next) : next;
    const s = String(clamped);
    setVal(s);
    onChange?.(s);
    onCommit?.(s);
  };

  return (
    <div className={`number-input-wrap ${className}`}>
      <input
        type="number"
        className="input number-input-field"
        value={val}
        placeholder={placeholder}
        onChange={handleChange}
        onBlur={handleBlur}
        autoFocus={autoFocus}
        onKeyDown={e => {
          if (e.key === 'ArrowUp') {
            e.preventDefault();
            stepUp();
          } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            stepDown();
          }
          onKeyDown?.(e);
        }}
      />
      <div className="number-steppers">
        <button type="button" tabIndex={-1} className="stepper-btn stepper-up" onClick={stepUp} title="Increment">
          <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="18 15 12 9 6 15"></polyline>
          </svg>
        </button>
        <button type="button" tabIndex={-1} className="stepper-btn stepper-down" onClick={stepDown} title="Decrement">
          <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </button>
      </div>
    </div>
  );
}
