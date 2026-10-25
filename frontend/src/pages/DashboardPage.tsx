import Icon from "../components/Icon";
import TelemetryTiles from "../components/TelemetryTiles";
import VoicePaths from "../components/VoicePaths";
import type { PageId, ShellStatus } from "../components/shell/AppShell";
import { useI18n } from "../i18n";
import type { VoiceCapabilities } from "../types/radio";
import type { MMDVMStatus } from "../types/runtime";

type Props = {
  status: ShellStatus;
  mmdvmStatus: MMDVMStatus | null;
  capabilities: VoiceCapabilities | null;
  onNavigate: (page: PageId) => void;
};

export default function DashboardPage({ status, mmdvmStatus, capabilities, onNavigate }: Props) {
  const { t } = useI18n();
  const heroTitle = status.rfTxActive
    ? t("dash.hero.tx")
    : status.runtimeActive
      ? t("dash.hero.active")
      : t("dash.hero.idle");
  const heroSub =
    status.runtimeActive || status.rfTxActive
      ? [status.protocolLabel, status.frequencyLabel, status.deviceLabel].filter(Boolean).join(" · ")
      : t("dash.hero.idle.sub");

  return (
    <>
      <div className="hero">
        <span className={`hero-dot${status.rfTxActive ? " tx" : status.runtimeActive ? " ok" : ""}`} />
        <div className="hero-main">
          <div className="hero-title">{heroTitle}</div>
          <div className="hero-sub">{heroSub}</div>
        </div>
        <div className="hero-metrics">
          <div className="hero-metric">
            <span className="hero-metric-label">{t("dash.mode")}</span>
            <span className="hero-metric-value">{status.protocolLabel ?? "—"}</span>
          </div>
          <div className="hero-metric">
            <span className="hero-metric-label">{t("tel.channel")}</span>
            <span className="hero-metric-value">{status.frequencyLabel ?? "—"}</span>
          </div>
          <div className="hero-metric">
            <span className="hero-metric-label">RF TX</span>
            <span className="hero-metric-value" style={{ color: status.rfTxActive ? "var(--danger)" : undefined }}>
              {status.rfTxActive ? "ON" : "OFF"}
            </span>
          </div>
        </div>
      </div>

      <div className="stat-grid">
        <button type="button" className="stat-card" onClick={() => onNavigate("routes")}>
          <div className="stat-label">{t("dash.routes")}</div>
          <div className="stat-value accent">{status.routeCount}</div>
          <div className="stat-sub">{t("dash.routes.sub")}</div>
          <span className="stat-icon">
            <Icon name="routes" size={30} />
          </span>
        </button>
        <button type="button" className="stat-card blue" onClick={() => onNavigate("sources")}>
          <div className="stat-label">{t("dash.sources")}</div>
          <div className="stat-value blue">{status.sourceCount}</div>
          <div className="stat-sub">{t("dash.sources.sub")}</div>
          <span className="stat-icon">
            <Icon name="source" size={30} />
          </span>
        </button>
        <button type="button" className="stat-card warn" onClick={() => onNavigate("devices")}>
          <div className="stat-label">{t("dash.devices")}</div>
          <div className="stat-value warn">{status.deviceCount}</div>
          <div className="stat-sub">{t("dash.devices.sub")}</div>
          <span className="stat-icon">
            <Icon name="device" size={30} />
          </span>
        </button>
        <button
          type="button"
          className={`stat-card${status.rfTxActive ? " danger" : ""}`}
          onClick={() => onNavigate("modes")}
        >
          <div className="stat-label">{t("dash.mode")}</div>
          <div className={`stat-value${status.rfTxActive ? " danger" : ""}`}>{status.protocolLabel ?? "—"}</div>
          <div className="stat-sub">
            {status.runtimeActive ? t("status.active") : t("status.stopped")}
            {status.frequencyLabel ? ` · ${status.frequencyLabel}` : ""}
          </div>
          <span className="stat-icon">
            <Icon name="radio" size={30} />
          </span>
        </button>
      </div>

      <div className="page-grid two">
        <div>
          <div className="card">
            <div className="card-head">
              <span className="card-title">{t("page.telemetry")}</span>
              <div className="card-actions">
                <button type="button" className="btn btn-sm" onClick={() => onNavigate("telemetry")}>
                  <Icon name="telemetry" /> {t("page.telemetry")}
                </button>
              </div>
            </div>
            <div className="card-body">
              <TelemetryTiles status={mmdvmStatus} runtimeActive={status.runtimeActive} rfTxActive={status.rfTxActive} compact />
            </div>
          </div>
          <VoicePaths capabilities={capabilities} />
        </div>
        <div className="card">
          <div className="card-head">
            <span className="card-title">{t("dash.quick")}</span>
          </div>
          <div className="card-body" style={{ display: "grid", gap: 10 }}>
            <button type="button" className="btn btn-primary" onClick={() => onNavigate("routes")}>
              <Icon name="routes" /> {t("dash.open_routes")}
            </button>
            <button type="button" className="btn" onClick={() => onNavigate("remote_sdr")}>
              <Icon name="sdr" /> {t("dash.add_sdr")}
            </button>
            <button type="button" className="btn" onClick={() => onNavigate("modes")}>
              <Icon name="radio" /> {t("dash.configure_rf")}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
