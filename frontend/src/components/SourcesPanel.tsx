import {
  useEffect,
  useState,
} from "react";

import "./SourcesPanel.css";


type BroadcastifyProbe = {
  provider: string;
  source_type: string;

  playlist_uuid: string;
  view: string;
  canonical_url: string;

  reachable: boolean;
  http_status: number | null;

  page_name:
    string
    | null;

  final_url:
    string
    | null;

  error:
    string
    | null;

  audio_api_configured: boolean;
  playback_state: string;
  playback_model: string;

  probed_at: string;
};


type BroadcastifySource = {
  id: string;

  name: string;

  type:
    "broadcastify_calls";

  provider:
    "broadcastify";

  url: string;

  playlist_uuid: string;
  view: string;

  created_at: string;
  updated_at: string;

  probe:
    BroadcastifyProbe
    | null;
};


type SourcesResponse = {
  version: number;
  count: number;

  sources:
    BroadcastifySource[];
};


type SourcesPanelProps = {
  onCountChange?:
    (
      count: number
    ) => void;
};


const API_BASE_URL =
  `${window.location.protocol}//${window.location.hostname}:8000`;


function playbackLabel(
  value:
    string
    | null
    | undefined
): string {
  if (
    !value
  ) {
    return "--";
  }

  return value
    .replace(
      /_/g,
      " "
    )
    .toUpperCase();
}


function SourcesPanel(
  props: SourcesPanelProps
) {
  const {
    onCountChange,
  } = props;


  const [
    sources,
    setSources,
  ] =
    useState<
      BroadcastifySource[]
    >(
      []
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
    addOpen,
    setAddOpen,
  ] =
    useState(
      false
    );


  const [
    addUrl,
    setAddUrl,
  ] =
    useState(
      ""
    );


  const [
    addName,
    setAddName,
  ] =
    useState(
      ""
    );


  const [
    addProbe,
    setAddProbe,
  ] =
    useState<
      BroadcastifyProbe
      | null
    >(
      null
    );


  const [
    addError,
    setAddError,
  ] =
    useState<
      string
      | null
    >(
      null
    );


  const [
    probingNew,
    setProbingNew,
  ] =
    useState(
      false
    );


  const [
    savingNew,
    setSavingNew,
  ] =
    useState(
      false
    );


  const [
    actionSourceId,
    setActionSourceId,
  ] =
    useState<
      string
      | null
    >(
      null
    );


  const applySources =
    (
      data: SourcesResponse
    ) => {
      setSources(
        data.sources
      );

      onCountChange?.(
        data.count
      );
    };


  const loadSources =
    async () => {
      try {
        setLoading(
          true
        );

        setError(
          null
        );


        const response =
          await fetch(
            `${API_BASE_URL}/api/sources`,
            {
              cache:
                "no-store",
            }
          );


        if (
          !response.ok
        ) {
          throw new Error(
            `Unable to load sources: HTTP ${response.status}`
          );
        }


        const data =
          (
            await response.json()
          ) as SourcesResponse;


        applySources(
          data
        );

      } catch (
        loadError
      ) {
        if (
          loadError instanceof Error
        ) {
          setError(
            loadError.message
          );

        } else {
          setError(
            "Unable to load sources"
          );
        }

      } finally {
        setLoading(
          false
        );
      }
    };


  useEffect(
    () => {
      void loadSources();
    },
    []
  );


  const resetAddForm =
    () => {
      setAddUrl(
        ""
      );

      setAddName(
        ""
      );

      setAddProbe(
        null
      );

      setAddError(
        null
      );

      setProbingNew(
        false
      );

      setSavingNew(
        false
      );
    };


  const closeAdd =
    () => {
      if (
        probingNew ||
        savingNew
      ) {
        return;
      }

      setAddOpen(
        false
      );

      resetAddForm();
    };


  const probeNewSource =
    async () => {
      try {
        const url =
          addUrl.trim();


        if (
          !url
        ) {
          throw new Error(
            "Paste a Broadcastify Calls playlist URL first."
          );
        }


        setProbingNew(
          true
        );

        setAddError(
          null
        );

        setAddProbe(
          null
        );


        const response =
          await fetch(
            `${API_BASE_URL}/api/sources/broadcastify/probe`,
            {
              method:
                "POST",

              headers: {
                "Content-Type":
                  "application/json",
              },

              body:
                JSON.stringify({
                  url,
                }),
            }
          );


        const data =
          await response.json();


        if (
          !response.ok
        ) {
          throw new Error(
            typeof data.detail ===
              "string"
              ? data.detail
              : JSON.stringify(
                  data.detail
                )
          );
        }


        const probe =
          data as BroadcastifyProbe;


        setAddProbe(
          probe
        );


        if (
          probe.page_name &&
          !addName.trim()
        ) {
          setAddName(
            probe.page_name
          );
        }


        if (
          !probe.reachable
        ) {
          setAddError(
            probe.error
            ??
            "Broadcastify playlist is not reachable."
          );
        }

      } catch (
        probeError
      ) {
        if (
          probeError instanceof Error
        ) {
          setAddError(
            probeError.message
          );

        } else {
          setAddError(
            "Unable to probe Broadcastify source."
          );
        }

      } finally {
        setProbingNew(
          false
        );
      }
    };


  const createSource =
    async () => {
      try {
        if (
          !addProbe ||
          !addProbe.reachable
        ) {
          throw new Error(
            "Probe the source successfully before adding it."
          );
        }


        const name =
          addName.trim()
          ||
          addProbe.page_name
          ||
          "Broadcastify Calls";


        setSavingNew(
          true
        );

        setAddError(
          null
        );


        const response =
          await fetch(
            `${API_BASE_URL}/api/sources`,
            {
              method:
                "POST",

              headers: {
                "Content-Type":
                  "application/json",
              },

              body:
                JSON.stringify({
                  name,

                  type:
                    "broadcastify_calls",

                  url:
                    addProbe.canonical_url,
                }),
            }
          );


        const data =
          await response.json();


        if (
          !response.ok
        ) {
          throw new Error(
            typeof data.detail ===
              "string"
              ? data.detail
              : JSON.stringify(
                  data.detail
                )
          );
        }


        setAddOpen(
          false
        );

        resetAddForm();

        await loadSources();

      } catch (
        createError
      ) {
        if (
          createError instanceof Error
        ) {
          setAddError(
            createError.message
          );

        } else {
          setAddError(
            "Unable to add source."
          );
        }

      } finally {
        setSavingNew(
          false
        );
      }
    };


  const probeExistingSource =
    async (
      sourceId: string
    ) => {
      try {
        setActionSourceId(
          sourceId
        );

        setError(
          null
        );


        const response =
          await fetch(
            `${API_BASE_URL}/api/sources/${sourceId}/probe`,
            {
              method:
                "POST",
            }
          );


        const data =
          await response.json();


        if (
          !response.ok
        ) {
          throw new Error(
            typeof data.detail ===
              "string"
              ? data.detail
              : JSON.stringify(
                  data.detail
                )
          );
        }


        const updated =
          data as BroadcastifySource;


        setSources(
          (
            current
          ) =>
            current.map(
              (
                source
              ) =>
                source.id ===
                updated.id
                  ? updated
                  : source
            )
        );

      } catch (
        probeError
      ) {
        if (
          probeError instanceof Error
        ) {
          setError(
            probeError.message
          );

        } else {
          setError(
            "Unable to probe source."
          );
        }

      } finally {
        setActionSourceId(
          null
        );
      }
    };


  const deleteSource =
    async (
      source:
        BroadcastifySource
    ) => {
      const confirmed =
        window.confirm(
          `Delete source "${source.probe?.page_name ?? source.name}"?`
        );


      if (
        !confirmed
      ) {
        return;
      }


      try {
        setActionSourceId(
          source.id
        );

        setError(
          null
        );


        const response =
          await fetch(
            `${API_BASE_URL}/api/sources/${source.id}`,
            {
              method:
                "DELETE",
            }
          );


        const data =
          await response.json();


        if (
          !response.ok
        ) {
          throw new Error(
            typeof data.detail ===
              "string"
              ? data.detail
              : JSON.stringify(
                  data.detail
                )
          );
        }


        const remaining =
          sources.filter(
            (
              item
            ) =>
              item.id !==
              source.id
          );


        setSources(
          remaining
        );

        onCountChange?.(
          remaining.length
        );

      } catch (
        deleteError
      ) {
        if (
          deleteError instanceof Error
        ) {
          setError(
            deleteError.message
          );

        } else {
          setError(
            "Unable to delete source."
          );
        }

      } finally {
        setActionSourceId(
          null
        );
      }
    };


  return (
    <>
      <section className="sources-panel">

        <div className="sources-heading">

          <div>
            <h2>
              Sources
            </h2>

            <p>
              Internet audio inputs
            </p>
          </div>


          <button
            type="button"
            className="sources-add-button"
            onClick={
              () => {
                setAddOpen(
                  true
                );
              }
            }
          >
            + ADD SOURCE
          </button>

        </div>


        {error && (
          <div className="sources-error">
            {error}
          </div>
        )}


        {loading && (
          <div className="sources-empty">
            Loading sources...
          </div>
        )}


        {!loading &&
          sources.length ===
            0 && (
            <div className="sources-empty">
              No audio sources configured.
              Add a Broadcastify Calls
              playlist to get started.
            </div>
          )}


        {!loading &&
          sources.length >
            0 && (
            <div className="sources-list">

              {sources.map(
                (
                  source
                ) => {
                  const probe =
                    source.probe;

                  const busy =
                    actionSourceId ===
                    source.id;

                  const displayName =
                    probe?.page_name
                    ??
                    source.name;


                  return (
                    <article
                      className="source-card"
                      key={
                        source.id
                      }
                    >

                      <div className="source-card-header">

                        <div>
                          <h3>
                            {displayName}
                          </h3>

                          <div className="source-provider">
                            BROADCASTIFY CALLS
                          </div>
                        </div>


                        <div
                          className={
                            probe?.reachable
                              ? "source-state source-state-online"
                              : "source-state source-state-offline"
                          }
                        >
                          <span />

                          {probe?.reachable
                            ? "REACHABLE"
                            : "OFFLINE"}
                        </div>

                      </div>


                      <div className="source-details">

                        <div className="source-detail-wide">
                          <span>
                            PLAYLIST UUID
                          </span>

                          <strong>
                            {source.playlist_uuid}
                          </strong>
                        </div>


                        <div>
                          <span>
                            PLAYBACK
                          </span>

                          <strong>
                            {playbackLabel(
                              probe?.playback_model
                            )}
                          </strong>
                        </div>


                        <div>
                          <span>
                            AUDIO
                          </span>

                          <strong>
                            {probe?.audio_api_configured
                              ? "CONFIGURED"
                              : "NOT CONFIGURED"}
                          </strong>
                        </div>


                        <div>
                          <span>
                            HTTP
                          </span>

                          <strong>
                            {probe?.http_status
                              ?? "--"}
                          </strong>
                        </div>

                      </div>


                      {probe?.error && (
                        <div className="source-card-error">
                          {probe.error}
                        </div>
                      )}


                      <div className="source-card-actions">

                        <button
                          type="button"
                          disabled={
                            busy
                          }
                          onClick={
                            () => {
                              void probeExistingSource(
                                source.id
                              );
                            }
                          }
                        >
                          {busy
                            ? "WORKING..."
                            : "↻ PROBE"}
                        </button>


                        <button
                          type="button"
                          className="source-delete-button"
                          disabled={
                            busy
                          }
                          onClick={
                            () => {
                              void deleteSource(
                                source
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


      {addOpen && (
        <div
          className="source-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Add Broadcastify source"
        >

          <div className="source-modal">

            <div className="source-modal-header">

              <div>
                <h2>
                  Add Source
                </h2>

                <p>
                  Broadcastify Calls playlist
                </p>
              </div>


              <button
                type="button"
                disabled={
                  probingNew ||
                  savingNew
                }
                onClick={
                  closeAdd
                }
              >
                CLOSE
              </button>

            </div>


            <div className="source-modal-body">

              <label className="source-field">
                <span>
                  Type
                </span>

                <input
                  type="text"
                  value="Broadcastify Calls"
                  disabled
                />
              </label>


              <label className="source-field">
                <span>
                  Playlist URL
                </span>

                <input
                  type="url"
                  placeholder="https://www.broadcastify.com/calls/playlists/?uuid=..."
                  value={
                    addUrl
                  }
                  disabled={
                    probingNew ||
                    savingNew
                  }
                  onChange={
                    (
                      event
                    ) => {
                      setAddUrl(
                        event
                          .target
                          .value
                      );

                      setAddProbe(
                        null
                      );

                      setAddError(
                        null
                      );
                    }
                  }
                />
              </label>


              <button
                type="button"
                className="source-probe-button"
                disabled={
                  probingNew ||
                  savingNew ||
                  !addUrl.trim()
                }
                onClick={
                  () => {
                    void probeNewSource();
                  }
                }
              >
                {probingNew
                  ? "PROBING..."
                  : "PROBE"}
              </button>


              {addError && (
                <div className="sources-error">
                  {addError}
                </div>
              )}


              {addProbe && (
                <div className="source-detected">

                  <div className="source-detected-header">
                    <span>
                      DETECTED SOURCE
                    </span>

                    <strong
                      className={
                        addProbe.reachable
                          ? "source-detected-online"
                          : "source-detected-offline"
                      }
                    >
                      {addProbe.reachable
                        ? "REACHABLE"
                        : "OFFLINE"}
                    </strong>
                  </div>


                  <h3>
                    {addProbe.page_name
                      ?? "Broadcastify Calls"}
                  </h3>


                  <div className="source-detected-grid">

                    <div>
                      <span>
                        PLAYLIST UUID
                      </span>

                      <strong>
                        {addProbe.playlist_uuid}
                      </strong>
                    </div>


                    <div>
                      <span>
                        HTTP
                      </span>

                      <strong>
                        {addProbe.http_status
                          ?? "--"}
                      </strong>
                    </div>


                    <div>
                      <span>
                        PLAYBACK
                      </span>

                      <strong>
                        {playbackLabel(
                          addProbe.playback_model
                        )}
                      </strong>
                    </div>


                    <div>
                      <span>
                        AUDIO
                      </span>

                      <strong>
                        {addProbe.audio_api_configured
                          ? "CONFIGURED"
                          : "NOT CONFIGURED"}
                      </strong>
                    </div>

                  </div>

                </div>
              )}


              {addProbe?.reachable && (
                <label className="source-field">
                  <span>
                    Source name
                  </span>

                  <input
                    type="text"
                    maxLength={
                      120
                    }
                    value={
                      addName
                    }
                    disabled={
                      savingNew
                    }
                    onChange={
                      (
                        event
                      ) => {
                        setAddName(
                          event
                            .target
                            .value
                        );
                      }
                    }
                  />
                </label>
              )}

            </div>


            <div className="source-modal-footer">

              <button
                type="button"
                disabled={
                  probingNew ||
                  savingNew
                }
                onClick={
                  closeAdd
                }
              >
                CANCEL
              </button>


              <button
                type="button"
                className="sources-add-button"
                disabled={
                  !addProbe?.reachable ||
                  probingNew ||
                  savingNew
                }
                onClick={
                  () => {
                    void createSource();
                  }
                }
              >
                {savingNew
                  ? "ADDING..."
                  : "ADD SOURCE"}
              </button>

            </div>

          </div>

        </div>
      )}
    </>
  );
}


export default SourcesPanel;
