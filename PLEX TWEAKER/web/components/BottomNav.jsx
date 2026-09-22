import { Icon } from './Icons';

const tabs = [
  ['flags',    'layers',   'FastFlags'],
  ['presets',  'list',     'Presets'],
  ['console',  'terminal', 'Console'],
  ['settings', 'settings', 'Settings'],
];

export default function BottomNav({ activeView, onChange }) {
  return (
    <nav className="bottom-nav" aria-label="Main navigation">
      {tabs.map(([id, icon, label]) => (
        <button
          key={id}
          className={`nav-tab${activeView === id ? ' active' : ''}`}
          onClick={() => onChange(id)}
          aria-label={label}
          aria-current={activeView === id ? 'page' : undefined}
        >
          <Icon name={icon} size={16} />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
