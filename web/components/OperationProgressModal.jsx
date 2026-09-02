import { useEffect, useState } from 'react';
import Modal from './Modal';

export default function OperationProgressModal({
  open,
  title = 'Processing...',
  subtitle = 'Please wait while Vellium Tweaker completes the operation',
  steps = ['Initializing...', 'Processing request...', 'Finalizing...'],
  onComplete,
}) {
  const [progress, setProgress] = useState(0);
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    if (!open) {
      setProgress(0);
      setStepIndex(0);
      return;
    }

    // Smooth progressive percentage progression
    let currentPct = 8;
    setProgress(currentPct);
    setStepIndex(0);

    const stepInterval = Math.max(250, Math.floor(1800 / (steps.length || 1)));

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 92) return prev; // wait for actual finish
        const increment = Math.floor(Math.random() * 12) + 6;
        const next = Math.min(92, prev + increment);
        const nextStep = Math.min(
          steps.length - 1,
          Math.floor((next / 92) * steps.length)
        );
        setStepIndex(nextStep);
        return next;
      });
    }, 120);

    return () => clearInterval(interval);
  }, [open, steps]);

  // SVG circle calculations
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (progress / 100) * circumference;

  return (
    <Modal
      open={open}
      onClose={() => {}}
      title=""
      width="380px"
      footer={null}
    >
      <div className="op-progress-container">
        {/* Animated Glow Progress Ring */}
        <div className="op-ring-wrapper">
          <svg className="op-ring-svg" width="96" height="96" viewBox="0 0 96 96">
            <circle
              className="op-ring-bg"
              cx="48"
              cy="48"
              r={radius}
              strokeWidth="6"
            />
            <circle
              className="op-ring-fill"
              cx="48"
              cy="48"
              r={radius}
              strokeWidth="6"
              style={{
                strokeDasharray: circumference,
                strokeDashoffset: strokeDashoffset,
              }}
            />
          </svg>
          <div className="op-ring-inner">
            <span className="op-ring-pct">{Math.round(progress)}%</span>
          </div>
        </div>

        {/* Operation Title & Dynamic Status Words */}
        <div className="op-text-block">
          <h3 className="op-title">{title}</h3>
          <p className="op-subtitle">{subtitle}</p>
          <div className="op-step-badge">
            <span className="op-step-pulse" />
            <span className="op-step-text">{steps[stepIndex] || steps[0]}</span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="op-bar-track">
          <div
            className="op-bar-fill"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    </Modal>
  );
}
