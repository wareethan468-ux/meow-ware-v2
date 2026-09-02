import { useEffect, useState } from 'react';
import { Icon } from './Icons';

export function parseNotification(input) {
  if (typeof input === 'object' && input !== null) {
    return {
      title: input.title || (input.type === 'error' ? 'Operation Failed' : 'Success'),
      message: input.message || '',
      type: input.type || 'info',
    };
  }

  const text = String(input || 'Done');
  const lower = text.toLowerCase();

  let type = 'success';
  let title = 'Success';

  if (lower.includes('fail') || lower.includes('error') || lower.includes('invalid') || lower.includes('could not')) {
    type = 'error';
    title = 'Operation Failed';
  } else if (lower.includes('clear') || lower.includes('uninject') || lower.includes('remove') || lower.includes('log out') || lower.includes('logged out')) {
    type = 'warning';
    title = lower.includes('clear') ? 'Workspace Cleared' : lower.includes('uninject') ? 'Flags Uninjected' : lower.includes('remove') ? 'Flag Removed' : 'Notice';
  } else if (lower.includes('import')) {
    type = 'success';
    title = 'Flags Imported';
  } else if (lower.includes('export')) {
    type = 'success';
    title = 'Flags Exported';
  } else if (lower.includes('applied') || lower.includes('inject')) {
    type = 'success';
    title = 'FastFlags Applied';
  } else if (lower.includes('welcome') || lower.includes('connect')) {
    type = 'info';
    title = 'Vellium Tweaker';
  } else if (lower.includes('loaded')) {
    type = 'info';
    title = 'Data Loaded';
  } else if (lower.includes('launch')) {
    type = 'info';
    title = 'Launching Roblox';
  }

  return { title, message: text, type };
}

export default function NotificationModal({
  notification,
  onClose,
}) {
  if (!notification || !notification.visible) return null;

  const { title, message, type } = parseNotification(notification.data);
  const closing = notification.closing;

  const iconName = type === 'success' ? 'check' : type === 'error' ? 'x' : type === 'warning' ? 'alert' : 'info';

  return (
    <div className={`notif-card-wrap${closing ? ' out' : ' in'}`} role="alert">
      <div className={`notif-card ${type}`}>
        <div className={`notif-icon-badge ${type}`}>
          <Icon name={iconName} size={15} />
        </div>
        <div className="notif-content">
          <strong className="notif-title">{title}</strong>
          <span className="notif-msg">{message}</span>
        </div>
        <button
          type="button"
          className="notif-close-btn"
          onClick={onClose}
          aria-label="Dismiss notification"
        >
          <Icon name="x" size={12} />
        </button>
      </div>
    </div>
  );
}
