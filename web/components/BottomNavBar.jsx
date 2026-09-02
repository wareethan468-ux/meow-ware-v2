import { useEffect, useRef, useState } from 'react';
import { Icon } from './Icons';
import AttachmentStatus from './AttachmentStatus';

const navItems = [
  { id: 'flags', icon: 'layers', label: 'Flags' },
  { id: 'presets', icon: 'list', label: 'Presets' },
  { id: 'monitor', icon: 'activity', label: 'Monitor' },
  { id: 'console', icon: 'terminal', label: 'Console' },
  { id: 'offsets', icon: 'refresh', label: 'Offsets' },
  { id: 'sources', icon: 'copy', label: 'Sources' },
  { id: 'themes', icon: 'brush', label: 'Themes' },
  { id: 'settings', icon: 'settings', label: 'Settings' },
];

const proxyNav = [
  { id: 'assetProxy', icon: 'route', label: 'Replacements' },
  { id: 'scraper', icon: 'database', label: 'Scraper' },
  { id: 'proxyTraffic', icon: 'activity', label: 'Traffic' },
  { id: 'proxyThemes', icon: 'brush', label: 'Themes' },
  { id: 'proxySettings', icon: 'settings', label: 'Settings' },
];

const executorNav = [
  { id: 'executor', icon: 'code', label: 'Editor' },
  { id: 'console', icon: 'terminal', label: 'Console' },
  { id: 'themes', icon: 'brush', label: 'Themes' },
  { id: 'settings', icon: 'settings', label: 'Settings' },
];

const productIcons = { injector: 'box', proxy: 'route', executor: 'bolt' };

export default function BottomNavBar({ activeView, onChange, product, onProductChange, terminalOpen, onToggleTerminal, capabilities = {} }) {
  const [hoveredItem, setHoveredItem] = useState(null);
  const [productOpen, setProductOpen] = useState(false);
  const productRef = useRef(null);
  useEffect(() => {
    const close = event => { if (!productRef.current?.contains(event.target)) setProductOpen(false); };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, []);
  const visibleItems = product === 'proxy' ? proxyNav : product === 'executor' ? executorNav : navItems;

  return (
    <nav className="bottom-floating-nav" role="navigation" aria-label="Main Navigation">
      <div className="bottom-nav-oval">
        <div className={`product-switcher${productOpen ? ' open' : ''}`} ref={productRef}>
          <button type="button" className="product-switcher-trigger" onClick={() => setProductOpen(value => !value)} aria-haspopup="menu" aria-expanded={productOpen} title="Switch product">
            <Icon name={productIcons[product] ?? 'box'} size={15}/>
            <Icon name="chevron" size={10}/>
          </button>
          <div className={`product-switcher-menu${productOpen ? ' visible' : ''}`} role="menu">
            <span className="product-switcher-label">Product type</span>
            <button type="button" className={product === 'injector' ? 'selected' : ''} onClick={() => { onProductChange('injector'); setProductOpen(false); }}>
              <i><Icon name="layers" size={15}/></i><span><strong>FFlag Injector</strong><small>Configure and apply FastFlags</small></span>{product === 'injector' && <Icon name="check" size={14}/>}
            </button>
            <button type="button" className={product === 'proxy' ? 'selected' : ''} onClick={() => { onProductChange('proxy'); setProductOpen(false); }}>
              <i><Icon name="route" size={15}/></i><span><strong>Vellium Proxy</strong><small>{capabilities.proxy === false ? 'Only available on Windows' : 'Manage local asset replacements'}</small></span>{product === 'proxy' && <Icon name="check" size={14}/>} 
            </button>
            <button type="button" className={product === 'executor' ? 'selected' : ''} onClick={() => { onProductChange('executor'); setProductOpen(false); }}>
              <i><Icon name="bolt" size={15}/></i><span><strong>Vellium Executor</strong><small>{capabilities.executor === false ? 'Only available on Windows' : 'Run Lua scripts via QuorumAPI'}</small></span>{product === 'executor' && <Icon name="check" size={14}/>} 
            </button>
          </div>
        </div>
        <div className="bottom-nav-divider" />
        <div className="bottom-nav-items">
          {visibleItems.map((item) => {
            const isActive = activeView === item.id;
            const isHovered = hoveredItem === item.id;
            const showLabel = isActive || isHovered;

            return (
              <button
                key={item.id}
                type="button"
                className={`bottom-nav-btn${isActive ? ' active' : ''}`}
                onClick={() => onChange(item.id)}
                onMouseEnter={() => setHoveredItem(item.id)}
                onMouseLeave={() => setHoveredItem(null)}
                title={item.label}
                aria-label={item.label}
              >
                <div className="bottom-nav-icon-wrap">
                  <Icon name={item.icon} size={15} />
                </div>
                <div className={`bottom-nav-label-wrap${showLabel ? ' expanded' : ''}`}>
                  <span className="bottom-nav-label-text">{item.label}</span>
                </div>
                {isActive && <div className="bottom-nav-active-glow" />}
              </button>
            );
          })}
        </div>

        <div className="bottom-nav-divider" />

        <div className="bottom-nav-actions">
          <div className="bottom-nav-status-wrap">
            <AttachmentStatus product={product} />
          </div>

          <button
            type="button"
            className={`bottom-nav-btn terminal-btn${terminalOpen ? ' active' : ''}`}
            onClick={onToggleTerminal}
            title={terminalOpen ? 'Close Terminal' : 'Open Terminal'}
            aria-label="Toggle Terminal Drawer"
          >
            <div className="bottom-nav-icon-wrap">
              <Icon name="terminal" size={14} />
            </div>
            <div className={`bottom-nav-label-wrap${terminalOpen ? ' expanded' : ''}`}>
              <span className="bottom-nav-label-text">CLI</span>
            </div>
          </button>
        </div>
      </div>
    </nav>
  );
}
