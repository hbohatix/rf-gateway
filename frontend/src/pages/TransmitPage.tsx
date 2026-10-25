import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import Icon from "../components/Icon";
import ProtocolSelector from "../components/ProtocolSelector";
import TelemetryTiles from "../components/TelemetryTiles";
import { useI18n } from "../i18n";
import { apiFetch, errorMessage } from "../lib/api";
import { getDeviceDisplayName } from "../lib/format";
import { STREAMING_PROTOCOLS } from "../lib/modes";
import type { Protocol, VoiceCapabilities } from "../types/radio";
import type { RFDevice } from "../types/rfDevice";
import type { OnAir, Source, TransmitState } from "../types/transmit";

type Props = {
  transmit: TransmitState | null;
  onRefresh: () => void;
  capabilities: VoiceCapabilities | null;
  onSelectProtocol: (protocol: Protocol) => void;
  modeForm: ReactNode;
  devices: RFDevice[];
  onSelectDevice: (deviceId: string) => void;
  onCalibrate: () => void;
  onSourcesChanged: (count: number) => void;
};

const SOURCE_TYPES: Record<string, string> = {
  broadcastify_calls: "Broadcastify Calls",
  broadcastify_live_audio: "Broadcastify Live",
  direct_audio: "Audio stream",
  remote_sdr: "Remote SDR",
};

function shortUrl(url: string): string {
  return url.replace(/^[a-z]+:\/\//i, "").replace(/\/$/, "");
}

function liveLine(onAir: OnAir): string {
  const parts: string[] = [];
  const live = onAir.live_audio;
  if (live) {
    if (live.state) parts.push(live.state);
    if (typeof live.last_activity_level_dbfs === "number") parts.push(`${live.last_activity_level_dbfs.toFixed(0)} dBFS`);
    if (live.tx_start_count) parts.push(`TX ×${live.tx_start_count}`);
    if (live.pcm_bytes_received) parts.push(`${(live.pcm_bytes_received / 1e6).toFixed(1)} MB`);
    if (live.error) parts.push(live.error);
  }
  const calls = onAir.calls;
  if (calls) {
    parts.push(`calls ${calls.calls_observed ?? 0}`);
    parts.push(`sent ${calls.calls_sent ?? 0}`);
    if (calls.current_call) parts.push("sending…");
  }
  return parts.join(" · ");
}

export default function TransmitPage(props: Props) {
  const { t } = useI18n();
  const { transmit, onRefresh, onSourcesChanged } = props;
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);

  const loadSources = useCallback(async () => {
    try {
      const data = await apiFetch<{ sources: Source[] }>("/api/transmit/sources");
      setSources(data.sources);
      onSourcesChanged(data.sources.length);
    } catch (error) {
      setNotice({ tone: "danger", text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }, [onSourcesChanged]);

  useEffect(() => {
    let cancelled = false;
    apiFetch<{ sources: Source[] }>("/api/transmit/sources")
      .then((data) => {
        if (!cancelled) {
          setSources(data.sources);
          onSourcesChanged(data.sources.length);
        }
      })
      .catch((error) => !cancelled && setNotice({ tone: "danger", text: errorMessage(error) }))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [onSourcesChanged]);

  const onAir = transmit?.on_air ?? null;
  const rf = transmit?.rf;
  const mode = transmit?.mode;
  const errors = transmit?.errors ?? {};

  const run = async (id: string, action: () => Promise<void>) => {
    setBusyId(id);
    setNotice(null);
    try {
      await action();
    } catch (error) {
      setNotice({ tone: "danger", text: errorMessage(error) });
    } finally {
      setBusyId(null);
      onRefresh();
    }
  };

  const start = (source: Source) =>
    run(source.id, async () => {
      const result = await apiFetch<{ started: boolean; message?: string }>("/api/transmit/start", {
        method: "POST",
        body: JSON.stringify({ source_id: source.id }),
      });
      if (!result.started) {
        throw new Error(result.message || "Start failed");
      }
    });

  const stopAll = () =>
    run("stop", async () => {
      await apiFetch("/api/transmit/stop", { method: "POST" });
    });

  const remove = (source: Source) => {
    if (!window.confirm(`${t("tx.delete_confirm")} "${source.name}"?`)) {
      return;
    }
    void run(source.id, async () => {
      await apiFetch(`/api/transmit/sources/${source.id}`, { method: "DELETE" });
      await loadSources();
    });
  };

  const add = async (event: FormEvent) => {
    event.preventDefault();
    if (!url.trim()) {
      return;
    }
    setAdding(true);
    setNotice(null);
    try {
      const source = await apiFetch<Source>("/api/transmit/sources", {
        method: "POST",
        body: JSON.stringify({ url: url.trim(), name: name.trim() || null }),
      });
      setUrl("");
      setName("");
      setNotice({ tone: "ok", text: `${t("tx.added")}: ${source.name}` });
      await loadSources();
    } catch (error) {
      setNotice({ tone: "danger", text: errorMessage(error) });
    } finally {
      setAdding(false);
    }
  };

  const onAirSource = onAir ? sources.find((source) => source.id === onAir.source_id) : undefined;
  const txOn = Boolean(rf?.rf_tx_active);
  const usableDevices = props.devices.filter((device) => device.available && device.probe_ok);

  return (
    <div className="page-grid two">
      {/* ------------------------------------------------------------ sources */}
      <div className="card">
        <div className="card-head">
          <span className="card-title">{t("tx.sources")}</span>
          <span className="card-sub">{t("tx.sources.sub")}</span>
        </div>
        <div className="card-body">
          <form className="tx-add" onSubmit={(event) => void add(event)}>
            <input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://www.broadcastify.com/listen/feed/… · /calls/playlists/… · http://stream… · kiwi://… · rtl_tcp://…"
              aria-label={t("tx.url")}
            />
            <input
              className="tx-add-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t("tx.name_optional")}
              aria-label={t("tx.name_optional")}
            />
            <button type="submit" className="btn btn-primary" disabled={adding || !url.trim()}>
              <Icon name="plus" /> {adding ? t("tx.adding") : t("tx.add")}
            </button>
          </form>

          {notice && <div className={`banner banner-${notice.tone}`}>{notice.text}</div>}
          {!mode?.protocol && <div className="banner banner-warn">{t("tx.choose_mode")}</div>}

          {loading && <div className="empty-state">…</div>}
          {!loading && sources.length === 0 && <div className="empty-state">{t("tx.no_sources")}</div>}

          <div className="tx-list">
            {sources.map((source) => {
              const live = onAir?.source_id === source.id;
              const probe = source.probe ?? {};
              const reachable = probe.reachable !== false && probe.audio_api_configured !== false;
              const error = errors[source.id] ?? (live ? onAir?.error : null);
              return (
                <div key={source.id} className={`tx-row${live ? " live" : ""}`}>
                  <span className={`tx-dot${live ? (txOn ? " tx" : " on") : reachable ? "" : " bad"}`} />
                  <div className="tx-row-main">
                    <div className="tx-row-name">{source.name}</div>
                    <div className="tx-row-sub">
                      {SOURCE_TYPES[source.type] ?? source.type} · {shortUrl(source.url)}
                    </div>
                    {live && onAir && <div className="tx-row-live">{liveLine(onAir) || onAir.state}</div>}
                    {error && <div className="tx-row-error">{error}</div>}
                  </div>
                  <div className="tx-row-actions">
                    {live ? (
                      <button type="button" className="btn btn-danger" disabled={busyId !== null} onClick={() => void stopAll()}>
                        <Icon name="stop" /> {t("rf.stop")}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={busyId !== null || !mode?.protocol}
                        onClick={() => void start(source)}
                      >
                        <Icon name="play" /> {busyId === source.id ? t("tx.starting") : t("tx.transmit")}
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-icon"
                      title={t("tx.delete")}
                      disabled={busyId !== null}
                      onClick={() => remove(source)}
                    >
                      ✕
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------- transmitter */}
      <div>
        <div className={`card tx-status${txOn ? " tx" : onAir ? " live" : ""}`}>
          <div className="card-body">
            <div className="tx-status-head">
              <span className={`pill ${txOn ? "pill-tx" : onAir ? "pill-ok" : rf?.runtime_active ? "pill-info" : "pill-idle"}`}>
                {txOn ? "TX" : onAir ? t("tx.on_air") : rf?.runtime_active ? t("status.ready") : t("tx.off")}
              </span>
              <span className="tx-status-mode">{mode?.summary ?? t("tx.no_mode")}</span>
            </div>
            <div className="tx-status-source">
              {onAir ? onAirSource?.name ?? onAir.source_id : t("tx.nothing")}
            </div>
            {rf?.runtime_active && (
              <TelemetryTiles status={rf.mmdvm ?? null} runtimeActive={Boolean(rf.runtime_active)} rfTxActive={txOn} compact />
            )}
            {rf?.mmdvm?.last_error && <div className="banner banner-danger">{rf.mmdvm.last_error}</div>}
            <div className="btn-row">
              <button
                type="button"
                className="btn btn-danger"
                disabled={busyId !== null || !(onAir || rf?.runtime_active)}
                onClick={() => void stopAll()}
              >
                <Icon name="stop" /> {t("tx.stop_all")}
              </button>
              <button type="button" className="btn" disabled={!mode?.protocol || txOn} onClick={props.onCalibrate}>
                <Icon name="calibrate" /> {t("rf.calibrate")}
              </button>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <span className="card-title">{t("tx.mode")}</span>
            <span className="card-sub">{t("tx.mode.sub")}</span>
          </div>
          <div className="card-body">
            <ProtocolSelector
              protocols={STREAMING_PROTOCOLS}
              activeProtocol={mode?.protocol ?? null}
              disabled={false}
              onToggle={props.onSelectProtocol}
              capabilities={props.capabilities}
            />
            {props.modeForm}
            <label className="field tx-device">
              <span className="field-label">{t("rf.device")}</span>
              <select value={transmit?.device_id ?? ""} onChange={(event) => props.onSelectDevice(event.target.value)}>
                <option value="">{usableDevices.length ? t("tx.device_auto") : t("rf.no_devices")}</option>
                {props.devices.map((device) => (
                  <option key={device.id} value={device.id} disabled={!device.available || !device.probe_ok}>
                    {getDeviceDisplayName(device)} · {device.driver}
                  </option>
                ))}
              </select>
            </label>
            <p className="help-text">{t("tx.legal")}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
