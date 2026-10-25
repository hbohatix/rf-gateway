import {
  useCallback,
  useEffect,
  useState,
} from "react";

import "./RoutesPanel.css";

import type {
  Protocol,
} from "../types/radio";

import type {
  RFDevice,
  RFDevicesResponse,
} from "../types/rfDevice";

import type {
  Route,
  RouteQueueStats,
  RouteRuntimeStatus,
  RouteWorkerStatus,
  RoutesResponse,
} from "../types/route";


type SourceProbe = {
  reachable?: boolean;

  page_name?:
    string
    | null;

  audio_api_configured?: boolean;

  playback_state?:
    string
    | null;
};


type Source = {
  id: string;

  name: string;

  type: string;

  provider: string;

  url: string;

  playlist_uuid?:
    string;

  feed_id?:
    number;

  view?:
    string;

  probe?:
    SourceProbe;
};


type SourcesResponse = {
  version: number;

  count: number;

  sources: Source[];
};


type LiveAudioGateStatus = {
  tx_active?: boolean;

  hang_ms?: number;

  hang_remaining_chunks?: number;

  trigger_dbfs?: number;

  release_dbfs?: number;

  noise_floor_dbfs?: number;
};


type LiveAudioP25Status = {
  active?: boolean;

  source_id?: number;

  destination_id?: number;

  pcm_frames_received?: number;

  imbe_frames_encoded?: number;

  ldu1_count?: number;

  ldu2_count?: number;

  network_records_sent?: number;

  network_bytes_sent?: number;

  terminator_bytes_sent?: number;

  duration_seconds?: number;
};


type LiveAudioStatus = {
  route_id: string;

  source_id: string;

  source_type:
    "broadcastify_live_audio" | "direct_audio" | "remote_sdr";

  feed_id: number | null;

  protocol: string;

  state: string;

  running: boolean;

  error:
    string
    | null;

  pcm_chunks_received: number;

  pcm_bytes_received: number;

  tx_start_count: number;

  tx_end_count: number;

  transport_gap_end_count: number;

  last_activity_level_dbfs:
    number
    | null;

  last_noise_floor_dbfs:
    number
    | null;

  last_trigger_dbfs:
    number
    | null;

  started_at:
    string
    | null;

  stopped_at:
    string
    | null;

  gate?:
    LiveAudioGateStatus
    | null;

  voice?:
    LiveAudioP25Status
    | null;

  p25?:
    LiveAudioP25Status
    | null;

  stream?: {
    error?: string | null;
    attempts?: number;
    transport?: string;
  } | null;
};


type CallsProcessorStatus = {
  state?: string;
  running?: boolean;
  error?: string | null;
  audio_download_count?: number;
  audio_decode_count?: number;
  audio_bridge_count?: number;
  calls_completed?: number;
  current_call_error_stage?: string | null;
  last_rf_tx_evidence?: {
    modem_reported_tx?: boolean;
    modem_tx_on_events?: number;
    modem_tx_off_events?: number;
    mmdvm_errors?: string[];
    rf_verified?: boolean;
    rf?: {state?: string; power_dbm?: number | null};
    verification_note?: string;
  } | null;
  last_audio_bridge_result?: {
    network_records?: number;
    sender_stats?: Record<string, unknown>;
  } | null;
};

type RfTxStatus = {
  runtime_active?: boolean;
  runtime_ready?: boolean;
  modem_rf_tx_active?: boolean;
  rf_verified?: boolean;
  hardware_tx_observation?: string;
  last_error?: string | null;
};

type RouteStatusResponse = {
  rf_tx?: RfTxStatus | null;
  runtime:
    RouteRuntimeStatus
    | null;

  worker:
    RouteWorkerStatus
    | null;

  live_audio?:
    LiveAudioStatus
    | null;

  processor?:
    CallsProcessorStatus | null;

  queue?:
    RouteQueueStats;
};


type RoutePreflightApiResponse = {
  route: Route;

  runtime: RouteRuntimeStatus;

  worker:
    RouteWorkerStatus
    | null;

  live_audio?:
    LiveAudioStatus
    | null;

  processor?:
    CallsProcessorStatus | null;

  queue:
    RouteQueueStats;
};


type RoutesPanelProps = {
  apiBaseUrl: string;

  onRoutesChanged?: (
    count: number
  ) => void;
  onSourcesChanged?: () => void;
};


type PreflightCheck =
  | "source"
  | "rf"
  | "config"
  | "audio_bridge";


type SourceUrlKind = "auto" | "direct_audio" | "remote_sdr";


const SOURCE_URL_PLACEHOLDERS: Record<SourceUrlKind, string> = {
  auto: "https://www.broadcastify.com/calls/playlists/?uuid=...",
  direct_audio: "http://192.168.1.50:8000/live.mp3",
  remote_sdr: "rtl_tcp://192.168.1.50:1234?freq=145500000&mod=nfm",
};


const PROTOCOLS:
  Protocol[] = [
    "fm",
    "dmr",
    "ysf",
    "dstar",
    "nxdn",
    "p25",
    "tetra",
  ];


function getSourceDisplayName(
  source:
    Source
    | undefined
): string {
  if (!source) {
    return "Unknown source";
  }

  const pageName =
    source.probe
      ?.page_name
      ?.trim();

  if (pageName) {
    return pageName;
  }

  const sourceName =
    source.name.trim();

  if (sourceName) {
    return sourceName;
  }

  return source.id;
}


function getSourceSelectionLabel(source: Source): string {
  const suffix = source.type === "broadcastify_calls"
    ? "Calls API / JWT"
    : source.type === "broadcastify_live_audio"
      ? "LEGACY Live Audio / website sign-in"
      : source.type === "direct_audio"
        ? "Direct HTTP Audio"
        : source.type === "remote_sdr"
          ? "Remote SDR"
          : source.type;
  return `${getSourceDisplayName(source)} — ${suffix}`;
}


function getDeviceDisplayName(
  device:
    RFDevice
    | undefined
): string {
  if (!device) {
    return "Unknown RF device";
  }

  if (
    device.driver
      .toLowerCase()
    ===
    "sx"
  ) {
    return "SXceiver";
  }

  const label =
    device.label.trim();

  if (label) {
    return label;
  }

  return device.driver;
}


function getWorkerStateLabel(
  worker:
    RouteWorkerStatus
    | null
    | undefined
): string {
  if (!worker) {
    return "STOPPED";
  }

  switch (
    worker.state
  ) {
    case "starting":
      return "STARTING";

    case "waiting_for_api_configuration":
      return "WAITING";

    case "polling":
      return "POLLING";

    case "idle":
      return "IDLE";

    case "stopping":
      return "STOPPING";

    case "error":
      return "ERROR";

    case "stopped":
    default:
      return "STOPPED";
  }
}


function getWorkerStateClass(
  worker:
    RouteWorkerStatus
    | null
    | undefined
): string {
  if (!worker) {
    return "stopped";
  }

  if (
    worker.state
    ===
    "error"
  ) {
    return "error";
  }

  if (
    worker.state
    ===
    "waiting_for_api_configuration"
    ||
    worker.state
    ===
    "starting"
  ) {
    return "waiting";
  }

  if (
    worker.running
  ) {
    return "running";
  }

  return "stopped";
}


function getLiveAudioStateLabel(
  liveAudio:
    LiveAudioStatus
    | null
    | undefined
): string {
  if (!liveAudio) {
    return "STOPPED";
  }

  switch (
    liveAudio.state
  ) {
    case "starting":
      return "STARTING";

    case "connecting":
      return "CONNECTING";

    case "listening":
      return "LISTENING";

    case "transmitting":
      return "TRANSMITTING";

    case "stopping":
      return "STOPPING";

    case "error":
      return "ERROR";

    case "stopped":
    default:
      return (
        liveAudio.running
          ? "RUNNING"
          : "STOPPED"
      );
  }
}


function getLiveAudioStateClass(
  liveAudio:
    LiveAudioStatus
    | null
    | undefined
): string {
  if (!liveAudio) {
    return "stopped";
  }

  if (
    liveAudio.state
    ===
    "error"
  ) {
    return "error";
  }

  if (
    liveAudio.state
    ===
    "starting"
    ||
    liveAudio.state
    ===
    "connecting"
  ) {
    return "waiting";
  }

  if (
    liveAudio.running
  ) {
    return "running";
  }

  return "stopped";
}


function getRuntimeStateLabel(
  runtime:
    RouteRuntimeStatus
    | null
    | undefined
): string {
  if (!runtime) {
    return "LOADING";
  }

  switch (
    runtime.state
  ) {
    case "starting":
      return "STARTING";

    case "ready":
      return "READY";

    case "running":
      return "RUNNING";

    case "blocked":
      return "BLOCKED";

    case "error":
      return "ERROR";

    case "stopped":
    default:
      return "STOPPED";
  }
}


function getRuntimeStateClass(
  runtime:
    RouteRuntimeStatus
    | null
    | undefined
): string {
  if (!runtime) {
    return "stopped";
  }

  switch (
    runtime.state
  ) {
    case "ready":
    case "running":
      return "running";

    case "starting":
    case "blocked":
      return "waiting";

    case "error":
      return "error";

    case "stopped":
    default:
      return "stopped";
  }
}


function getPreflightCheckLabel(
  runtime:
    RouteRuntimeStatus
    | null
    | undefined,
  check: PreflightCheck
): string {
  if (!runtime) {
    return "--";
  }

  if (
    runtime.blocked_reason
    ===
    "route_disabled"
  ) {
    return "--";
  }

  switch (
    check
  ) {
    case "source":
      return (
        runtime.source_ready
          ? "READY"
          : "NOT READY"
      );

    case "rf":
      if (
        !runtime.source_ready
      ) {
        return "--";
      }

      return (
        runtime.rf_ready
          ? "READY"
          : "NOT READY"
      );

    case "config":
      if (
        !runtime.rf_ready
      ) {
        return "--";
      }

      return (
        runtime.config_ready
          ? "READY"
          : "NOT READY"
      );

    case "audio_bridge":
      if (
        !runtime.config_ready
      ) {
        return "--";
      }

      return (
        runtime.audio_bridge_ready
          ? "READY"
          : "BLOCKED"
      );

    default:
      return "--";
  }
}


function formatDbfs(
  value:
    number
    | null
    | undefined
): string {
  if (
    value === null
    ||
    value === undefined
    ||
    !Number.isFinite(
      value
    )
  ) {
    return "--";
  }

  return (
    `${value.toFixed(1)} dBFS`
  );
}


function isRouteActuallyRunning(
  status:
    RouteStatusResponse
    | undefined
): boolean {
  if (!status) {
    return false;
  }

  return Boolean(
    status.runtime
      ?.active
    ||
    status.worker
      ?.running
    ||
    status.live_audio
      ?.running
  );
}


async function readApiObject(
  response: Response
): Promise<
  Record<string, unknown>
  | null
> {
  try {
    const value =
      await response.json();

    if (
      value
      &&
      typeof value
      ===
      "object"
      &&
      !Array.isArray(
        value
      )
    ) {
      return value as
        Record<
          string,
          unknown
        >;
    }

    return null;

  } catch {
    return null;
  }
}


function getApiError(
  data:
    Record<string, unknown>
    | null,
  fallback: string
): string {
  if (
    data
    &&
    typeof data.detail
    ===
    "string"
  ) {
    return data.detail;
  }

  if (
    data
    &&
    typeof data.message
    ===
    "string"
  ) {
    return data.message;
  }

  return fallback;
}


type CatalogItem = {
  kind: "playlist" | "group" | "node";
  id: string;
  name: string;
  url: string;
};

function CallsCatalogPicker({
  apiBaseUrl,
  onSelect,
}: {
  apiBaseUrl: string;
  onSelect: (item: CatalogItem) => void;
}) {
  const [kind, setKind] = useState<CatalogItem["kind"]>("playlist");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [scope, setScope] = useState("");
  const search = async () => {
    setBusy(true);
    setMessage(null);
    setItems([]);
    try {
      const params = new URLSearchParams({ kind, q: query.trim(), limit: "100" });
      const res = await fetch(`${apiBaseUrl}/api/sources/broadcastify/catalog?${params}`);
      const body = await res.json();
      if (!res.ok) throw new Error(body?.detail || `Catalog HTTP ${res.status}`);
      setItems(body.items || []);
      setScope(body.catalog_scope || "");
      if (!body.items?.length) setMessage("No entries matching your search.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Catalog not available");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="calls-catalog">
      <div className="calls-catalog__search">
        <select value={kind} onChange={(event) => {
          setKind(event.target.value as CatalogItem["kind"]);
          setItems([]);
          setMessage(null);
        }}>
          <option value="playlist">Public playlists</option>
          <option value="group">Active groups (sample)</option>
          <option value="node">Active systems/sites (sample)</option>
        </select>
        <input type="search" value={query} placeholder="FDNY, Indianapolis, dispatch..."
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") { event.preventDefault(); void search(); }
          }} />
        <button type="button" disabled={busy} onClick={() => { void search(); }}>
          {busy ? "LOADING..." : "SEARCH"}
        </button>
      </div>
      {scope === "live_sample_only" && (
        <small>Currently active public sample only, not the full county catalog.</small>
      )}
      {message && <small>{message}</small>}
      <div className="calls-catalog__results">
        {items.map((item) => (
          <button type="button" className="calls-catalog__item"
            key={`${item.kind}:${item.id}`} onClick={() => onSelect(item)}>
            <span>{item.name}</span>
            <small>{item.kind} · {item.id} · SELECT</small>
          </button>
        ))}
      </div>
    </div>
  );
}


function RoutesPanel({
  apiBaseUrl,
  onRoutesChanged,
  onSourcesChanged,
}: RoutesPanelProps) {
  const [
    routes,
    setRoutes,
  ] =
    useState<Route[]>(
      []
    );

  const [
    sources,
    setSources,
  ] =
    useState<Source[]>(
      []
    );

  const [
    devices,
    setDevices,
  ] =
    useState<RFDevice[]>(
      []
    );

  const [
    statuses,
    setStatuses,
  ] =
    useState<
      Record<
        string,
        RouteStatusResponse
      >
    >(
      {}
    );

  const [
    expandedRoutes,
    setExpandedRoutes,
  ] =
    useState<
      Record<
        string,
        boolean
      >
    >(
      {}
    );

  const [
    loading,
    setLoading,
  ] =
    useState(
      true
    );

  const [
    error,
    setError,
  ] =
    useState<
      string
      | null
    >(
      null
    );

  // A route-specific failure must not look like a global Calls API outage.
  const [routeActionErrors, setRouteActionErrors] = useState<Record<string, string>>({});
  const [routeNotices, setRouteNotices] = useState<Record<string, string>>({});

  const [
    actionRouteId,
    setActionRouteId,
  ] =
    useState<
      string
      | null
    >(
      null
    );

  const [
    createOpen,
    setCreateOpen,
  ] =
    useState(
      false
    );

  const [
    createBusy,
    setCreateBusy,
  ] =
    useState(
      false
    );

  const [editingRouteId, setEditingRouteId] = useState<string | null>(null);
  const [editSourceMode, setEditSourceMode] = useState<"saved" | "url" | "playlist" | "groups" | "node" | "catalog">("saved");
  const [editNodeId, setEditNodeId] = useState("");
  const [editPlaylistUuid, setEditPlaylistUuid] = useState("");
  const [editGroups, setEditGroups] = useState("");
  const [editSourceId, setEditSourceId] = useState("");
  const [editSourceUrl, setEditSourceUrl] = useState("");
  const [editSourceKind, setEditSourceKind] = useState<SourceUrlKind>("auto");
  const [editRouteName, setEditRouteName] = useState("");
  const [editDeviceId, setEditDeviceId] = useState("");
  const [editProtocol, setEditProtocol] = useState<Protocol>("p25");

  const [sourceMode, setSourceMode] = useState<"url" | "saved" | "playlist" | "groups" | "node" | "catalog">("catalog");
  const [nodeId, setNodeId] = useState("");
  const [playlistUuid, setPlaylistUuid] = useState("");
  const [callsGroups, setCallsGroups] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceKind, setSourceKind] = useState<SourceUrlKind>("auto");
  const [routeName, setRouteName] = useState("");
  const [startNow, setStartNow] = useState(false);

  const [
    selectedSourceId,
    setSelectedSourceId,
  ] =
    useState(
      ""
    );

  const [
    selectedDeviceId,
    setSelectedDeviceId,
  ] =
    useState(
      ""
    );

  const [
    selectedProtocol,
    setSelectedProtocol,
  ] =
    useState<Protocol>(
      "p25"
    );


  const loadSources =
    useCallback(
      async () => {
        const response =
          await fetch(
            `${apiBaseUrl}/api/sources`,
            {
              cache:
                "no-store",
            }
          );

        if (
          !response.ok
        ) {
          throw new Error(
            `Sources HTTP ${response.status}`
          );
        }

        const data =
          (
            await response.json()
          ) as SourcesResponse;

        setSources(
          data.sources
        );

        setSelectedSourceId(
          (
            current
          ) => {
            if (
              current
              &&
              data.sources.some(
                (
                  source
                ) =>
                  source.id
                  ===
                  current
              )
            ) {
              return current;
            }

            return (
              data.sources[
                0
              ]?.id
              ??
              ""
            );
          }
        );
      },
      [
        apiBaseUrl,
      ]
    );


  const loadDevices =
    useCallback(
      async () => {
        const response =
          await fetch(
            `${apiBaseUrl}/api/devices`,
            {
              cache:
                "no-store",
            }
          );

        if (
          !response.ok
        ) {
          throw new Error(
            `Devices HTTP ${response.status}`
          );
        }

        const data =
          (
            await response.json()
          ) as RFDevicesResponse;

        const usable =
          data.devices.filter(
            (
              device
            ) =>
              device.available
              &&
              device.probe_ok
          );

        setDevices(
          usable
        );

        setSelectedDeviceId(
          (
            current
          ) => {
            if (
              current
              &&
              usable.some(
                (
                  device
                ) =>
                  device.id
                  ===
                  current
              )
            ) {
              return current;
            }

            return (
              usable[
                0
              ]?.id
              ??
              ""
            );
          }
        );
      },
      [
        apiBaseUrl,
      ]
    );


  const loadRoutes =
    useCallback(
      async () => {
        const response =
          await fetch(
            `${apiBaseUrl}/api/routes`,
            {
              cache:
                "no-store",
            }
          );

        if (
          !response.ok
        ) {
          throw new Error(
            `Routes HTTP ${response.status}`
          );
        }

        const data =
          (
            await response.json()
          ) as RoutesResponse;

        setRoutes(
          data.routes
        );

        onRoutesChanged?.(
          data.count
        );

        return data.routes;
      },
      [
        apiBaseUrl,
        onRoutesChanged,
      ]
    );


  const storeStatus =
    useCallback(
      (
        routeId: string,
        status:
          RouteStatusResponse
      ) => {
        setStatuses(
          (
            current
          ) => ({
            ...current,

            [
              routeId
            ]:
              status,
          })
        );
      },
      []
    );


  const loadRuntimeStatus =
    useCallback(
      async (
        routeId: string
      ) => {
        try {
          const response =
            await fetch(
              (
                `${apiBaseUrl}` +
                `/api/routes/` +
                `${routeId}/runtime`
              ),
              {
                cache:
                  "no-store",
              }
            );

          if (
            !response.ok
          ) {
            return null;
          }

          const data =
            (
              await response.json()
            ) as RouteStatusResponse;

          storeStatus(
            routeId,
            data
          );

          return data;

        } catch {
          return null;
        }
      },
      [
        apiBaseUrl,
        storeStatus,
      ]
    );


  const runPreflight =
    useCallback(
      async (
        routeId: string
      ) => {
        try {
          const response =
            await fetch(
              (
                `${apiBaseUrl}` +
                `/api/routes/` +
                `${routeId}/preflight`
              ),
              {
                method:
                  "POST",

                cache:
                  "no-store",
              }
            );

          if (
            !response.ok
          ) {
            return null;
          }

          const data =
            (
              await response.json()
            ) as RoutePreflightApiResponse;

          const status:
            RouteStatusResponse = {
              runtime:
                data.runtime,

              worker:
                data.worker,

              live_audio:
                data.live_audio
                ??
                null,

              processor:
                data.processor,

              queue:
                data.queue,
            };

          storeStatus(
            routeId,
            status
          );

          return status;

        } catch {
          return null;
        }
      },
      [
        apiBaseUrl,
        storeStatus,
      ]
    );


  const refreshRouteStatus =
    useCallback(
      async (
        route: Route,
        allowPreflight: boolean
      ) => {
        const status =
          await loadRuntimeStatus(
            route.id
          );

        const running =
          isRouteActuallyRunning(
            status
            ??
            undefined
          );

        if (
          allowPreflight
          &&
          route.enabled
          &&
          !running
        ) {
          await runPreflight(
            route.id
          );
        }
      },
      [
        loadRuntimeStatus,
        runPreflight,
      ]
    );


  const refreshAll =
    useCallback(
      async () => {
        setError(
          null
        );

        try {
          const [
            routeList,
          ] =
            await Promise.all([
              loadRoutes(),
              loadSources(),
              loadDevices(),
            ]);

          await Promise.all(
            routeList.map(
              (
                route
              ) =>
                refreshRouteStatus(
                  route,
                  true
                )
            )
          );

        } catch (
          caught
        ) {
          if (
            caught instanceof
            Error
          ) {
            setError(
              caught.message
            );

          } else {
            setError(
              "Unable to load routes"
            );
          }
        }
      },
      [
        loadRoutes,
        loadSources,
        loadDevices,
        refreshRouteStatus,
      ]
    );


  useEffect(
    () => {
      let cancelled =
        false;

      const initialLoad =
        async () => {
          setLoading(
            true
          );

          await refreshAll();

          if (
            !cancelled
          ) {
            setLoading(
              false
            );
          }
        };

      void initialLoad();

      return () => {
        cancelled =
          true;
      };
    },
    [
      refreshAll,
    ]
  );


  useEffect(
    () => {
      const timer =
        window.setInterval(
          () => {
            for (
              const route
              of routes
            ) {
              void loadRuntimeStatus(
                route.id
              );
            }
          },
          1000
        );

      return () => {
        window.clearInterval(
          timer
        );
      };
    },
    [
      routes,
      loadRuntimeStatus,
    ]
  );


  const handleCreateRoute = async () => {
    if (sourceMode === "catalog") {
      setError("Select a Calls catalog result first"); return;
    }
    if (sourceMode === "node" && !nodeId.trim()) {
      setError("Select a Calls node"); return;
    }
    if (sourceMode === "playlist" && !playlistUuid.trim()) {
      setError("Enter a Calls playlist UUID");
      return;
    }
    if (sourceMode === "groups" && !callsGroups.trim()) {
      setError("Enter one or more Calls group IDs");
      return;
    }
    if (sourceMode === "url" && !sourceUrl.trim()) {
      setError("Enter a Broadcastify Calls playlist or Live Audio feed URL");
      return;
    }
    if (sourceMode === "saved" && !selectedSourceId) {
      setError("Select an existing source");
      return;
    }
    if (!selectedDeviceId) {
      setError("Select an RF device");
      return;
    }

    setCreateBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/routes/setup`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: routeName.trim() || null,
            source_id: sourceMode === "saved" ? selectedSourceId : null,
            source_url: sourceMode === "url" ? sourceUrl.trim() : null,
            source_type: sourceMode === "url" ? sourceKind : "auto",
            playlist_uuid: sourceMode === "playlist" ? playlistUuid.trim() : null,
            node_id: sourceMode === "node" ? nodeId.trim() : null,
            group_ids: sourceMode === "groups" ? callsGroups.split(",").map((s) => s.trim()).filter(Boolean) : null,
            device_id: selectedDeviceId,
            protocol: selectedProtocol,
            start_now: startNow,
          }),
        }
      );
      const data = await readApiObject(response);
      if (!response.ok) {
        throw new Error(
          getApiError(data, `Create route HTTP ${response.status}`)
        );
      }

      setCreateOpen(false);
      setSourceUrl("");
      setSourceKind("auto");
      setPlaylistUuid("");
      setCallsGroups("");
      setNodeId("");
      setRouteName("");
      setStartNow(false);
      await refreshAll();
      if (data?.source_created) onSourcesChanged?.();

      if (startNow && data?.start) {
        const startStatus = data.start as {
          started?: boolean;
          message?: string;
          runtime?: RouteRuntimeStatus;
        };
        if (startStatus.started === false) {
          setError(
            "Route saved, but not started: " +
            (startStatus.runtime?.error ||
              startStatus.runtime?.blocked_reason ||
              startStatus.message ||
              "preflight failed")
          );
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create route");
    } finally {
      setCreateBusy(false);
    }
  };


  const handleToggleEnabled =
    async (
      route: Route
    ) => {
      setActionRouteId(
        route.id
      );

      setError(
        null
      );

      try {
        const response =
          await fetch(
            (
              `${apiBaseUrl}` +
              `/api/routes/${route.id}`
            ),
            {
              method:
                "PUT",

              headers: {
                "Content-Type":
                  "application/json",
              },

              body:
                JSON.stringify({
                  enabled:
                    !route.enabled,
                }),
            }
          );

        if (
          !response.ok
        ) {
          const data =
            await readApiObject(
              response
            );

          throw new Error(
            getApiError(
              data,
              (
                `Update route HTTP ` +
                `${response.status}`
              )
            )
          );
        }

        await refreshAll();

      } catch (
        caught
      ) {
        if (
          caught instanceof
          Error
        ) {
          setError(
            caught.message
          );
        }

      } finally {
        setActionRouteId(
          null
        );
      }
    };


  const openRouteEditor = (route: Route) => {
    setEditingRouteId(route.id);
    setEditRouteName(route.name);
    setEditSourceMode("saved");
    setEditSourceId(route.source_id);
    setEditSourceUrl("");
    setEditSourceKind("auto");
    setEditPlaylistUuid("");
    setEditGroups("");
    setEditNodeId("");
    setEditDeviceId(route.device_id);
    setEditProtocol(route.protocol);
    setExpandedRoutes((current) => ({ ...current, [route.id]: true }));
    setError(null);
  };

  const saveEditedRoute = async (route: Route) => {
    if (!editRouteName.trim() || !editDeviceId) {
      setError("Enter a route name and RF device");
      return;
    }
    if ((editSourceMode === "saved" && !editSourceId) ||
        (editSourceMode === "url" && !editSourceUrl.trim()) ||
        (editSourceMode === "playlist" && !editPlaylistUuid.trim()) ||
        (editSourceMode === "groups" && !editGroups.trim()) ||
        (editSourceMode === "node" && !editNodeId.trim()) ||
        editSourceMode === "catalog") {
      setError("Select a source or provide its URL");
      return;
    }

    setActionRouteId(route.id);
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/routes/${route.id}/setup`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: editRouteName.trim(),
            source_id: editSourceMode === "saved" ? editSourceId : null,
            source_url: editSourceMode === "url" ? editSourceUrl.trim() : null,
            source_type: editSourceMode === "url" ? editSourceKind : "auto",
            playlist_uuid: editSourceMode === "playlist" ? editPlaylistUuid.trim() : null,
            node_id: editSourceMode === "node" ? editNodeId.trim() : null,
            group_ids: editSourceMode === "groups" ? editGroups.split(",").map((s) => s.trim()).filter(Boolean) : null,
            device_id: editDeviceId,
            protocol: editProtocol,
            start_now: false,
          }),
        }
      );
      const data = await readApiObject(response);
      if (!response.ok) {
        throw new Error(
          getApiError(data, `Unable to save route: HTTP ${response.status}`)
        );
      }

      setEditingRouteId(null);
      await refreshAll();
      if (data?.source_created) onSourcesChanged?.();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save route");
    } finally {
      setActionRouteId(null);
    }
  };


  const handleDelete =
    async (
      route: Route
    ) => {
      if (!window.confirm(
        `Delete "${route.name}"? Its source will also be deleted if no other route uses it.`
      )) {
        return;
      }

      setActionRouteId(
        route.id
      );

      setError(
        null
      );

      try {
        const response =
          await fetch(
            (
              `${apiBaseUrl}` +
              `/api/routes/${route.id}?cleanup_source=true`
            ),
            {
              method:
                "DELETE",
            }
          );

        if (
          !response.ok
        ) {
          throw new Error(
            (
              `Delete route HTTP ` +
              `${response.status}`
            )
          );
        }

        const deleted = await readApiObject(response);
        if (deleted?.source_deleted) onSourcesChanged?.();
        if (deleted?.source_cleanup_error) {
          setError(
            `Route deleted; source cleanup failed: ${deleted.source_cleanup_error}`
          );
        }
        if (editingRouteId === route.id) setEditingRouteId(null);

        setStatuses(
          (
            current
          ) => {
            const next = {
              ...current,
            };

            delete next[
              route.id
            ];

            return next;
          }
        );

        setExpandedRoutes(
          (
            current
          ) => {
            const next = {
              ...current,
            };

            delete next[
              route.id
            ];

            return next;
          }
        );

        await refreshAll();

      } catch (
        caught
      ) {
        if (
          caught instanceof
          Error
        ) {
          setError(
            caught.message
          );
        }

      } finally {
        setActionRouteId(
          null
        );
      }
    };


  const handleRouteStart =
    async (
      route: Route
    ) => {
      setActionRouteId(
        route.id
      );

      setError(null);
      setRouteActionErrors((current) => {
        const next = { ...current };
        delete next[route.id];
        return next;
      });

      try {
        const response =
          await fetch(
            (
              `${apiBaseUrl}` +
              `/api/routes/` +
              `${route.id}/start`
            ),
            {
              method:
                "POST",
            }
          );

        const data =
          await readApiObject(
            response
          );

        if (
          !response.ok
        ) {
          throw new Error(
            getApiError(
              data,
              (
                `Route start HTTP ` +
                `${response.status}`
              )
            )
          );
        }

        if (data && data.started === false) {
          const runtime = data.runtime as RouteRuntimeStatus | undefined;
          throw new Error(
            (typeof data.message === "string" && data.message.startsWith("RF runtime:") ? data.message : null) ||
            runtime?.error ||
            runtime?.blocked_reason ||
            getApiError(data, "Route did not start")
          );
        }

        const rfMessage = data && typeof data.rf_runtime_message === "string" ? data.rf_runtime_message : null;
        setRouteNotices((current) => {
          const next = { ...current };
          if (rfMessage) {
            next[route.id] = rfMessage;
          } else {
            delete next[route.id];
          }
          return next;
        });

        await loadRuntimeStatus(
          route.id
        );

      } catch (
        caught
      ) {
        if (
          caught instanceof
          Error
        ) {
          setRouteActionErrors((current) => ({
            ...current,
            [route.id]: caught.message,
          }));
        }

      } finally {
        setActionRouteId(
          null
        );
      }
    };


  const handleRouteStop =
    async (
      route: Route
    ) => {
      setActionRouteId(
        route.id
      );

      setError(
        null
      );

      try {
        const response =
          await fetch(
            (
              `${apiBaseUrl}` +
              `/api/routes/` +
              `${route.id}/stop`
            ),
            {
              method:
                "POST",
            }
          );

        const data =
          await readApiObject(
            response
          );

        if (
          !response.ok
        ) {
          throw new Error(
            getApiError(
              data,
              (
                `Route stop HTTP ` +
                `${response.status}`
              )
            )
          );
        }

        await refreshRouteStatus(
          route,
          true
        );

      } catch (
        caught
      ) {
        if (
          caught instanceof
          Error
        ) {
          setError(
            caught.message
          );
        }

      } finally {
        setActionRouteId(
          null
        );
      }
    };


  const toggleExpanded =
    (
      routeId: string
    ) => {
      setExpandedRoutes(
        (
          current
        ) => ({
          ...current,

          [
            routeId
          ]:
            !current[
              routeId
            ],
        })
      );
    };


  return (
    <section className="routes-panel">
      <div className="routes-panel__header">
        <div>
          <h2>
            Routes
          </h2>

          <p>
            Configure source, RF device and protocol in one place
          </p>
        </div>

        <div className="routes-panel__header-actions">
          <button
            type="button"
            className="routes-panel__add"
            onClick={
              () =>
                setCreateOpen(
                  (
                    current
                  ) =>
                    !current
                )
            }
          >
            {createOpen
              ? "CANCEL"
              : "+ ADD ROUTE"}
          </button>
        </div>
      </div>


      {createOpen && (
        <div className="route-create">
          <label>
            <span>Calls source</span>
            <select
              value={sourceMode}
              onChange={(event) => setSourceMode(event.target.value as
                "playlist" | "groups" | "saved" | "url" | "node" | "catalog")}
            >
              <option value="catalog">Browse Broadcastify Calls</option>
              <option value="playlist">Calls playlist UUID</option>
              <option value="groups">Calls group IDs (1–5)</option>
              <option value="node">Calls node ID</option>
              <option value="saved">Existing saved source</option>
              <option value="url">Advanced: Source URL</option>
            </select>
          </label>

          {sourceMode === "catalog" ? (
            <div className="route-create__wide">
              <CallsCatalogPicker apiBaseUrl={apiBaseUrl} onSelect={(item) => {
                setRouteName(item.name);
                if (item.kind === "playlist") {
                  setPlaylistUuid(item.id); setSourceMode("playlist");
                } else if (item.kind === "group") {
                  setCallsGroups(item.id); setSourceMode("groups");
                } else {
                  setNodeId(item.id); setSourceMode("node");
                }
              }} />
            </div>
          ) : sourceMode === "node" ? (
            <label className="route-create__wide">
              <span>Selected Calls node ID</span>
              <input value={nodeId} onChange={(event) => setNodeId(event.target.value)} />
            </label>
          ) : sourceMode === "playlist" ? (
            <label className="route-create__wide">
              <span>Broadcastify Calls playlist UUID</span>
              <input
                type="text"
                value={playlistUuid}
                onChange={(event) => setPlaylistUuid(event.target.value)}
                placeholder="Paste UUID, without the playlist URL"
              />
              <small>Uses the existing JWT Calls API. No website login or separate Source setup.</small>
            </label>
          ) : sourceMode === "groups" ? (
            <label className="route-create__wide">
              <span>Broadcastify Calls group IDs (comma-separated)</span>
              <input
                type="text"
                value={callsGroups}
                onChange={(event) => setCallsGroups(event.target.value)}
                placeholder="2-3416, 2-3417, c-223312"
              />
              <small>One to five groups; formats SID-TG or c-FID. These are Broadcastify IDs, not DMR TG numbers.</small>
            </label>
          ) : sourceMode === "saved" ? (
            <label className="route-create__wide">
              <span>Saved source</span>
              <select
                value={selectedSourceId}
                onChange={(event) => setSelectedSourceId(event.target.value)}
              >
                {sources.map((source) => (
                  <option key={source.id} value={source.id}>
                    {getSourceSelectionLabel(source)}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label className="route-create__wide">
              <span>Source URL</span>
              <select
                value={sourceKind}
                onChange={(event) => setSourceKind(event.target.value as SourceUrlKind)}
              >
                <option value="auto">Broadcastify URL (Calls playlist preferred)</option>
                <option value="direct_audio">Direct HTTP audio (authorized)</option>
                <option value="remote_sdr">Remote SDR (rtl_tcp / KiwiSDR / SDR audio)</option>
              </select>
              <input
                type="url"
                value={sourceUrl}
                onChange={(event) => setSourceUrl(event.target.value)}
                placeholder={SOURCE_URL_PLACEHOLDERS[sourceKind]}
              />
            </label>
          )}

          <label>
            <span>Route name (optional)</span>
            <input
              type="text"
              maxLength={120}
              value={routeName}
              onChange={(event) => setRouteName(event.target.value)}
              placeholder="Auto from source"
            />
          </label>

          <label>
            <span>RF Device</span>
            <select
              value={selectedDeviceId}
              onChange={(event) => setSelectedDeviceId(event.target.value)}
            >
              {devices.map((device) => (
                <option key={device.id} value={device.id}>
                  {getDeviceDisplayName(device)} · {device.id}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Protocol</span>
            <select
              value={selectedProtocol}
              onChange={(event) => setSelectedProtocol(event.target.value as Protocol)}
            >
              {PROTOCOLS.map((protocol) => (
                <option key={protocol} value={protocol}>
                  {protocol.toUpperCase()}
                </option>
              ))}
            </select>
          </label>

          <label className="route-create__start">
            <input
              type="checkbox"
              checked={startNow}
              onChange={(event) => setStartNow(event.target.checked)}
            />
            <span>Start immediately (may transmit RF if audio is available)</span>
          </label>

          <div className="route-create__actions">
            <button
              type="button"
              className="route-create__submit"
              disabled={
                createBusy ||
                !selectedDeviceId ||
                (sourceMode === "url" ? !sourceUrl.trim() :
                  sourceMode === "saved" ? !selectedSourceId :
                  sourceMode === "playlist" ? !playlistUuid.trim() :
                  sourceMode === "node" ? !nodeId.trim() :
                  sourceMode === "catalog" ? true : !callsGroups.trim())
              }
              onClick={() => { void handleCreateRoute(); }}
            >
              {createBusy ? "SAVING..." : startNow ? "CREATE & START" : "CREATE ROUTE"}
            </button>
          </div>
        </div>
      )}


      {error && (
        <div className="routes-panel__error">
          {error}
        </div>
      )}


      {loading ? (
        <div className="routes-panel__empty">
          Loading routes...
        </div>
      ) : routes.length === 0 ? (
        <div className="routes-panel__empty">
          No routes configured
        </div>
      ) : (
        <div className="routes-panel__list">
          {routes.map(
            (
              route
            ) => {
              const source =
                sources.find(
                  (
                    item
                  ) =>
                    item.id
                    ===
                    route.source_id
                );

              const device =
                devices.find(
                  (
                    item
                  ) =>
                    item.id
                    ===
                    route.device_id
                );

              const status =
                statuses[
                  route.id
                ];

              const runtime =
                status
                  ?.runtime
                ??
                null;

              const worker =
                status
                  ?.worker
                ??
                null;

              const liveAudio =
                status
                  ?.live_audio
                ??
                null;

              const queue =
                status
                  ?.queue;
              const processor = status?.processor ?? null;
              const rfTx = status?.rf_tx ?? null;
              const rfEvidence = processor?.last_rf_tx_evidence ?? null;

              const busy =
                actionRouteId
                ===
                route.id;

              const running =
                isRouteActuallyRunning(
                  status
                );

              const expanded =
                Boolean(
                  expandedRoutes[
                    route.id
                  ]
                );

              const isLiveAudio =
                source?.type === "broadcastify_live_audio"
                || source?.type === "direct_audio"
                || source?.type === "remote_sdr";
              const legacyLiveSource = source?.type === "broadcastify_live_audio";
              const legacyLiveBlocked = legacyLiveSource &&
                runtime?.blocked_reason === "source_stream_unavailable";
              const routeActionError = routeActionErrors[route.id];

              const processorFailed = !isLiveAudio && Boolean(processor?.error);
              const pipelineLabel = processorFailed
                ? "PROCESSOR ERROR"
                : isLiveAudio
                  ? getLiveAudioStateLabel(liveAudio)
                  : getWorkerStateLabel(worker);

              const pipelineClass = processorFailed
                ? "error"
                : isLiveAudio
                  ? getLiveAudioStateClass(liveAudio)
                  : getWorkerStateClass(worker);


              return (
                <article
                  className={
                    (
                      "route-card " +
                      (
                        expanded
                          ? "expanded"
                          : "collapsed"
                      )
                    )
                  }
                  key={
                    route.id
                  }
                  style={{
                    padding:
                      expanded
                        ? "12px"
                        : "10px 12px",

                    gap:
                      "10px",
                  }}
                >
                  <div className="route-card__main">
                    <div
                      className="route-card__title-row"
                      style={{
                        alignItems:
                          "center",
                      }}
                    >
                      <div
                        style={{
                          minWidth:
                            0,

                          flex:
                            "1 1 auto",
                        }}
                      >
                        <h3>
                          {route.name}
                        </h3>

                        <div
                          className="route-card__meta"
                          style={{
                            marginTop:
                              "3px",
                          }}
                        >
                          <span>
                            {
                              getSourceDisplayName(
                                source
                              )
                            }
                          </span>

                          <span>
                            {
                              getDeviceDisplayName(
                                device
                              )
                            }
                            {" · "}
                            {
                              route.device_id
                            }
                          </span>

                          <span>
                            {
                              route.protocol
                                .toUpperCase()
                            }
                          </span>
                        </div>
                      </div>


                      <div
                        className="route-card__badges"
                        style={{
                          position:
                            "static",

                          alignSelf:
                            "center",

                          marginLeft:
                            "12px",
                        }}
                      >
                        <span
                          className={
                            (
                              "route-card__badge " +
                              (
                                route.enabled
                                  ? "enabled"
                                  : "disabled"
                              )
                            )
                          }
                        >
                          {route.enabled
                            ? "ENABLED"
                            : "DISABLED"}
                        </span>


                        <span
                          className={
                            (
                              "route-worker__state " +
                              getRuntimeStateClass(
                                runtime
                              )
                            )
                          }
                        >
                          {
                            getRuntimeStateLabel(
                              runtime
                            )
                          }
                        </span>


                        <span
                          className={
                            (
                              "route-worker__state " +
                              pipelineClass
                            )
                          }
                        >
                          {pipelineLabel}
                        </span>
                      </div>
                    </div>


                    {(routeActionError || legacyLiveBlocked) && (
                      <div className="route-worker__error" role="alert">
                        {routeActionError && <div>{routeActionError}</div>}
                        {legacyLiveBlocked && !routeActionError && (
                          <div>Legacy Broadcastify Live Audio is unavailable without a website playback session.</div>
                        )}
                        {legacyLiveSource && (
                          <>
                            <div>
                              This is a website Live Audio feed, not Broadcastify Calls.
                              Developer JWT works for Calls playlists/groups/nodes, not this HLS feed.
                            </div>
                            {!running && (
                              <button type="button"
                                disabled={busy}
                                onClick={() => {
                                  openRouteEditor(route);
                                  setEditSourceMode("catalog");
                                  setRouteActionErrors((current) => {
                                    const next = { ...current };
                                    delete next[route.id];
                                    return next;
                                  });
                                }}>
                                CHOOSE CALLS API SOURCE
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    )}

                    {expanded && (
                      <>
                        {editingRouteId === route.id && (
                          <div className="route-edit">
                            <div className="route-edit__heading">
                              <strong>Edit route</strong>
                              <span>Save does not start RF. Stop the route before editing.</span>
                            </div>
                            <div className="route-edit__grid">
                              <label>
                                <span>Name</span>
                                <input
                                  type="text"
                                  maxLength={120}
                                  value={editRouteName}
                                  onChange={(event) => setEditRouteName(event.target.value)}
                                />
                              </label>
                              <label>
                                <span>Source selection</span>
                                <select
                                  value={editSourceMode}
                                  onChange={(event) => setEditSourceMode(
                                    event.target.value as "saved" | "url" | "playlist" | "groups" | "node" | "catalog"
                                  )}
                                >
                                  <option value="saved">Saved source</option>
                                  <option value="url">New source URL</option>
                                  <option value="playlist">Calls playlist UUID</option>
                                  <option value="groups">Calls group IDs (1–5)</option>
                                  <option value="node">Calls node ID</option>
                                  <option value="catalog">Browse Calls catalog</option>
                                </select>
                              </label>
                              {editSourceMode === "saved" ? (
                                <label className="route-edit__wide">
                                  <span>Saved source</span>
                                  <select value={editSourceId}
                                    onChange={(event) => setEditSourceId(event.target.value)}>
                                    {sources.map((item) => (
                                      <option key={item.id} value={item.id}>
                                        {getSourceSelectionLabel(item)}
                                      </option>
                                    ))}
                                  </select>
                                </label>
                              ) : editSourceMode === "catalog" ? (
                                <div className="route-edit__wide">
                                  <CallsCatalogPicker apiBaseUrl={apiBaseUrl} onSelect={(item) => {
                                    setEditRouteName(item.name);
                                    if (item.kind === "playlist") {
                                      setEditPlaylistUuid(item.id); setEditSourceMode("playlist");
                                    } else if (item.kind === "group") {
                                      setEditGroups(item.id); setEditSourceMode("groups");
                                    } else {
                                      setEditNodeId(item.id); setEditSourceMode("node");
                                    }
                                  }} />
                                </div>
                              ) : editSourceMode === "node" ? (
                                <label className="route-edit__wide">
                                  <span>Calls node ID</span>
                                  <input value={editNodeId} onChange={(event) => setEditNodeId(event.target.value)} />
                                </label>
                              ) : editSourceMode === "playlist" ? (
                                <label className="route-edit__wide">
                                  <span>Calls playlist UUID</span>
                                  <input type="text" value={editPlaylistUuid}
                                    placeholder="Playlist UUID"
                                    onChange={(event) => setEditPlaylistUuid(event.target.value)} />
                                </label>
                              ) : editSourceMode === "groups" ? (
                                <label className="route-edit__wide">
                                  <span>Calls group IDs (1–5)</span>
                                  <input type="text" value={editGroups}
                                    placeholder="2-3416, c-223312"
                                    onChange={(event) => setEditGroups(event.target.value)} />
                                </label>
                              ) : (
                                <label className="route-edit__wide">
                                  <span>Source URL</span>
                                  <select value={editSourceKind}
                                    onChange={(event) => setEditSourceKind(event.target.value as SourceUrlKind)}>
                                    <option value="auto">Broadcastify (detect)</option>
                                    <option value="direct_audio">Direct HTTP audio</option>
                                    <option value="remote_sdr">Remote SDR</option>
                                  </select>
                                  <input type="url" value={editSourceUrl}
                                    placeholder={SOURCE_URL_PLACEHOLDERS[editSourceKind]}
                                    onChange={(event) => setEditSourceUrl(event.target.value)} />
                                </label>
                              )}
                              <label>
                                <span>RF Device</span>
                                <select
                                  value={editDeviceId}
                                  onChange={(event) => setEditDeviceId(event.target.value)}
                                >
                                  {!devices.some((item) => item.id === editDeviceId) && (
                                    <option value={editDeviceId}>
                                      {editDeviceId} (not currently available)
                                    </option>
                                  )}
                                  {devices.map((item) => (
                                    <option key={item.id} value={item.id}>
                                      {getDeviceDisplayName(item)} · {item.id}
                                    </option>
                                  ))}
                                </select>
                              </label>
                              <label>
                                <span>Protocol</span>
                                <select
                                  value={editProtocol}
                                  onChange={(event) => setEditProtocol(
                                    event.target.value as Protocol
                                  )}
                                >
                                  {PROTOCOLS.map((item) => (
                                    <option key={item} value={item}>
                                      {item.toUpperCase()}
                                    </option>
                                  ))}
                                </select>
                              </label>
                            </div>
                            <div className="route-edit__actions">
                              <button
                                type="button"
                                disabled={busy || running}
                                onClick={() => { void saveEditedRoute(route); }}
                              >
                                {busy ? "SAVING..." : "SAVE CHANGES"}
                              </button>
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => setEditingRouteId(null)}
                              >
                                CANCEL
                              </button>
                            </div>
                          </div>
                        )}
                        <div
                          style={{
                            display:
                              "grid",

                            gridTemplateColumns:
                              (
                                "repeat(" +
                                "2, " +
                                "minmax(0, 1fr)" +
                                ")"
                              ),

                            gap:
                              "10px",
                          }}
                        >
                          {isLiveAudio ? (
                            <div className="route-worker">
                              <div className="route-worker__header">
                                <span>
                                  LIVE AUDIO
                                </span>

                                <strong
                                  className={
                                    (
                                      "route-worker__state " +
                                      getLiveAudioStateClass(
                                        liveAudio
                                      )
                                    )
                                  }
                                >
                                  {
                                    getLiveAudioStateLabel(
                                      liveAudio
                                    )
                                  }
                                </strong>
                              </div>


                              <div className="route-worker__stats">
                                <div>
                                  <span>
                                    PCM Chunks
                                  </span>

                                  <strong>
                                    {
                                      liveAudio
                                        ?.pcm_chunks_received
                                      ??
                                      0
                                    }
                                  </strong>
                                </div>


                                <div>
                                  <span>
                                    TX Starts
                                  </span>

                                  <strong>
                                    {
                                      liveAudio
                                        ?.tx_start_count
                                      ??
                                      0
                                    }
                                  </strong>
                                </div>


                                <div>
                                  <span>
                                    TX Ends
                                  </span>

                                  <strong>
                                    {
                                      liveAudio
                                        ?.tx_end_count
                                      ??
                                      0
                                    }
                                  </strong>
                                </div>


                                <div>
                                  <span>
                                    Audio Level
                                  </span>

                                  <strong>
                                    {
                                      formatDbfs(
                                        liveAudio
                                          ?.last_activity_level_dbfs
                                      )
                                    }
                                  </strong>
                                </div>
                              </div>


                              <div className="route-worker__stats">
                                <div>
                                  <span>
                                    {source?.type === "direct_audio" || source?.type === "remote_sdr" ? "INPUT" : "Feed ID"}
                                  </span>

                                  <strong>
                                    {
                                      liveAudio
                                        ?.feed_id
                                      ??
                                      source
                                        ?.feed_id
                                      ??
                                      "--"
                                    }
                                  </strong>
                                </div>


                                <div>
                                  <span>
                                    Trigger
                                  </span>

                                  <strong>
                                    {
                                      formatDbfs(
                                        liveAudio
                                          ?.last_trigger_dbfs
                                      )
                                    }
                                  </strong>
                                </div>


                                <div>
                                  <span>
                                    Noise Floor
                                  </span>

                                  <strong>
                                    {
                                      formatDbfs(
                                        liveAudio
                                          ?.last_noise_floor_dbfs
                                      )
                                    }
                                  </strong>
                                </div>


                                <div>
                                  <span>
                                    {(route.protocol ?? "p25").toUpperCase()} Records
                                  </span>

                                  <strong>
                                    {
                                      (liveAudio?.voice ?? liveAudio?.p25)
                                        ?.network_records_sent
                                      ??
                                      0
                                    }
                                  </strong>
                                </div>
                              </div>


                              {liveAudio?.error && (
                                <div className="route-worker__error">
                                  {liveAudio.error}
                                </div>
                              )}

                              {liveAudio?.stream?.error && (
                                <div className="route-worker__error">
                                  {liveAudio.stream.error} (reconnecting)
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="route-worker">
                              <div className="route-worker__header">
                                <span>
                                  SOURCE WORKER
                                </span>

                                <strong
                                  className={
                                    (
                                      "route-worker__state " +
                                      getWorkerStateClass(
                                        worker
                                      )
                                    )
                                  }
                                >
                                  {
                                    getWorkerStateLabel(
                                      worker
                                    )
                                  }
                                </strong>
                              </div>


                              <div className="route-worker__stats">
                                <div>
                                  <span>
                                    Queue
                                  </span>

                                  <strong>
                                    {
                                      queue
                                        ?.queue_size
                                      ??
                                      0
                                    }
                                  </strong>
                                </div>


                                <div>
                                  <span>
                                    Received
                                  </span>

                                  <strong>
                                    {
                                      worker
                                        ?.calls_received
                                      ??
                                      0
                                    }
                                  </strong>
                                </div>


                                <div>
                                  <span>
                                    Enqueued
                                  </span>

                                  <strong>
                                    {
                                      worker
                                        ?.calls_enqueued
                                      ??
                                      0
                                    }
                                  </strong>
                                </div>


                                <div>
                                  <span>
                                    Duplicates
                                  </span>

                                  <strong>
                                    {
                                      worker
                                        ?.calls_duplicates
                                      ??
                                      0
                                    }
                                  </strong>
                                </div>
                              </div>


                              <div className="route-worker__stats">
                                <div>
                                  <span>Completed</span>
                                  <strong>{processor?.calls_completed ?? 0}</strong>
                                </div>
                                <div>
                                  <span>Dequeued</span>
                                  <strong>{queue?.total_dequeued ?? 0}</strong>
                                </div>
                                <div>
                                  <span>Dropped</span>
                                  <strong>{queue?.total_dropped ?? 0}</strong>
                                </div>
                                <div>
                                  <span>Cleared</span>
                                  <strong>{queue?.total_cleared ?? 0}</strong>
                                </div>
                              </div>

                              <div className="route-worker__stats">
                                <div>
                                  <span>Audio downloads</span>
                                  <strong>{processor?.audio_download_count ?? 0}</strong>
                                </div>
                                <div>
                                  <span>PCM decoded</span>
                                  <strong>{processor?.audio_decode_count ?? 0}</strong>
                                </div>
                                <div>
                                  <span>{(route.protocol ?? "p25").toUpperCase()} handoffs</span>
                                  <strong>{processor?.audio_bridge_count ?? 0}</strong>
                                </div>
                                <div>
                                  <span>Last {(route.protocol ?? "p25").toUpperCase()} records</span>
                                  <strong>{isLiveAudio ? ((liveAudio?.voice ?? liveAudio?.p25)?.network_records_sent ?? 0) : (processor?.last_audio_bridge_result?.network_records ?? 0)}</strong>
                                </div>
                              </div>

                              <div className="route-worker__hint">
                                Handoff = sent toward MMDVM-Host; RF transmission is not confirmed.
                              </div>

                              {processor?.error && (
                                <div className="route-worker__error">
                                  Processor{processor.current_call_error_stage
                                    ? ` (${processor.current_call_error_stage})`
                                    : ""}: {processor.error}
                                </div>
                              )}

                              {worker?.error && (
                                <div className="route-worker__error">
                                  {worker.error}
                                </div>
                              )}
                            </div>
                          )}


                          <div className="route-worker">
                            <div className="route-worker__header">
                              <span>RF TX MONITOR (MMDVM)</span>
                              <strong className={"route-worker__state " +
                                (rfTx?.modem_rf_tx_active ? "running" : "stopped")}>
                                {rfTx?.modem_rf_tx_active ? "MODEM TX ON" :
                                  rfTx?.runtime_active ? "MODEM IDLE" : "NO RUNTIME"}
                              </strong>
                            </div>
                            <div className="route-worker__stats">
                              <div>
                                <span>Last network records</span>
                                <strong>{isLiveAudio ? ((liveAudio?.voice ?? liveAudio?.p25)?.network_records_sent ?? 0) : (processor?.last_audio_bridge_result?.network_records ?? 0)}</strong>
                              </div>
                              <div>
                                <span>Last UDP datagrams</span>
                                <strong>{isLiveAudio ? "see P25 records" : String(processor?.last_audio_bridge_result?.sender_stats?.datagrams_sent ?? "--")}</strong>
                              </div>
                              <div>
                                <span>Modem TX ON events</span>
                                <strong>{isLiveAudio ? (liveAudio?.tx_start_count ?? "--") : (rfEvidence?.modem_tx_on_events ?? "--")}</strong>
                              </div>
                              <div>
                                <span>Radiated RF evidence</span>
                                <strong>{rfEvidence?.rf_verified
                                  ? "RF DETECTED" : rfEvidence ? "UNVERIFIED" : "NO DATA"}</strong>
                              </div>
                            </div>
                            <div className="route-worker__hint">
                              MMDVM TX ON = modem report, not proof of antenna output.
                              Independent RF confirmation requires an external receiver.
                              {rfEvidence?.rf?.power_dbm != null
                                ? ` Last RF power: ${rfEvidence.rf.power_dbm} dBm.` : ""}
                            </div>
                            {rfTx?.last_error && (
                              <div className="route-worker__error">MMDVM: {rfTx.last_error}</div>
                            )}
                            {rfEvidence?.mmdvm_errors?.map((message, index) => (
                              <div className="route-worker__error" key={index}>{message}</div>
                            ))}
                          </div>

                          <div className="route-worker">
                            <div className="route-worker__header">
                              <span>
                                ROUTE PREFLIGHT
                              </span>

                              <strong
                                className={
                                  (
                                    "route-worker__state " +
                                    getRuntimeStateClass(
                                      runtime
                                    )
                                  )
                                }
                              >
                                {
                                  getRuntimeStateLabel(
                                    runtime
                                  )
                                }
                              </strong>
                            </div>


                            <div className="route-worker__stats">
                              <div>
                                <span>
                                  Source
                                </span>

                                <strong>
                                  {
                                    getPreflightCheckLabel(
                                      runtime,
                                      "source"
                                    )
                                  }
                                </strong>
                              </div>


                              <div>
                                <span>
                                  RF
                                </span>

                                <strong>
                                  {
                                    getPreflightCheckLabel(
                                      runtime,
                                      "rf"
                                    )
                                  }
                                </strong>
                              </div>


                              <div>
                                <span>
                                  Config
                                </span>

                                <strong>
                                  {
                                    getPreflightCheckLabel(
                                      runtime,
                                      "config"
                                    )
                                  }
                                </strong>
                              </div>


                              <div>
                                <span>
                                  Audio Bridge
                                </span>

                                <strong>
                                  {
                                    getPreflightCheckLabel(
                                      runtime,
                                      "audio_bridge"
                                    )
                                  }
                                </strong>
                              </div>
                            </div>


                            {runtime?.rf_runtime && (
                              <div
                                className={
                                  runtime.rf_runtime.matches
                                    ? "route-worker__hint"
                                    : runtime.rf_runtime.action === "blocked"
                                      ? "route-worker__error"
                                      : "route-worker__hint route-rf-warning"
                                }
                              >
                                RF OUTPUT:{" "}
                                {runtime.rf_runtime.runtime_active
                                  ? String(runtime.rf_runtime.runtime_protocol ?? "").toUpperCase()
                                  : "STOPPED"}
                                {" · ROUTE: "}
                                {runtime.rf_runtime.route_protocol.toUpperCase()}
                                {runtime.rf_runtime.matches
                                  ? " · OK"
                                  : runtime.rf_runtime.message
                                    ? ` · ${runtime.rf_runtime.message}`
                                    : ""}
                              </div>
                            )}

                            {routeNotices[route.id] && (
                              <div className="route-worker__hint">
                                {routeNotices[route.id]}
                              </div>
                            )}

                            {runtime?.blocked_reason && (
                              <div className="route-worker__error">
                                BLOCKED: {
                                  runtime.blocked_reason
                                }
                              </div>
                            )}


                            {runtime?.error && (
                              <div className="route-worker__error">
                                {runtime.error}
                              </div>
                            )}
                          </div>
                        </div>


                        <div
                          style={{
                            display:
                              "flex",

                            flexWrap:
                              "wrap",

                            alignItems:
                              "center",

                            gap:
                              "7px",

                            paddingTop:
                              "2px",
                          }}
                        >
                          {!running ? (
                            <button
                              type="button"
                              className="route-card__worker-start"
                              disabled={
                                busy
                              }
                              onClick={
                                () => {
                                  void handleRouteStart(
                                    route
                                  );
                                }
                              }
                            >
                              START ROUTE
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="route-card__worker-stop"
                              disabled={
                                busy
                              }
                              onClick={
                                () => {
                                  void handleRouteStop(
                                    route
                                  );
                                }
                              }
                            >
                              STOP ROUTE
                            </button>
                          )}


                          <button
                            type="button"
                            disabled={
                              busy
                            }
                            onClick={
                              () => {
                                void handleToggleEnabled(
                                  route
                                );
                              }
                            }
                          >
                            {route.enabled
                              ? "DISABLE"
                              : "ENABLE"}
                          </button>


                          <button
                            type="button"
                            disabled={busy || running}
                            onClick={() => editingRouteId === route.id
                              ? setEditingRouteId(null)
                              : openRouteEditor(route)}
                          >
                            {editingRouteId === route.id ? "CANCEL EDIT" : "EDIT"}
                          </button>


                          <button
                            type="button"
                            className="route-card__delete"
                            disabled={
                              busy
                              ||
                              running
                            }
                            onClick={
                              () => {
                                void handleDelete(
                                  route
                                );
                              }
                            }
                          >
                            DELETE
                          </button>
                        </div>
                      </>
                    )}
                  </div>


                  <div
                    className="route-card__actions"
                    style={{
                      minWidth:
                        "108px",

                      justifyContent:
                        "center",
                    }}
                  >
                    {!expanded && (
                      running ? (
                        <button
                          type="button"
                          className="route-card__worker-stop"
                          disabled={
                            busy
                          }
                          onClick={
                            () => {
                              void handleRouteStop(
                                route
                              );
                            }
                          }
                        >
                          STOP
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="route-card__worker-start"
                          disabled={
                            busy
                          }
                          onClick={
                            () => {
                              void handleRouteStart(
                                route
                              );
                            }
                          }
                        >
                          START
                        </button>
                      )
                    )}


                    <button
                      type="button"
                      className="route-card__details"
                      disabled={
                        busy
                      }
                      aria-expanded={
                        expanded
                      }
                      onClick={
                        () => {
                          toggleExpanded(
                            route.id
                          );
                        }
                      }
                    >
                      {expanded
                        ? "▲ HIDE"
                        : "▼ DETAILS"}
                    </button>
                  </div>
                </article>
              );
            }
          )}
        </div>
      )}
    </section>
  );
}


export default RoutesPanel;