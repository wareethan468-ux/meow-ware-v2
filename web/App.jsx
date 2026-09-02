import { useCallback, useEffect, useRef, useState } from 'react';
import BottomNavBar from './components/BottomNavBar';
import DiscordAuthModal from './components/DiscordAuthModal';
import { TermsModal } from './components/LegalAndUpdates';
import NotificationModal from './components/NotificationModal';
import TerminalDrawer from './components/TerminalDrawer';
import TitleBar from './components/TitleBar';
import ConsoleView from './views/ConsoleView';
import FlagsView from './views/FlagsView';
import PresetsView from './views/PresetsView';
import SettingsView from './views/SettingsView';
import OffsetsView from './views/OffsetsView';
import SourcesView from './views/SourcesView';
import ThemesView from './views/ThemesView';
import AssetProxyView from './views/AssetProxyView';
import ScraperView from './views/ScraperView';
import ProxySettingsView from './views/ProxySettingsView';
import ProxyTrafficView from './views/ProxyTrafficView';
import ExecutorView from './views/ExecutorView';
import Modal from './components/Modal';
import { Icon } from './components/Icons';
import { callDesktop, hasDesktopApi } from './lib/desktopApi';
import { applyTheme, cacheTheme, loadCachedTheme } from './lib/theme';

const views = { flags: FlagsView, presets: PresetsView, console: ConsoleView, settings: SettingsView, offsets: OffsetsView, sources: SourcesView, themes: ThemesView, assetProxy: AssetProxyView, scraper: ScraperView, proxyTraffic: ProxyTrafficView, proxyThemes: ThemesView, proxySettings: ProxySettingsView, executor: ExecutorView };

import ResizeHandles from './components/ResizeHandles';
import KeyVerificationModal from './components/KeyVerificationModal';

export default function App() {
  const [activeView, setActiveView] = useState('flags');
  const [product, setProduct] = useState('injector');
  const [flags, setFlags] = useState([]);
  const [notification, setNotification] = useState({ data: null, visible: false, closing: false });
  const [terminalOpen, setTerminalOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [keyModalOpen, setKeyModalOpen] = useState(false);
  const [keyNotice, setKeyNotice] = useState('');
  const [currentDiscordUser, setCurrentDiscordUser] = useState(null);
  const [termsModalOpen, setTermsModalOpen] = useState(false);
  const [proxyAdminPrompt, setProxyAdminPrompt] = useState(false);
  const [capabilities, setCapabilities] = useState({});
  const notifTimer = useRef();
  const exitTimer = useRef();

  useEffect(() => {
    const loadCapabilities = async () => {
      const value = await callDesktop('get_platform_capabilities');
      if (value) setCapabilities(value);
    };
    if (hasDesktopApi()) loadCapabilities();
    else window.addEventListener('pywebviewready', loadCapabilities, { once: true });
    return () => window.removeEventListener('pywebviewready', loadCapabilities);
  }, []);

  const dismissNotification = useCallback(() => {
    clearTimeout(notifTimer.current);
    setNotification(cur => ({ ...cur, closing: true }));
    exitTimer.current = setTimeout(() => {
      setNotification({ data: null, visible: false, closing: false });
    }, 220);
  }, []);

  const notify = useCallback((payload = 'Done') => {
    clearTimeout(notifTimer.current);
    clearTimeout(exitTimer.current);
    setNotification({ data: payload, visible: true, closing: false });
    notifTimer.current = setTimeout(() => {
      dismissNotification();
    }, 3200);
  }, [dismissNotification]);

  const refreshFlags = useCallback(async () => {
    const rows = await callDesktop('get_user_flags');
    if (!rows) return 0;
    setFlags(rows.map(flag => [flag.name, String(flag.value)]));
    return rows.length;
  }, []);

  useEffect(() => {
    const cached = loadCachedTheme();
    if (cached) applyTheme(cached);
    const loadTheme = async () => {
      const settings = await callDesktop('get_settings');
      if (settings) {
        const theme = { preset: settings.theme_preset, colors: settings.custom_theme_colors, customCss: settings.custom_css, background: settings.theme_background, buttonStyles: settings.theme_button_styles };
        applyTheme(theme);
        cacheTheme(theme);
      }
    };
    const handleDesktopReady = () => loadTheme();
    if (hasDesktopApi()) loadTheme();
    else window.addEventListener('pywebviewready', handleDesktopReady);
    window.addEventListener('meowware:theme_change', loadTheme);
    return () => {
      window.removeEventListener('pywebviewready', handleDesktopReady);
      window.removeEventListener('meowware:theme_change', loadTheme);
    };
  }, []);

  useEffect(() => {
    const ready = async () => {
      const count = await refreshFlags();
      if (count) notify(`Loaded ${count} flags`);
    };
    window.addEventListener('pywebviewready', ready);
    if (hasDesktopApi()) ready();
    window.refreshConfig = refreshFlags;
    return () => {
      window.removeEventListener('pywebviewready', ready);
      clearTimeout(notifTimer.current);
      delete window.refreshConfig;
    };
  }, [notify, refreshFlags]);

  // Check persistent auth state (Discord login + Terms accepted + License key) every 10s
  useEffect(() => {
    const evaluateState = async () => {
      if (hasDesktopApi()) {
        const state = await callDesktop('get_auth_state');
        if (state?.discord_user) setCurrentDiscordUser(state.discord_user);

        if (state?.authenticated) {
          setAuthOpen(false);
          setKeyModalOpen(false);
          setKeyNotice('');
          window.dispatchEvent(new CustomEvent('meowware:auth_change', { detail: state }));
        } else if (!state?.terms_accepted || !state?.discord_user) {
          setAuthOpen(true);
          setKeyModalOpen(false);
        } else {
          // Key is missing or expired
          setAuthOpen(false);
          setKeyNotice('Your license key has expired or is invalid. Please enter a valid key from /getkey.');
          setKeyModalOpen(true);
        }
      }
    };

    if (hasDesktopApi()) {
      evaluateState();
    } else {
      window.addEventListener('pywebviewready', evaluateState, { once: true });
      setTimeout(evaluateState, 350);
    }

    // Watchdog checking every 10 seconds
    const interval = setInterval(() => {
      evaluateState();
    }, 10000);

    const showTerms = () => setTermsModalOpen(true);
    const handleLogoutEvent = () => {
      setAuthOpen(true);
      setKeyModalOpen(false);
      notify('Logged out from Discord');
    };
    const handleRequireAuth = () => {
      setKeyNotice('An active license key is required to perform this action.');
      setKeyModalOpen(true);
    };

    window.addEventListener('vellium:show-terms', showTerms);
    window.addEventListener('meowware:logout', handleLogoutEvent);
    window.addEventListener('meowware:require_auth', handleRequireAuth);
    return () => {
      clearInterval(interval);
      window.removeEventListener('vellium:show-terms', showTerms);
      window.removeEventListener('meowware:logout', handleLogoutEvent);
      window.removeEventListener('meowware:require_auth', handleRequireAuth);
    };
  }, [notify]);

  const handleAuthNext = (authPayload) => {
    setAuthOpen(false);
    if (authPayload?.discord_user) setCurrentDiscordUser(authPayload.discord_user);
    setKeyNotice('');
    setKeyModalOpen(true);
  };

  const handleKeyVerified = (keyPayload) => {
    setKeyModalOpen(false);
    setKeyNotice('');
    window.dispatchEvent(new CustomEvent('meowware:auth_change', { detail: keyPayload }));
    notify('License activated — Welcome to Vellium Tweaker!');
  };

  const View = views[activeView];
  return (
    <main className="stage">
      <div className="theme-background" aria-hidden="true" />
      <ResizeHandles />
      <section className="app-window" aria-label="Vellium FastFlag Injector">
        <TitleBar />
        <div className="workspace-shell">
          <div className="content"><View flags={flags} refreshFlags={refreshFlags} notify={notify} onNavigate={setActiveView} product={product} proxyMode={product === 'proxy'} /></div>
          <TerminalDrawer open={terminalOpen} onClose={() => setTerminalOpen(false)} />
        </div>
        <BottomNavBar activeView={activeView} onChange={setActiveView} product={product} capabilities={capabilities} onProductChange={async(next) => { if(next !== 'injector' && capabilities[next] === false){notify({title:'Only available on Windows',message:`${next === 'proxy' ? 'Vellium Proxy' : 'Vellium Executor'} is not available on macOS. FastFlag Injector remains available.`,type:'error'});return} setProduct(next); setActiveView(next === 'proxy' ? 'assetProxy' : next === 'executor' ? 'executor' : 'flags'); if(next === 'proxy'&&!sessionStorage.getItem('vellium.adminPrompted')){const result=await callDesktop('get_proxy_settings');if(result&&!result.is_admin&&result.settings?.run_as_admin){sessionStorage.setItem('vellium.adminPrompted','1');setProxyAdminPrompt(true)}} }} terminalOpen={terminalOpen} onToggleTerminal={() => setTerminalOpen(value => !value)} />
        <NotificationModal notification={notification} onClose={dismissNotification} />
        <DiscordAuthModal open={authOpen} onAuthenticated={handleAuthNext} />
        <KeyVerificationModal
          open={keyModalOpen}
          notice={keyNotice}
          discordUser={currentDiscordUser}
          onKeyVerified={handleKeyVerified}
          onBackToAuth={() => {
            setKeyModalOpen(false);
            setAuthOpen(true);
          }}
        />
        <TermsModal open={termsModalOpen} required={false} onAccept={() => setTermsModalOpen(false)} onClose={() => setTermsModalOpen(false)} />
        <Modal open={proxyAdminPrompt} onClose={()=>setProxyAdminPrompt(false)} title="Administrator access required" subtitle="Vellium Proxy needs elevated network access" width="430px" footer={<><button className="btn" onClick={async()=>{await callDesktop('set_proxy_setting','run_as_admin',false);setProxyAdminPrompt(false);notify('Administrator launch disabled')}}>Continue without admin</button><button className="btn primary" onClick={()=>setProxyAdminPrompt(false)}><Icon name="shield" size={13}/>Use administrator mode</button></>}><p className="modal-body-text">The app is running as a standard user. When you start Vellium Proxy, Windows will show a UAC prompt and launch the proxy runtime as administrator.</p></Modal>
      </section>
    </main>
  );
}
