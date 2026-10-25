import { useState, type ReactNode } from "react";
import Icon, { type IconName } from "../Icon";
import { useI18n, type TranslationKey } from "../../i18n";
import { PAGE_TITLES, type PageId, type Theme } from "./pages";

export type { PageId, Theme } from "./pages";



type NavItem = { id: PageId; icon: IconName; badge?: number | string; badgeWarn?: boolean };
type NavSection = { label: TranslationKey; items: NavItem[] };

export type ShellStatus = {
  backendOnline: boolean | null;
  backendVersion: string | null;
  runtimeActive: boolean;
  rfTxActive: boolean;
  protocolLabel: string | null;
  frequencyLabel: string | null;
  deviceLabel: string | null;
  sourceCount: number;
  deviceCount: number;
};

type AppShellProps = {
  page: PageId;
  onNavigate: (page: PageId) => void;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  status: ShellStatus;
  children: ReactNode;
};



export default function AppShell({
  page,
  onNavigate,
  theme,
  onThemeChange,
  collapsed,
  onToggleCollapsed,
  status,
  children,
}: AppShellProps) {
  const { t, lang, setLang } = useI18n();
  const [mobileOpen, setMobileOpen] = useState(false);

  const sections: NavSection[] = [
    {
      label: "nav.radio",
      items: [
        {
          id: "transmit",
          icon: "radio",
          badge: status.rfTxActive ? "TX" : status.sourceCount || undefined,
          badgeWarn: status.rfTxActive,
        },
        { id: "remote_sdr", icon: "sdr" },
        { id: "devices", icon: "device", badge: status.deviceCount || undefined },
      ],
    },
    {
      label: "nav.system",
      items: [{ id: "logs", icon: "log" }],
    },
  ];

  const navigate = (next: PageId) => {
    onNavigate(next);
    setMobileOpen(false);
  };

  const titles = PAGE_TITLES[page];
  const backendState =
    status.backendOnline === null ? t("status.connecting") : status.backendOnline ? t("status.online") : t("status.offline");

  return (
    <div className="shell">
      <aside className={`sidebar${collapsed ? " collapsed" : ""}${mobileOpen ? " mobile-open" : ""}`}>
        <div className="sidebar-logo">
          <div className="logo-row">
            <div className="logo-icon">RG</div>
            <div className="logo-text">
              <div className="logo-name">RF Gateway</div>
              <div className="logo-sub">MMDVM · SDR · {status.backendVersion ? `v${status.backendVersion}` : "—"}</div>
            </div>
          </div>
          <div className="hw-status">
            <div className="hw-row hw-row--sdr" title={status.deviceLabel ?? ""}>
              <div className="hw-glyph">
                <Icon name="device" />
              </div>
              <div className="hw-meta">
                <span className="hw-key">SDR / modem</span>
                <span className="hw-val">{status.deviceLabel ?? "—"}</span>
              </div>
              {status.runtimeActive && (
                <span className="hw-live">
                  <span className={`hw-live-dot${status.rfTxActive ? " tx" : ""}`} />
                </span>
              )}
            </div>
            <div className="hw-row hw-row--mode">
              <div className="hw-glyph">
                <Icon name="radio" />
              </div>
              <div className="hw-meta">
                <span className="hw-key">{t("dash.mode")}</span>
                <span className="hw-val">
                  {status.protocolLabel ?? "—"}
                  {status.frequencyLabel ? ` · ${status.frequencyLabel}` : ""}
                </span>
              </div>
            </div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {sections.map((section) => (
            <div key={section.label}>
              <div className="nav-section-label">{t(section.label)}</div>
              {section.items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`nav-item${page === item.id ? " active" : ""}`}
                  onClick={() => navigate(item.id)}
                  title={t(PAGE_TITLES[item.id].title)}
                >
                  <span className="nav-icon">
                    <Icon name={item.icon} />
                  </span>
                  <span className="nav-label">{t(PAGE_TITLES[item.id].title)}</span>
                  {item.badge !== undefined && (
                    <span className={`nav-badge${item.badgeWarn ? " warn" : ""}`}>{item.badge}</span>
                  )}
                </button>
              ))}
            </div>
          ))}
          <a className="nav-item" href="/docs" target="_blank" rel="noreferrer" title={t("page.api")}>
            <span className="nav-icon">
              <Icon name="api" />
            </span>
            <span className="nav-label">{t("page.api")}</span>
          </a>
        </nav>

        <div className="sidebar-footer">
          <div className="conn-row boxed">
            <span className={`conn-led${status.runtimeActive ? (status.rfTxActive ? " warn" : " blue") : ""}`} />
            <div className="conn-info">
              <div className="conn-info-label">MMDVM</div>
              <div className="conn-info-val">
                {status.runtimeActive ? (status.rfTxActive ? "TX" : t("status.active")) : t("status.stopped")}
              </div>
            </div>
          </div>
          <div className="conn-row">
            <span className={`conn-led${status.backendOnline ? " on" : ""}`} />
            <div className="conn-info">
              <div className="conn-info-label">{t("status.backend").toUpperCase()}</div>
              <div className="conn-info-val" style={{ color: status.backendOnline ? "var(--accent)" : "var(--danger)" }}>
                {backendState}
              </div>
            </div>
          </div>
          <div className="sidebar-copyright">RF Gateway · FastAPI · MMDVM</div>
          <button type="button" className="sidebar-toggle" onClick={onToggleCollapsed} title={t("common.collapse")}>
            <Icon name={collapsed ? "chevron_right" : "chevron_left"} />
          </button>
        </div>
      </aside>

      {mobileOpen && <div className="sidebar-scrim mobile-only" onClick={() => setMobileOpen(false)} />}

      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="sidebar-toggle mobile-only"
            aria-label="Menu"
            onClick={() => setMobileOpen((v) => !v)}
          >
            <Icon name="menu" />
          </button>
          <span className="topbar-title">{t(titles.title)}</span>
          <span className="topbar-sub">{t(titles.sub)}</span>
          <div className="topbar-pills">
            {status.rfTxActive ? (
              <span className="pill pill-tx">TX ON AIR</span>
            ) : (
              <span className={`pill ${status.runtimeActive ? "pill-ok" : "pill-idle"}`}>
                RF {status.runtimeActive ? t("status.active") : t("status.stopped")}
              </span>
            )}
            {status.protocolLabel && <span className="pill pill-info no-dot optional">{status.protocolLabel}</span>}
          </div>
          <div className="topbar-right">
            <div className="seg" role="group" aria-label="Theme">
              {(["dark", "light", "blue"] as Theme[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  className={theme === option ? "active" : ""}
                  onClick={() => onThemeChange(option)}
                >
                  {t(`theme.${option}` as TranslationKey)}
                </button>
              ))}
            </div>
            <div className="seg" role="group" aria-label="Language">
              {(["pl", "en"] as const).map((option) => (
                <button key={option} type="button" className={lang === option ? "active" : ""} onClick={() => setLang(option)}>
                  {option.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
