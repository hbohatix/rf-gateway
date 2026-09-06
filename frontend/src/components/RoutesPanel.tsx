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
    "broadcastify_live_audio";

  feed_id: number;

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

  p25?:
    LiveAudioP25Status
    | null;
};


type RouteStatusResponse = {
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
    unknown;

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
    unknown;

  queue:
    RouteQueueStats;
};


type RoutesPanelProps = {
  apiBaseUrl: string;

  onRoutesChanged?: (
    count: number
  ) => void;
};


type PreflightCheck =
  | "source"
  | "rf"
  | "config"
  | "audio_bridge";


const PROTOCOLS:
  Protocol[] = [
    "fm",
    "dmr",
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


function RoutesPanel({
  apiBaseUrl,
  onRoutesChanged,
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


  const handleCreateRoute =
    async () => {
      if (
        !selectedSourceId
      ) {
        setError(
          "Select a source"
        );

        return;
      }

      if (
        !selectedDeviceId
      ) {
        setError(
          "Select an RF device"
        );

        return;
      }

      const source =
        sources.find(
          (
            item
          ) =>
            item.id
            ===
            selectedSourceId
        );

      if (
        !source
      ) {
        setError(
          "Selected source was not found"
        );

        return;
      }

      setCreateBusy(
        true
      );

      setError(
        null
      );

      try {
        const response =
          await fetch(
            `${apiBaseUrl}/api/routes`,
            {
              method:
                "POST",

              headers: {
                "Content-Type":
                  "application/json",
              },

              body:
                JSON.stringify({
                  name:
                    getSourceDisplayName(
                      source
                    ),

                  source_id:
                    selectedSourceId,

                  device_id:
                    selectedDeviceId,

                  protocol:
                    selectedProtocol,

                  enabled:
                    true,
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
                `Create route HTTP ` +
                `${response.status}`
              )
            )
          );
        }

        setCreateOpen(
          false
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

        } else {
          setError(
            "Unable to create route"
          );
        }

      } finally {
        setCreateBusy(
          false
        );
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


  const handleDelete =
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

      setError(
        null
      );

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

        if (
          data
          &&
          data.started
          ===
          false
        ) {
          throw new Error(
            getApiError(
              data,
              "Route did not start"
            )
          );
        }

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
            Internet sources routed to RF devices
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
            <span>
              Source
            </span>

            <select
              value={
                selectedSourceId
              }
              onChange={
                (
                  event
                ) =>
                  setSelectedSourceId(
                    event.target.value
                  )
              }
            >
              {sources.map(
                (
                  source
                ) => (
                  <option
                    key={
                      source.id
                    }
                    value={
                      source.id
                    }
                  >
                    {
                      getSourceDisplayName(
                        source
                      )
                    }
                  </option>
                )
              )}
            </select>
          </label>


          <label>
            <span>
              RF Device
            </span>

            <select
              value={
                selectedDeviceId
              }
              onChange={
                (
                  event
                ) =>
                  setSelectedDeviceId(
                    event.target.value
                  )
              }
            >
              {devices.map(
                (
                  device
                ) => (
                  <option
                    key={
                      device.id
                    }
                    value={
                      device.id
                    }
                  >
                    {
                      getDeviceDisplayName(
                        device
                      )
                    }
                    {" · "}
                    {device.id}
                  </option>
                )
              )}
            </select>
          </label>


          <label>
            <span>
              Protocol
            </span>

            <select
              value={
                selectedProtocol
              }
              onChange={
                (
                  event
                ) =>
                  setSelectedProtocol(
                    event.target.value as Protocol
                  )
              }
            >
              {PROTOCOLS.map(
                (
                  protocol
                ) => (
                  <option
                    key={
                      protocol
                    }
                    value={
                      protocol
                    }
                  >
                    {
                      protocol
                        .toUpperCase()
                    }
                  </option>
                )
              )}
            </select>
          </label>


          <div className="route-create__actions">
            <button
              type="button"
              className="route-create__submit"
              disabled={
                createBusy
                ||
                !selectedSourceId
                ||
                !selectedDeviceId
              }
              onClick={
                () => {
                  void handleCreateRoute();
                }
              }
            >
              {createBusy
                ? "CREATING..."
                : "CREATE ROUTE"}
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
                source?.type
                ===
                "broadcastify_live_audio";

              const pipelineLabel =
                isLiveAudio
                  ? getLiveAudioStateLabel(
                      liveAudio
                    )
                  : getWorkerStateLabel(
                      worker
                    );

              const pipelineClass =
                isLiveAudio
                  ? getLiveAudioStateClass(
                      liveAudio
                    )
                  : getWorkerStateClass(
                      worker
                    );


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


                    {expanded && (
                      <>
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
                                    Feed ID
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
                                    P25 Records
                                  </span>

                                  <strong>
                                    {
                                      liveAudio
                                        ?.p25
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


                              {worker?.error && (
                                <div className="route-worker__error">
                                  {worker.error}
                                </div>
                              )}
                            </div>
                          )}


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
                                ||
                                !route.enabled
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
                            ||
                            !route.enabled
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