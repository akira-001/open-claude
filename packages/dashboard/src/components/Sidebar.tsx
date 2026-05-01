import { useState, useEffect, useCallback } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import BotSelector from './BotSelector';
import { useI18n } from '../i18n';
import type { Lang } from '../i18n';
import { globalConfigEvents } from '../globalConfigEvents';

interface NavItem {
  to: string;
  labelKey: string;
}

interface NavSection {
  titleKey: string;
  items: NavItem[];
}

const sections: NavSection[] = [
  {
    titleKey: 'sidebar.dashboard',
    items: [
      { to: '/', labelKey: 'sidebar.overview' },
      { to: '/activity', labelKey: 'sidebar.activity' },
    ],
  },
  {
    titleKey: 'sidebar.botSettings',
    items: [
      { to: '/bot/personality', labelKey: 'sidebar.personality' },
      { to: '/bot/models', labelKey: 'sidebar.models' },
      { to: '/bot/proactive', labelKey: 'sidebar.proactive' },
      { to: '/bot/support-log', labelKey: 'sidebar.supportLog' },
      { to: '/bot/cron-jobs', labelKey: 'sidebar.cronJobs' },
      { to: '/bot/mcp-servers', labelKey: 'sidebar.mcpServers' },
    ],
  },
  {
    titleKey: 'sidebar.knowledge',
    items: [
      { to: '/insights', labelKey: 'sidebar.insights' },
      { to: '/weights', labelKey: 'sidebar.weights' },
      { to: '/constants', labelKey: 'sidebar.constants' },
      { to: '/profile', labelKey: 'sidebar.profile' },
      { to: '/thought-trace', labelKey: 'sidebar.thoughtTrace' },
    ],
  },
  {
    titleKey: 'sidebar.tools',
    items: [
      { to: '/ember-chat', labelKey: 'sidebar.emberChat' },
      { to: '/voice-enroll', labelKey: 'sidebar.voiceEnroll' },
    ],
  },
  {
    titleKey: 'sidebar.system',
    items: [
      { to: '/system/bots', labelKey: 'sidebar.botManagement' },
      { to: '/system/stamps', labelKey: 'sidebar.stamps' },
      { to: '/system/local-models', labelKey: 'sidebar.localModels' },
      { to: '/system/global', labelKey: 'sidebar.globalConfig' },
    ],
  },
];

export default function Sidebar() {
  const { lang, setLang, t } = useI18n();
  const [open, setOpen] = useState(false);
  const [hiddenRoutes, setHiddenRoutes] = useState<Set<string>>(new Set());
  const location = useLocation();

  const fetchHiddenRoutes = useCallback(() => {
    fetch('/api/global')
      .then((r) => r.json())
      .then((data) => {
        const hidden = new Set<string>();
        if (data.emberChatStandalone) hidden.add('/ember-chat');
        setHiddenRoutes(hidden);
      })
      .catch(() => {});
  }, []);

  useEffect(() => { fetchHiddenRoutes(); }, [fetchHiddenRoutes]);
  useEffect(() => { globalConfigEvents.subscribe(fetchHiddenRoutes); }, [fetchHiddenRoutes]);

  return (
    <>
      {/* Mobile hamburger */}
      <button
        onClick={() => setOpen(!open)}
        className="fixed top-3 left-3 z-50 md:hidden w-10 h-10 flex items-center justify-center rounded-lg bg-[var(--sidebar-bg)] text-[var(--sidebar-text-active)] border border-[var(--sidebar-border)]"
        aria-label="Toggle menu"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          {open ? (
            <><line x1="4" y1="4" x2="16" y2="16"/><line x1="16" y1="4" x2="4" y2="16"/></>
          ) : (
            <><line x1="3" y1="5" x2="17" y2="5"/><line x1="3" y1="10" x2="17" y2="10"/><line x1="3" y1="15" x2="17" y2="15"/></>
          )}
        </svg>
      </button>
      {/* Overlay */}
      {open && <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={() => setOpen(false)} />}
    <aside className={`fixed left-0 top-0 h-screen w-60 bg-[var(--sidebar-bg)] border-r border-[var(--sidebar-border)] flex flex-col z-40 transition-transform md:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}>
      <div className="px-5 py-4 border-b border-[var(--sidebar-border)] flex items-center gap-3">
        <svg viewBox="56 20 144 212" xmlns="http://www.w3.org/2000/svg" className="w-8 h-8 flex-shrink-0">
          <defs>
            <linearGradient id="sb-lo" x1="0.5" y1="1" x2="0.5" y2="0"><stop offset="0%" stopColor="#dc2626"/><stop offset="40%" stopColor="#ea580c"/><stop offset="70%" stopColor="#f97316"/><stop offset="100%" stopColor="#fb923c"/></linearGradient>
            <linearGradient id="sb-lm" x1="0.5" y1="1" x2="0.5" y2="0"><stop offset="0%" stopColor="#ea580c"/><stop offset="50%" stopColor="#f97316"/><stop offset="100%" stopColor="#fdba74"/></linearGradient>
            <linearGradient id="sb-li" x1="0.5" y1="1" x2="0.5" y2="0"><stop offset="0%" stopColor="#f97316"/><stop offset="40%" stopColor="#fbbf24"/><stop offset="100%" stopColor="#fde68a"/></linearGradient>
            <linearGradient id="sb-lc" x1="0.5" y1="1" x2="0.5" y2="0"><stop offset="0%" stopColor="#fbbf24"/><stop offset="100%" stopColor="#fef3c7"/></linearGradient>
          </defs>
          <path d="M128 28C128 28 188 80 192 140C194 165 182 192 164 208C158 213 148 220 128 224C108 220 98 213 92 208C74 192 62 165 64 140C68 80 128 28 128 28Z" fill="url(#sb-lo)"/>
          <path d="M128 60C128 60 172 104 174 148C175 168 166 190 152 204C144 210 136 216 128 218C120 216 112 210 104 204C90 190 81 168 82 148C84 104 128 60 128 60Z" fill="url(#sb-lm)"/>
          <path d="M128 96C128 96 158 128 160 158C161 172 154 190 144 200C140 204 134 208 128 210C122 208 116 204 112 200C102 190 95 172 96 158C98 128 128 96 128 96Z" fill="url(#sb-li)"/>
          <path d="M128 140C128 140 146 158 146 174C146 184 140 196 134 202C132 204 130 206 128 206C126 206 124 204 122 202C116 196 110 184 110 174C110 158 128 140 128 140Z" fill="url(#sb-lc)"/>
        </svg>
        <span className="text-sm font-semibold text-[var(--sidebar-text-active)]">Multi-Agent <span className="text-[var(--accent-light)]">Ember</span></span>
      </div>
      <BotSelector />
      <nav className="flex-1 py-2 overflow-y-auto">
        {sections.map((section) => {
          const visibleItems = section.items.filter((item) => !hiddenRoutes.has(item.to));
          if (visibleItems.length === 0) return null;
          return (
          <div key={section.titleKey} className="mb-1">
            <div className="px-5 py-2 text-[10px] uppercase tracking-wider text-[var(--text-dim)] font-medium">
              {t(section.titleKey as any)}
            </div>
            {visibleItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  `block px-5 py-2.5 text-sm transition-colors ${
                    isActive
                      ? 'bg-[var(--sidebar-active-bg)] text-[var(--sidebar-text-active)] border-l-2 border-[var(--sidebar-active-border)]'
                      : 'text-[var(--sidebar-text)] hover:text-[var(--sidebar-text-active)] hover:bg-[var(--sidebar-surface)] border-l-2 border-transparent'
                  }`
                }
              >
                {t(item.labelKey as any)}
              </NavLink>
            ))}
          </div>
          );
        })}
      </nav>
      <div className="p-4 border-t border-[var(--sidebar-border)] flex items-center justify-between">
        <span className="text-[10px] text-[var(--text-dim)]">{t('sidebar.footer')}</span>
        <button
          onClick={() => setLang(lang === 'ja' ? 'en' : 'ja')}
          className="px-3 py-1.5 text-xs font-medium rounded border border-[var(--sidebar-border)] text-[var(--sidebar-text)] hover:text-[var(--sidebar-text-active)] hover:border-[var(--sidebar-text)] transition-colors"
        >
          {lang === 'ja' ? 'EN' : 'JA'}
        </button>
      </div>
    </aside>
    </>
  );
}
