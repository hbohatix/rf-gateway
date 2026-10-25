import { useCallback, useEffect, useMemo, useState } from "react";

import "./styles/theme.css";
import "./App.css";

import CalibrationPanel from "./components/CalibrationPanel";
import DMRConfigForm from "./components/protocols/DMRConfig";
import DStarConfigForm from "./components/protocols/DStarConfig";
import FMConfigForm from "./components/protocols/FMConfig";
import NXDNConfigForm from "./components/protocols/NXDNConfig";
import P25ConfigForm from "./components/protocols/P25Config";
import YSFConfigForm from "./components/protocols/YSFConfig";
import AppShell, { type PageId, type ShellStatus, type Theme } from "./components/shell/AppShell";
import { I18nProvider } from "./i18n";
import { API_BASE_URL, apiFetch, errorMessage } from "./lib/api";
import { formatFrequency, getDeviceDisplayName, loadFromStorage, readStorage, saveToStorage } from "./lib/format";
import {
  DEFAULT_DMR_CONFIG,
  DEFAULT_DSTAR_CONFIG,
  DEFAULT_FM_CONFIG,
  DEFAULT_NXDN_CONFIG,
  DEFAULT_P25_CONFIG,
  DEFAULT_YSF_CONFIG,
  PROTOCOL_INFO,
  STORAGE_KEYS,
  dmrFromSaved,
  dmrPayload,
  dstarFromSaved,
  dstarPayload,
  fmFromSaved,
  fmPayload,
  nxdnFromSaved,
  nxdnPayload,
  p25FromSaved,
  p25Payload,
  ysfFromSaved,
  ysfPayload,
} from "./lib/modes";
import DevicesPage from "./pages/DevicesPage";
import LogsPage from "./pages/LogsPage";
import RemoteSdrPage from "./pages/RemoteSdrPage";
import TransmitPage from "./pages/TransmitPage";
import type {
  DMRConfig,
  DStarConfig,
  FMConfig,
  NXDNConfig,
  P25Config,
  Protocol,
  VoiceCapabilities,
  YSFConfig,
} from "./types/radio";
import type { RFDevicesResponse } from "./types/rfDevice";
import type { Health, SavedModesResponse } from "./types/runtime";
import type { TransmitState } from "./types/transmit";

const PAGES: PageId[] = ["transmit", "remote_sdr", "devices", "logs"];

function pageFromHash(): PageId | null {
  const hash = window.location.hash.replace("#", "");
  return (PAGES as string[]).includes(hash) ? (hash as PageId) : null;
}

function initialPage(): PageId {
  const stored = readStorage(STORAGE_KEYS.page);
  return pageFromHash() ?? ((PAGES as string[]).includes(stored ?? "") ? (stored as PageId) : "transmit");
}

function initialTheme(): Theme {
  const stored = readStorage(STORAGE_KEYS.theme);
  if (stored === "dark" || stored === "light" || stored === "blue") {
    return stored;
  }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function payloadJson(build: () => object): string | null {
  try {
    return JSON.stringify(build());
  } catch {
    return null; // incomplete input
  }
}

/** Debounced PUT /api/config/modes whenever a mode form changes (the backend applies it on air). */
function useAutosave(enabled: boolean, body: string | null) {
  useEffect(() => {
    if (!enabled || body === null) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      apiFetch("/api/config/modes", { method: "PUT", body }).catch((error) =>
        console.error("Unable to save mode configuration:", error),
      );
    }, 700);
    return () => window.clearTimeout(timer);
  }, [enabled, body]);
}

function AppContent() {
  const [page, setPage] = useState<PageId>(initialPage);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [collapsed, setCollapsed] = useState(() => readStorage(STORAGE_KEYS.sidebar) === "1");

  const [health, setHealth] = useState<Health | null>(null);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [transmit, setTransmit] = useState<TransmitState | null>(null);
  const [devicesResponse, setDevicesResponse] = useState<RFDevicesResponse | null>(null);
  const [devicesLoading, setDevicesLoading] = useState(true);
  const [devicesError, setDevicesError] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<VoiceCapabilities | null>(null);
  const [modeConfigsLoaded, setModeConfigsLoaded] = useState(false);
  const [sourceCount, setSourceCount] = useState(0);
  const [calibrationOpen, setCalibrationOpen] = useState(false);
  const [calibrationError, setCalibrationError] = useState<string | null>(null);

  const [fmConfig, setFmConfig] = useState<FMConfig>(() => loadFromStorage(STORAGE_KEYS.fmConfig, DEFAULT_FM_CONFIG));
  const [dmrConfig, setDmrConfig] = useState<DMRConfig>(() => loadFromStorage(STORAGE_KEYS.dmrConfig, DEFAULT_DMR_CONFIG));
  const [p25Config, setP25Config] = useState<P25Config>(() => loadFromStorage(STORAGE_KEYS.p25Config, DEFAULT_P25_CONFIG));
  const [nxdnConfig, setNxdnConfig] = useState<NXDNConfig>(() => loadFromStorage(STORAGE_KEYS.nxdnConfig, DEFAULT_NXDN_CONFIG));
  const [dstarConfig, setDstarConfig] = useState<DStarConfig>(() =>
    loadFromStorage(STORAGE_KEYS.dstarConfig, DEFAULT_DSTAR_CONFIG),
  );
  const [ysfConfig, setYsfConfig] = useState<YSFConfig>(() => loadFromStorage(STORAGE_KEYS.ysfConfig, DEFAULT_YSF_CONFIG));

  const devices = useMemo(() => devicesResponse?.devices ?? [], [devicesResponse]);
  const activeProtocol = transmit?.mode.protocol ?? null;
  const rf = transmit?.rf;
  const mmdvmStatus = rf?.mmdvm ?? null;

  // ---------------------------------------------------------------- loaders
  const loadTransmit = useCallback(async () => {
    try {
      setTransmit(await apiFetch<TransmitState>("/api/transmit"));
    } catch {
      // backend offline: the health check reports it
    }
  }, []);

  const loadDevices = useCallback(async () => {
    setDevicesLoading(true);
    setDevicesError(null);
    try {
      setDevicesResponse(await apiFetch<RFDevicesResponse>("/api/devices"));
    } catch (error) {
      setDevicesError(errorMessage(error));
    } finally {
      setDevicesLoading(false);
    }
  }, []);

  const loadCapabilities = useCallback(async () => {
    try {
      setCapabilities(await apiFetch<VoiceCapabilities>("/api/voice/capabilities"));
    } catch {
      // older backend
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadHealth = () =>
      apiFetch<Health>("/api/health")
        .then((data) => {
          if (!cancelled) {
            setHealth(data);
            setBackendOnline(true);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setBackendOnline(false);
          }
        });

    const loadModes = async () => {
      try {
        const data = await apiFetch<SavedModesResponse>("/api/config/modes");
        if (data.modes.fm) setFmConfig(fmFromSaved(data.modes.fm));
        if (data.modes.dmr) setDmrConfig(dmrFromSaved(data.modes.dmr));
        if (data.modes.p25) setP25Config(p25FromSaved(data.modes.p25));
        if (data.modes.ysf) setYsfConfig(ysfFromSaved(data.modes.ysf));
        if (data.modes.dstar) setDstarConfig(dstarFromSaved(data.modes.dstar));
        if (data.modes.nxdn) setNxdnConfig(nxdnFromSaved(data.modes.nxdn));
      } catch (error) {
        console.error("Unable to load saved mode configurations:", error);
      } finally {
        if (!cancelled) {
          setModeConfigsLoaded(true);
        }
      }
    };

    const loadInitialDevices = () =>
      apiFetch<RFDevicesResponse>("/api/devices")
        .then((data) => !cancelled && setDevicesResponse(data))
        .catch((error) => !cancelled && setDevicesError(errorMessage(error)))
        .finally(() => !cancelled && setDevicesLoading(false));

    void loadHealth();
    void loadModes();
    void loadInitialDevices();
    apiFetch<VoiceCapabilities>("/api/voice/capabilities")
      .then((data) => !cancelled && setCapabilities(data))
      .catch(() => undefined);
    apiFetch<TransmitState>("/api/transmit")
      .then((data) => !cancelled && setTransmit(data))
      .catch(() => undefined);

    const transmitTimer = window.setInterval(() => void loadTransmit(), 1000);
    const healthTimer = window.setInterval(() => void loadHealth(), 10000);
    const capabilityTimer = window.setInterval(() => void loadCapabilities(), 30000);
    return () => {
      cancelled = true;
      window.clearInterval(transmitTimer);
      window.clearInterval(healthTimer);
      window.clearInterval(capabilityTimer);
    };
  }, [loadCapabilities, loadTransmit]);

  // ------------------------------------------------------------ persistence
  useEffect(() => saveToStorage(STORAGE_KEYS.fmConfig, fmConfig), [fmConfig]);
  useEffect(() => saveToStorage(STORAGE_KEYS.dmrConfig, dmrConfig), [dmrConfig]);
  useEffect(() => saveToStorage(STORAGE_KEYS.p25Config, p25Config), [p25Config]);
  useEffect(() => saveToStorage(STORAGE_KEYS.ysfConfig, ysfConfig), [ysfConfig]);
  useEffect(() => saveToStorage(STORAGE_KEYS.dstarConfig, dstarConfig), [dstarConfig]);
  useEffect(() => saveToStorage(STORAGE_KEYS.nxdnConfig, nxdnConfig), [nxdnConfig]);
  useEffect(() => saveToStorage(STORAGE_KEYS.sidebar, collapsed ? "1" : "0"), [collapsed]);
  useEffect(() => {
    saveToStorage(STORAGE_KEYS.page, page);
    if (window.location.hash !== `#${page}`) {
      window.history.pushState(null, "", `#${page}`);
    }
  }, [page]);
  useEffect(() => {
    const onHashChange = () => {
      const next = pageFromHash();
      if (next) {
        setPage(next);
      }
    };
    window.addEventListener("hashchange", onHashChange);
    window.addEventListener("popstate", onHashChange);
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      window.removeEventListener("popstate", onHashChange);
    };
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    saveToStorage(STORAGE_KEYS.theme, theme);
  }, [theme]);

  useAutosave(modeConfigsLoaded, useMemo(() => payloadJson(() => fmPayload(fmConfig)), [fmConfig]));
  useAutosave(modeConfigsLoaded, useMemo(() => payloadJson(() => dmrPayload(dmrConfig)), [dmrConfig]));
  useAutosave(modeConfigsLoaded, useMemo(() => payloadJson(() => p25Payload(p25Config)), [p25Config]));
  useAutosave(modeConfigsLoaded, useMemo(() => payloadJson(() => ysfPayload(ysfConfig)), [ysfConfig]));
  useAutosave(modeConfigsLoaded, useMemo(() => payloadJson(() => dstarPayload(dstarConfig)), [dstarConfig]));
  useAutosave(modeConfigsLoaded, useMemo(() => payloadJson(() => nxdnPayload(nxdnConfig)), [nxdnConfig]));

  // Vocoder changes alter capability; refresh shortly after saving.
  useEffect(() => {
    const timer = window.setTimeout(() => void loadCapabilities(), 1500);
    return () => window.clearTimeout(timer);
  }, [dmrConfig.vocoder, ysfConfig.vocoder, nxdnConfig.vocoder, loadCapabilities]);

  // ----------------------------------------------------------------- actions
  const selectProtocol = async (protocol: Protocol) => {
    setTransmit((current) => (current ? { ...current, mode: { ...current.mode, protocol } } : current));
    try {
      await apiFetch("/api/transmit/mode", { method: "PUT", body: JSON.stringify({ protocol }) });
    } finally {
      void loadTransmit();
    }
  };

  const selectDevice = async (deviceId: string) => {
    if (!deviceId) {
      return;
    }
    await apiFetch("/api/transmit/device", { method: "PUT", body: JSON.stringify({ device_id: deviceId }) });
    void loadTransmit();
  };

  const modePayload = (protocol: Protocol) => {
    const builders: Partial<Record<Protocol, () => object>> = {
      fm: () => fmPayload(fmConfig),
      dmr: () => dmrPayload(dmrConfig),
      p25: () => p25Payload(p25Config),
      ysf: () => ysfPayload(ysfConfig),
      dstar: () => dstarPayload(dstarConfig),
      nxdn: () => nxdnPayload(nxdnConfig),
    };
    const build = builders[protocol];
    if (!build) {
      throw new Error(`${protocol.toUpperCase()} cannot be transmitted`);
    }
    return build();
  };

  /** Calibration needs the transmitter running (without a source). */
  const openCalibration = async () => {
    setCalibrationError(null);
    if (!activeProtocol) {
      return;
    }
    try {
      if (!rf?.runtime_active) {
        const deviceId =
          transmit?.device_id ?? devices.find((device) => device.available && device.probe_ok)?.id ?? null;
        if (!deviceId) {
          throw new Error("No usable RF device");
        }
        await apiFetch("/api/rf/start", {
          method: "POST",
          body: JSON.stringify({ ...modePayload(activeProtocol), device_id: deviceId }),
        });
      }
      setCalibrationOpen(true);
    } catch (error) {
      setCalibrationError(errorMessage(error));
    } finally {
      void loadTransmit();
    }
  };

  // ------------------------------------------------------------------ status
  const selectedDevice = devices.find((device) => device.id === (transmit?.device_id ?? rf?.device_id)) ?? null;
  const activeFrequencyHz = (() => {
    if (mmdvmStatus?.channel_frequency_hz) {
      return mmdvmStatus.channel_frequency_hz;
    }
    try {
      return activeProtocol ? (modePayload(activeProtocol) as { frequency_hz?: number }).frequency_hz ?? null : null;
    } catch {
      return null;
    }
  })();

  const shellStatus: ShellStatus = {
    backendOnline,
    backendVersion: health?.version ?? null,
    runtimeActive: Boolean(rf?.runtime_active),
    rfTxActive: Boolean(rf?.rf_tx_active),
    protocolLabel: activeProtocol ? PROTOCOL_INFO[activeProtocol].name : null,
    frequencyLabel: activeProtocol ? formatFrequency(activeFrequencyHz, 4) : null,
    deviceLabel: selectedDevice ? `${getDeviceDisplayName(selectedDevice)} · ${selectedDevice.driver}` : null,
    sourceCount,
    deviceCount: devicesResponse?.device_count ?? 0,
  };

  const modeForm = (() => {
    switch (activeProtocol) {
      case "fm":
        return <FMConfigForm value={fmConfig} onChange={setFmConfig} />;
      case "dmr":
        return <DMRConfigForm value={dmrConfig} onChange={setDmrConfig} />;
      case "p25":
        return <P25ConfigForm value={p25Config} onChange={setP25Config} />;
      case "ysf":
        return <YSFConfigForm value={ysfConfig} onChange={setYsfConfig} />;
      case "dstar":
        return <DStarConfigForm value={dstarConfig} onChange={setDstarConfig} />;
      case "nxdn":
        return <NXDNConfigForm value={nxdnConfig} onChange={setNxdnConfig} />;
      default:
        return null;
    }
  })();

  return (
    <AppShell
      page={page}
      onNavigate={setPage}
      theme={theme}
      onThemeChange={setTheme}
      collapsed={collapsed}
      onToggleCollapsed={() => setCollapsed((value) => !value)}
      status={shellStatus}
    >
      {backendOnline === false && (
        <div className="banner banner-danger">
          Backend unreachable at {API_BASE_URL || window.location.origin}/api — start it with: rf-gateway start
        </div>
      )}
      {calibrationError && <div className="banner banner-danger">{calibrationError}</div>}

      {page === "transmit" && (
        <TransmitPage
          transmit={transmit}
          onRefresh={() => void loadTransmit()}
          capabilities={capabilities}
          onSelectProtocol={(protocol) => void selectProtocol(protocol)}
          modeForm={modeForm}
          devices={devices}
          onSelectDevice={(deviceId) => void selectDevice(deviceId)}
          onCalibrate={() => void openCalibration()}
          onSourcesChanged={setSourceCount}
        />
      )}

      {page === "devices" && (
        <DevicesPage
          devices={devices}
          loading={devicesLoading}
          error={devicesError}
          warnings={devicesResponse?.warnings ?? []}
          selectedDeviceId={transmit?.device_id ?? null}
          runtimeActive={Boolean(rf?.runtime_active)}
          onRefresh={() => void loadDevices()}
          onSelect={(device) => void selectDevice(device.id)}
        />
      )}

      {page === "remote_sdr" && <RemoteSdrPage onSourcesChanged={() => undefined} onOpenRoutes={() => setPage("transmit")} />}

      {page === "logs" && <LogsPage />}

      <CalibrationPanel
        open={calibrationOpen}
        runtimeActive={Boolean(rf?.runtime_active)}
        runtimeReady={Boolean(mmdvmStatus?.runtime_ready)}
        rfTxActive={Boolean(rf?.rf_tx_active)}
        protocol={activeProtocol}
        channelFrequencyHz={mmdvmStatus?.channel_frequency_hz}
        sdrCenterFrequencyHz={mmdvmStatus?.sdr_tx_center_frequency_hz}
        digitalIfHz={mmdvmStatus?.digital_if_hz}
        onClose={() => setCalibrationOpen(false)}
      />
    </AppShell>
  );
}

export default function App() {
  return (
    <I18nProvider>
      <AppContent />
    </I18nProvider>
  );
}
