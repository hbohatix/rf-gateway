import { useCallback, useEffect, useMemo, useState } from "react";

import "./styles/theme.css";
import "./App.css";

import CalibrationPanel from "./components/CalibrationPanel";
import RoutesPanel from "./components/RoutesPanel";
import SourcesPanel from "./components/SourcesPanel";
import TelemetryTiles from "./components/TelemetryTiles";
import VoicePaths from "./components/VoicePaths";
import AppShell, { type PageId, type ShellStatus, type Theme } from "./components/shell/AppShell";
import { I18nProvider } from "./i18n";
import { API_BASE_URL, apiFetch, errorMessage } from "./lib/api";
import { formatFrequency, getDeviceDisplayName, loadFromStorage, readStorage, saveToStorage } from "./lib/format";
import {
  DEFAULT_DMR_CONFIG,
  DEFAULT_FM_CONFIG,
  DEFAULT_P25_CONFIG,
  DEFAULT_TETRA_CONFIG,
  DEFAULT_YSF_CONFIG,
  DEFAULT_DSTAR_CONFIG,
  DEFAULT_NXDN_CONFIG,
  nxdnFromSaved,
  nxdnPayload,
  dstarFromSaved,
  dstarPayload,
  PROTOCOL_INFO,
  STORAGE_KEYS,
  dmrFromSaved,
  dmrPayload,
  fmFromSaved,
  fmPayload,
  isProtocol,
  p25FromSaved,
  p25Payload,
  tetraFromSaved,
  tetraPayload,
  ysfFromSaved,
  ysfPayload,
} from "./lib/modes";
import DashboardPage from "./pages/DashboardPage";
import DevicesPage from "./pages/DevicesPage";
import LogsPage from "./pages/LogsPage";
import ModesPage from "./pages/ModesPage";
import RemoteSdrPage from "./pages/RemoteSdrPage";
import type {
  DMRConfig,
  DStarConfig,
  FMConfig,
  NXDNConfig,
  P25Config,
  Protocol,
  TETRAConfig,
  VoiceCapabilities,
  YSFConfig,
} from "./types/radio";
import type { RFDevice, RFDevicesResponse } from "./types/rfDevice";
import type { Health, MMDVMStatus, RFStatus, SavedModesResponse } from "./types/runtime";

const PAGES: PageId[] = ["dashboard", "routes", "telemetry", "modes", "devices", "remote_sdr", "sources", "logs"];

function initialPage(): PageId {
  const fromHash = window.location.hash.replace("#", "");
  if ((PAGES as string[]).includes(fromHash)) {
    return fromHash as PageId;
  }
  const stored = readStorage(STORAGE_KEYS.page);
  return stored && (PAGES as string[]).includes(stored) ? (stored as PageId) : "dashboard";
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

/** Debounced PUT /api/config/modes whenever a protocol form changes. */
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

  const [activeProtocol, setActiveProtocol] = useState<Protocol | null>(() => {
    const stored = readStorage(STORAGE_KEYS.activeProtocol);
    return isProtocol(stored) ? stored : null;
  });
  const [preferredDeviceId, setSelectedDeviceId] = useState<string | null>(() => readStorage(STORAGE_KEYS.selectedDeviceId));
  const [devicesResponse, setDevicesResponse] = useState<RFDevicesResponse | null>(null);
  const [devicesLoading, setDevicesLoading] = useState(true);
  const [devicesError, setDevicesError] = useState<string | null>(null);
  const [modeConfigsLoaded, setModeConfigsLoaded] = useState(false);
  const [capabilities, setCapabilities] = useState<VoiceCapabilities | null>(null);

  const [runtimeActive, setRuntimeActive] = useState(false);
  const [rfTxActive, setRfTxActive] = useState(false);
  const [mmdvmStatus, setMmdvmStatus] = useState<MMDVMStatus | null>(null);
  const [runtimeMessage, setRuntimeMessage] = useState<string | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [calibrationOpen, setCalibrationOpen] = useState(false);

  const [sourceCount, setSourceCount] = useState(0);
  const [sourceRefreshKey, setSourceRefreshKey] = useState(0);
  const [routeCount, setRouteCount] = useState(0);

  const [fmConfig, setFmConfig] = useState<FMConfig>(() => loadFromStorage(STORAGE_KEYS.fmConfig, DEFAULT_FM_CONFIG));
  const [dmrConfig, setDmrConfig] = useState<DMRConfig>(() => loadFromStorage(STORAGE_KEYS.dmrConfig, DEFAULT_DMR_CONFIG));
  const [p25Config, setP25Config] = useState<P25Config>(() => loadFromStorage(STORAGE_KEYS.p25Config, DEFAULT_P25_CONFIG));
  const [nxdnConfig, setNxdnConfig] = useState<NXDNConfig>(() => loadFromStorage(STORAGE_KEYS.nxdnConfig, DEFAULT_NXDN_CONFIG));
  const [dstarConfig, setDstarConfig] = useState<DStarConfig>(() =>
    loadFromStorage(STORAGE_KEYS.dstarConfig, DEFAULT_DSTAR_CONFIG),
  );
  const [ysfConfig, setYsfConfig] = useState<YSFConfig>(() => loadFromStorage(STORAGE_KEYS.ysfConfig, DEFAULT_YSF_CONFIG));
  const [tetraConfig, setTetraConfig] = useState<TETRAConfig>(() =>
    loadFromStorage(STORAGE_KEYS.tetraConfig, DEFAULT_TETRA_CONFIG),
  );

  const devices = useMemo(() => devicesResponse?.devices ?? [], [devicesResponse]);

  // The stored preference wins while it is usable (or while RF runs on it);
  // otherwise fall back to the only usable device.
  const selectedDeviceId = useMemo(() => {
    const usable = devices.filter((device) => device.available && device.probe_ok);
    if (preferredDeviceId && (runtimeActive || usable.some((device) => device.id === preferredDeviceId))) {
      return preferredDeviceId;
    }
    if (!devicesResponse) {
      return preferredDeviceId;
    }
    return usable.length === 1 ? usable[0].id : null;
  }, [devices, devicesResponse, preferredDeviceId, runtimeActive]);
  const selectedDevice = devices.find((device) => device.id === selectedDeviceId) ?? null;

  // ---------------------------------------------------------------- loaders
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

  const applyRFStatus = useCallback((data: RFStatus) => {
    setRuntimeActive(Boolean(data.runtime_active));
    setRfTxActive(Boolean(data.rf_tx_active));
    setMmdvmStatus(data.mmdvm ?? null);
    if (data.protocol) {
      setActiveProtocol(data.protocol);
    }
    if (data.device_id) {
      setSelectedDeviceId(data.device_id);
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
        if (data.modes.tetra) setTetraConfig(tetraFromSaved(data.modes.tetra));
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

    const loadRFStatus = () =>
      apiFetch<RFStatus>("/api/rf/status")
        .then((data) => {
          if (!cancelled) {
            applyRFStatus(data);
          }
        })
        .catch(() => undefined);

    const loadInitialDevices = () =>
      apiFetch<RFDevicesResponse>("/api/devices")
        .then((data) => {
          if (!cancelled) {
            setDevicesResponse(data);
            setDevicesError(null);
          }
        })
        .catch((error) => {
          if (!cancelled) {
            setDevicesError(errorMessage(error));
          }
        })
        .finally(() => {
          if (!cancelled) {
            setDevicesLoading(false);
          }
        });

    const loadVoiceCapabilities = () =>
      apiFetch<VoiceCapabilities>("/api/voice/capabilities")
        .then((data) => {
          if (!cancelled) {
            setCapabilities(data);
          }
        })
        .catch(() => undefined);

    void loadHealth();
    void loadModes();
    void loadInitialDevices();
    void loadVoiceCapabilities();
    void loadRFStatus();

    const statusTimer = window.setInterval(() => void loadRFStatus(), 750);
    const healthTimer = window.setInterval(() => void loadHealth(), 10000);
    const capabilityTimer = window.setInterval(() => void loadVoiceCapabilities(), 30000);
    return () => {
      cancelled = true;
      window.clearInterval(statusTimer);
      window.clearInterval(healthTimer);
      window.clearInterval(capabilityTimer);
    };
  }, [applyRFStatus]);

  // ------------------------------------------------------------ persistence
  useEffect(() => saveToStorage(STORAGE_KEYS.activeProtocol, activeProtocol), [activeProtocol]);
  useEffect(() => saveToStorage(STORAGE_KEYS.selectedDeviceId, preferredDeviceId), [preferredDeviceId]);
  useEffect(() => saveToStorage(STORAGE_KEYS.fmConfig, fmConfig), [fmConfig]);
  useEffect(() => saveToStorage(STORAGE_KEYS.dmrConfig, dmrConfig), [dmrConfig]);
  useEffect(() => saveToStorage(STORAGE_KEYS.p25Config, p25Config), [p25Config]);
  useEffect(() => saveToStorage(STORAGE_KEYS.tetraConfig, tetraConfig), [tetraConfig]);
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
      const next = window.location.hash.replace("#", "");
      if ((PAGES as string[]).includes(next)) {
        setPage(next as PageId);
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
  useAutosave(modeConfigsLoaded, useMemo(() => payloadJson(() => tetraPayload(tetraConfig)), [tetraConfig]));
  useAutosave(modeConfigsLoaded, useMemo(() => payloadJson(() => ysfPayload(ysfConfig)), [ysfConfig]));
  useAutosave(modeConfigsLoaded, useMemo(() => payloadJson(() => dstarPayload(dstarConfig)), [dstarConfig]));
  useAutosave(modeConfigsLoaded, useMemo(() => payloadJson(() => nxdnPayload(nxdnConfig)), [nxdnConfig]));

  // DMR vocoder changes alter capability; refresh shortly after saving.
  useEffect(() => {
    const timer = window.setTimeout(() => void loadCapabilities(), 1500);
    return () => window.clearTimeout(timer);
  }, [dmrConfig.vocoder, ysfConfig.vocoder, nxdnConfig.vocoder, loadCapabilities]);

  // ----------------------------------------------------------------- actions
  const toggleProtocol = (protocol: Protocol) => {
    if (runtimeActive) {
      return;
    }
    setRuntimeMessage(null);
    setRuntimeError(null);
    setActiveProtocol((current) => (current === protocol ? null : protocol));
  };

  const selectDevice = (device: RFDevice) => {
    if (runtimeActive || !device.available || !device.probe_ok) {
      return;
    }
    setSelectedDeviceId(device.id);
    setRuntimeMessage(null);
    setRuntimeError(null);
  };

  const buildStartPayload = () => {
    if (!activeProtocol) {
      throw new Error("Select an RF protocol first");
    }
    if (!selectedDevice) {
      throw new Error("Select an RF device first");
    }
    const builders = {
      fm: () => fmPayload(fmConfig),
      dmr: () => dmrPayload(dmrConfig),
      p25: () => p25Payload(p25Config),
      ysf: () => ysfPayload(ysfConfig),
      dstar: () => dstarPayload(dstarConfig),
      nxdn: () => nxdnPayload(nxdnConfig),
      tetra: () => tetraPayload(tetraConfig),
    };
    return { ...builders[activeProtocol](), device_id: selectedDevice.id };
  };

  const handleStart = async () => {
    setRuntimeMessage(null);
    setRuntimeError(null);
    try {
      const payload = buildStartPayload();
      const data = await apiFetch<RFStatus>("/api/rf/start", { method: "POST", body: JSON.stringify(payload) });
      if (data.error) {
        throw new Error(data.error);
      }
      applyRFStatus(data);
      setRuntimeMessage(
        `${activeProtocol?.toUpperCase()} runtime started on ${selectedDevice ? getDeviceDisplayName(selectedDevice) : "device"}`,
      );
    } catch (error) {
      setRuntimeError(errorMessage(error));
    }
  };

  const handleStop = async () => {
    setCalibrationOpen(false);
    setRuntimeMessage(null);
    setRuntimeError(null);
    try {
      const data = await apiFetch<RFStatus>("/api/rf/stop", { method: "POST" });
      if (data.error) {
        throw new Error(data.error);
      }
      applyRFStatus(data);
      setRuntimeMessage("RF runtime stopped");
    } catch (error) {
      setRuntimeError(errorMessage(error));
    }
  };

  // ------------------------------------------------------------------ status
  const activeFrequencyHz = (() => {
    if (mmdvmStatus?.channel_frequency_hz) {
      return mmdvmStatus.channel_frequency_hz;
    }
    try {
      if (activeProtocol === "fm") return fmPayload(fmConfig).frequency_hz;
      if (activeProtocol === "dmr") return dmrPayload(dmrConfig).frequency_hz;
      if (activeProtocol === "p25") return p25Payload(p25Config).frequency_hz;
      if (activeProtocol === "tetra") return tetraPayload(tetraConfig).frequency_hz;
      if (activeProtocol === "ysf") return ysfPayload(ysfConfig).frequency_hz;
      if (activeProtocol === "dstar") return dstarPayload(dstarConfig).frequency_hz;
      if (activeProtocol === "nxdn") return nxdnPayload(nxdnConfig).frequency_hz;
    } catch {
      return null;
    }
    return null;
  })();

  const shellStatus: ShellStatus = {
    backendOnline,
    backendVersion: health?.version ?? null,
    runtimeActive,
    rfTxActive,
    protocolLabel: activeProtocol ? PROTOCOL_INFO[activeProtocol].name : null,
    frequencyLabel: activeProtocol ? formatFrequency(activeFrequencyHz, 4) : null,
    deviceLabel: selectedDevice ? `${getDeviceDisplayName(selectedDevice)} · ${selectedDevice.driver}` : null,
    routeCount,
    sourceCount,
    deviceCount: devicesResponse?.device_count ?? 0,
  };

  const refreshSources = () => setSourceRefreshKey((value) => value + 1);

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
          Backend unreachable at {API_BASE_URL || window.location.origin}/api — start it with ./scripts/run-dev.sh
        </div>
      )}

      {page === "dashboard" && (
        <DashboardPage status={shellStatus} mmdvmStatus={mmdvmStatus} capabilities={capabilities} onNavigate={setPage} />
      )}

      {/* Routes stay mounted so their polling and counters keep running. */}
      <div style={{ display: page === "routes" ? "block" : "none" }}>
        <RoutesPanel apiBaseUrl={API_BASE_URL} onRoutesChanged={setRouteCount} onSourcesChanged={refreshSources} />
      </div>

      {page === "telemetry" && (
        <>
          <div className="card">
            <div className="card-head">
              <span className="card-title">MMDVM</span>
              <span className="card-sub">{mmdvmStatus?.runtime_config ?? ""}</span>
            </div>
            <div className="card-body">
              <TelemetryTiles status={mmdvmStatus} runtimeActive={runtimeActive} rfTxActive={rfTxActive} />
            </div>
          </div>
          <VoicePaths capabilities={capabilities} />
        </>
      )}

      {page === "modes" && (
        <ModesPage
          activeProtocol={activeProtocol}
          onToggleProtocol={toggleProtocol}
          runtimeActive={runtimeActive}
          runtimeReady={Boolean(mmdvmStatus?.runtime_ready)}
          rfTxActive={rfTxActive}
          capabilities={capabilities}
          devices={devices}
          selectedDevice={selectedDevice}
          onSelectDevice={selectDevice}
          fmConfig={fmConfig}
          setFmConfig={setFmConfig}
          dmrConfig={dmrConfig}
          setDmrConfig={setDmrConfig}
          p25Config={p25Config}
          setP25Config={setP25Config}
          nxdnConfig={nxdnConfig}
          setNxdnConfig={setNxdnConfig}
          dstarConfig={dstarConfig}
          setDstarConfig={setDstarConfig}
          ysfConfig={ysfConfig}
          setYsfConfig={setYsfConfig}
          tetraConfig={tetraConfig}
          setTetraConfig={setTetraConfig}
          runtimeMessage={runtimeMessage}
          runtimeError={runtimeError}
          onStart={() => void handleStart()}
          onStop={() => void handleStop()}
          onCalibrate={() => setCalibrationOpen(true)}
        />
      )}

      {page === "devices" && (
        <DevicesPage
          devices={devices}
          loading={devicesLoading}
          error={devicesError}
          warnings={devicesResponse?.warnings ?? []}
          selectedDeviceId={selectedDeviceId}
          runtimeActive={runtimeActive}
          onRefresh={() => void loadDevices()}
          onSelect={selectDevice}
        />
      )}

      {page === "remote_sdr" && <RemoteSdrPage onSourcesChanged={refreshSources} onOpenRoutes={() => setPage("routes")} />}

      <div style={{ display: page === "sources" ? "block" : "none" }}>
        <SourcesPanel onCountChange={setSourceCount} refreshKey={sourceRefreshKey} />
      </div>

      {page === "logs" && <LogsPage />}

      <CalibrationPanel
        open={calibrationOpen}
        runtimeActive={runtimeActive}
        runtimeReady={Boolean(mmdvmStatus?.runtime_ready)}
        rfTxActive={rfTxActive}
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
