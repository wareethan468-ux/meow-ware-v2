export const THEME_PRESETS = {
  graphite: { label: 'Graphite', bg: '#050505', panel: '#090909', raised: '#161616', accent: '#f5f5f5', text: '#e2e2e8', border:'#35353b', success:'#10b981', warning:'#f59e0b', danger:'#ef4444' },
  violet:   { label: 'Violet',   bg: '#08060d', panel: '#0e0a16', raised: '#191126', accent: '#a878ff', text: '#eee9f8', border:'#372b49', success:'#52d69a', warning:'#e9ad55', danger:'#f06f88' },
  ocean:    { label: 'Ocean',    bg: '#05090c', panel: '#081117', raised: '#10212b', accent: '#55b9ef', text: '#e5f2f8', border:'#203b49', success:'#49c993', warning:'#e1a84f', danger:'#ed6e73' },
  forest:   { label: 'Forest',   bg: '#050907', panel: '#09110d', raised: '#122019', accent: '#66d49a', text: '#e6f3eb', border:'#294335', success:'#66d49a', warning:'#d7aa55', danger:'#e46f6f' },
  ember:    { label: 'Ember',    bg: '#0b0705', panel: '#130c08', raised: '#25150d', accent: '#f29a62', text: '#f4ebe5', border:'#4a2c1c', success:'#70c991', warning:'#f0a451', danger:'#ed675d' },
};

const rgba = (hex, alpha) => {
  if (hex === 'transparent') return 'rgba(0,0,0,0)';
  const clean = String(hex || '').replace('#', '');
  if (!/^[0-9a-f]{6}$/i.test(clean)) return `rgba(255,255,255,${alpha})`;
  const value = Number.parseInt(clean, 16);
  return `rgba(${value >> 16},${(value >> 8) & 255},${value & 255},${alpha})`;
};

export function applyTheme({ preset = 'graphite', colors = {}, customCss = '', background = {}, buttonStyles = {} } = {}) {
  const base = THEME_PRESETS[preset] || THEME_PRESETS.graphite;
  const theme = preset === 'custom' ? { ...THEME_PRESETS.graphite, ...colors } : base;
  const root = document.documentElement;
  root.dataset.theme = preset;
  root.style.setProperty('--bg', theme.bg);
  root.style.setProperty('--bg-1', theme.panel);
  root.style.setProperty('--bg-2', theme.raised);
  root.style.setProperty('--bg-3', theme.raised);
  root.style.setProperty('--bg-hover', theme.raised);
  root.style.setProperty('--surface-glass', rgba(theme.panel, .92));
  root.style.setProperty('--surface-soft', rgba(theme.raised, .78));
  root.style.setProperty('--purple', theme.accent);
  root.style.setProperty('--purple-hi', theme.accent);
  root.style.setProperty('--purple-lo', theme.accent);
  root.style.setProperty('--purple-bg', rgba(theme.accent, .09));
  root.style.setProperty('--purple-bd', rgba(theme.accent, .34));
  root.style.setProperty('--text', theme.text);
  root.style.setProperty('--text-2', rgba(theme.text, .68));
  root.style.setProperty('--text-3', rgba(theme.text, .38));
  root.style.setProperty('--line', rgba(theme.border, .45));
  root.style.setProperty('--line-2', rgba(theme.border, .78));
  root.style.setProperty('--hover-soft', rgba(theme.text, .035));
  root.style.setProperty('--hover-strong', rgba(theme.text, .075));
  root.style.setProperty('--success', theme.success);
  root.style.setProperty('--success-bg', rgba(theme.success, .12));
  root.style.setProperty('--success-bd', rgba(theme.success, .28));
  root.style.setProperty('--warning', theme.warning);
  root.style.setProperty('--warning-bg', rgba(theme.warning, .13));
  root.style.setProperty('--warning-bd', rgba(theme.warning, .3));
  root.style.setProperty('--danger', theme.danger);
  root.style.setProperty('--danger-bg', rgba(theme.danger, .12));
  root.style.setProperty('--danger-bd', rgba(theme.danger, .3));
  root.style.setProperty('--red', theme.danger);
  root.style.setProperty('--red-bg', rgba(theme.danger, .1));
  root.style.setProperty('--red-bd', rgba(theme.danger, .28));
  const backgroundMode = ['none','aurora','mesh','grid','stars','custom'].includes(background.mode) ? background.mode : 'none';
  root.dataset.background = backgroundMode;
  root.style.setProperty('--background-opacity', `${Math.max(0, Math.min(100, Number(background.opacity) || 35)) / 100}`);
  root.style.setProperty('--background-speed', `${Math.max(1, 11 - (Number(background.speed) || 5)) * 4}s`);
  const safeSource = String(background.render_source || background.source || '').replace(/["\\\n\r]/g, '');
  root.style.setProperty('--theme-background-image', safeSource ? `url("${safeSource}")` : 'none');
  const radii = { pill: '9999px', rounded: '8px', square: '3px', rectangle: '0px' };
  const globalShape = radii[buttonStyles.global] ? buttonStyles.global : 'pill';
  const resolveRadius = key => radii[buttonStyles[key]] || radii[globalShape];
  root.style.setProperty('--button-radius', radii[globalShape]);
  root.style.setProperty('--primary-button-radius', resolveRadius('primary'));
  root.style.setProperty('--secondary-button-radius', resolveRadius('secondary'));
  root.style.setProperty('--icon-button-radius', resolveRadius('icon'));
  root.style.setProperty('--nav-button-radius', resolveRadius('nav'));

  let customStyle = document.getElementById('meow-custom-theme-css');
  if (!customStyle) {
    customStyle = document.createElement('style');
    customStyle.id = 'meow-custom-theme-css';
    document.head.appendChild(customStyle);
  }
  customStyle.textContent = String(customCss || '').slice(0, 20000);
}

export function cacheTheme(theme) {
  try {
    const cached = { ...theme, background: { ...(theme?.background || {}) } };
    delete cached.background.render_source;
    window.localStorage.setItem('meowware-theme', JSON.stringify(cached));
  } catch { /* storage may be unavailable */ }
}

export function loadCachedTheme() {
  try {
    const cached = JSON.parse(window.localStorage.getItem('meowware-theme') || 'null');
    return cached && typeof cached === 'object' ? cached : null;
  } catch {
    return null;
  }
}
