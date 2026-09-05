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
  RoutePreflightResponse,
  RouteRuntimeStatus,
  RouteWorkerResponse,
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

  if (
    source.name
      .trim()
      .length > 0
  ) {
    return source.name;
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
      .toLowerCase() ===
    "sx"
  ) {
    return "SXceiver";
  }

  if (
    device.label
      .trim()
      .length > 0
  ) {
    return device.label;
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
      return "WAITING FOR API";

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
    worker.state ===
    "error"
  ) {
    return "error";
  }

  if (
    worker.state ===
    "waiting_for_api_configuration"
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
    runtime.blocked_reason ===
    "route_disabled"
  ) {
    return "--";
  }

  switch (
    check
  ) {
    case "source":
      if (
        runtime.source_ready
      ) {
        return "READY";
      }

      if (
        runtime.state ===
        "stopped"
      ) {
        return "--";
      }

      return "NOT READY";


    case "rf":
      if (
        runtime.rf_ready
      ) {
        return "READY";
      }

      if (
        !runtime.source_ready
      ) {
        return "--";
      }

      return "NOT READY";


    case "config":
      if (
        runtime.config_ready
      ) {
        return "READY";
      }

      if (
        !runtime.rf_ready
      ) {
        return "--";
      }

      return "NOT READY";


    case "audio_bridge":
      if (
        runtime.audio_bridge_ready
      ) {
        return "READY";
      }

      if (
        !runtime.config_ready
      ) {
        return "--";
      }

      if (
        runtime.audio_bridge
      ) {
        return "BLOCKED";
      }

      return "NOT READY";


    default:
      return "--";
  }
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
    workers,
    setWorkers,
  ] =
    useState<
      Record<
        string,
        RouteWorkerResponse
      >
    >(
      {}
    );


  const [
    preflights,
    setPreflights,
  ] =
    useState<
      Record<
        string,
        RoutePreflightResponse
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
            await response
              .json()
          ) as SourcesResponse;


        setSources(
          data.sources
        );


        setSelectedSourceId(
          (
            current
          ) => {
            if (
              current &&
              data.sources.some(
                (
                  source
                ) =>
                  source.id ===
                  current
              )
            ) {
              return current;
            }


            return (
              data.sources[
                0
              ]?.id ??
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
            await response
              .json()
          ) as RFDevicesResponse;


        const usable =
          data.devices.filter(
            (
              device
            ) =>
              device.available &&
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
              current &&
              usable.some(
                (
                  device
                ) =>
                  device.id ===
                  current
              )
            ) {
              return current;
            }


            return (
              usable[
                0
              ]?.id ??
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
            await response
              .json()
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


  const loadWorker =
    useCallback(
      async (
        routeId: string
      ) => {
        try {
          const response =
            await fetch(
              (
                `${apiBaseUrl}` +
                `/api/routes/${routeId}/worker`
              ),
              {
                cache:
                  "no-store",
              }
            );


          if (
            !response.ok
          ) {
            return;
          }


          const data =
            (
              await response
                .json()
            ) as RouteWorkerResponse;


          setWorkers(
            (
              current
            ) => ({
              ...current,

              [
                routeId
              ]:
                data,
            })
          );

        } catch {
          // Main dashboard handles backend connectivity.
        }
      },
      [
        apiBaseUrl,
      ]
    );


  const loadPreflight =
    useCallback(
      async (
        routeId: string
      ) => {
        try {
          const response =
            await fetch(
              (
                `${apiBaseUrl}` +
                `/api/routes/${routeId}/preflight`
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
            return;
          }


          const data =
            (
              await response
                .json()
            ) as RoutePreflightResponse;


          setPreflights(
            (
              current
            ) => ({
              ...current,

              [
                routeId
              ]:
                data,
            })
          );

        } catch {
          // Main dashboard handles backend connectivity.
        }
      },
      [
        apiBaseUrl,
      ]
    );


  const loadWorkers =
    useCallback(
      async (
        routeList:
          Route[]
      ) => {
        await Promise.all(
          routeList.map(
            (
              route
            ) =>
              loadWorker(
                route.id
              )
          )
        );
      },
      [
        loadWorker,
      ]
    );


  const loadPreflights =
    useCallback(
      async (
        routeList:
          Route[]
      ) => {
        await Promise.all(
          routeList.map(
            (
              route
            ) =>
              loadPreflight(
                route.id
              )
          )
        );
      },
      [
        loadPreflight,
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


          await Promise.all([
            loadWorkers(
              routeList
            ),

            loadPreflights(
              routeList
            ),
          ]);

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
        loadWorkers,
        loadPreflights,
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
              void loadWorker(
                route.id
              );

              void loadPreflight(
                route.id
              );
            }
          },
          2000
        );


      return () => {
        window.clearInterval(
          timer
        );
      };
    },
    [
      routes,
      loadWorker,
      loadPreflight,
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
            item.id ===
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
            await response
              .json()
              .catch(
                () => null
              );


          throw new Error(
            (
              data &&
              typeof data.detail ===
                "string"
            )
              ? data.detail
              : (
                  `Create route HTTP ` +
                  `${response.status}`
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
          throw new Error(
            (
              `Update route HTTP ` +
              `${response.status}`
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


        setWorkers(
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


        setPreflights(
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


  const handleWorkerStart =
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
              `/api/routes/${route.id}` +
              `/worker/start`
            ),
            {
              method:
                "POST",
            }
          );


        if (
          !response.ok
        ) {
          const data =
            await response
              .json()
              .catch(
                () => null
              );


          throw new Error(
            (
              data &&
              typeof data.detail ===
                "string"
            )
              ? data.detail
              : (
                  `Worker start HTTP ` +
                  `${response.status}`
                )
          );
        }


        await Promise.all([
          loadWorker(
            route.id
          ),

          loadPreflight(
            route.id
          ),
        ]);

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


  const handleWorkerStop =
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
              `/api/routes/${route.id}` +
              `/worker/stop`
            ),
            {
              method:
                "POST",
            }
          );


        if (
          !response.ok
        ) {
          throw new Error(
            (
              `Worker stop HTTP ` +
              `${response.status}`
            )
          );
        }


        await Promise.all([
          loadWorker(
            route.id
          ),

          loadPreflight(
            route.id
          ),
        ]);

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
                createBusy ||
                !selectedSourceId ||
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
                    item.id ===
                    route.source_id
                );


              const device =
                devices.find(
                  (
                    item
                  ) =>
                    item.id ===
                    route.device_id
                );


              const workerResponse =
                workers[
                  route.id
                ];


              const worker =
                workerResponse
                  ?.worker ??
                null;


              const queue =
                workerResponse
                  ?.queue;


              const preflightResponse =
                preflights[
                  route.id
                ];


              const runtime =
                preflightResponse
                  ?.runtime ??
                null;


              const busy =
                actionRouteId ===
                route.id;


              const workerRunning =
                Boolean(
                  worker
                    ?.running
                );


              return (
                <article
                  className="route-card"
                  key={
                    route.id
                  }
                >
                  <div className="route-card__main">
                    <div className="route-card__title-row">
                      <div>
                        <h3>
                          {route.name}
                        </h3>

                        <div className="route-card__meta">
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


                      <div className="route-card__badges">
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
                      </div>
                    </div>


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
                                ?.queue_size ??
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
                                ?.calls_received ??
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
                                ?.calls_enqueued ??
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
                                ?.calls_duplicates ??
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


                  <div className="route-card__actions">
                    <button
                      type="button"
                      className="route-card__worker-start"
                      disabled={
                        busy ||
                        !route.enabled ||
                        workerRunning
                      }
                      onClick={
                        () => {
                          void handleWorkerStart(
                            route
                          );
                        }
                      }
                    >
                      START SOURCE
                    </button>


                    <button
                      type="button"
                      className="route-card__worker-stop"
                      disabled={
                        busy ||
                        !workerRunning
                      }
                      onClick={
                        () => {
                          void handleWorkerStop(
                            route
                          );
                        }
                      }
                    >
                      STOP SOURCE
                    </button>


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
                        busy ||
                        workerRunning
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