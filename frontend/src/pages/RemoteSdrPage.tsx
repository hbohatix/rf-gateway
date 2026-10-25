import { useEffect, useMemo, useState } from "react";
import Icon from "../components/Icon";
import { useI18n } from "../i18n";
import { apiFetch, errorMessage } from "../lib/api";

type Kind = "rtl_tcp" | "kiwisdr" | "audio_stream";
type StreamPreset = "gqrx" | "sdrpp" | "http" | "rtsp" | "custom";

type ProbeResult = {
  canonical_url: string;
  reachable: boolean;
  error: string | null;
  page_name?: string | null;
  receiver_info?: Record<string, unknown>;
  playback_state?: string;
  listening?: boolean;
};

type SourceItem = {
  id: string;
  name: string;
  type: string;
  url: string;
  probe?: ProbeResult;
};

type Props = {
  onSourcesChanged: () => void;
  onOpenRoutes: () => void;
};

const KINDS: { id: Kind; title: string; hint: string }[] = [
  { id: "rtl_tcp", title: "rtl_tcp", hint: "RTL-SDR shared with rtl_tcp — raw IQ, demodulated here (NFM/AM + squelch)" },
  { id: "kiwisdr", title: "KiwiSDR", hint: "Public or private KiwiSDR (0–30 MHz) over WebSocket" },
  { id: "audio_stream", title: "Audio stream", hint: "GQRX / SDR++ / SDRangel / OpenWebRX audio (UDP, TCP, HTTP, RTSP)" },
];

const PRESETS: Record<StreamPreset, { label: string; scheme: string; port: string; format: string; rate: string }> = {
  gqrx: { label: "GQRX UDP audio (48 kHz s16le)", scheme: "udp", port: "7355", format: "s16le", rate: "48000" },
  sdrpp: { label: "SDR++ network sink (TCP, 48 kHz s16le)", scheme: "tcp", port: "7355", format: "s16le", rate: "48000" },
  http: { label: "HTTP / Icecast stream", scheme: "http", port: "8000", format: "", rate: "" },
  rtsp: { label: "RTSP stream", scheme: "rtsp", port: "8554", format: "", rate: "" },
  custom: { label: "Custom URL", scheme: "", port: "", format: "", rate: "" },
};

function mhzToHz(value: string): number | null {
  const mhz = Number(value.replace(",", "."));
  return Number.isFinite(mhz) && mhz > 0 ? Math.round(mhz * 1_000_000) : null;
}

export default function RemoteSdrPage({ onSourcesChanged, onOpenRoutes }: Props) {
  const { t } = useI18n();
  const [kind, setKind] = useState<Kind>("rtl_tcp");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("1234");
  const [frequency, setFrequency] = useState("145.500");
  const [modulation, setModulation] = useState("nfm");
  const [gain, setGain] = useState("auto");
  const [squelch, setSquelch] = useState("auto");
  const [audioGain, setAudioGain] = useState("1.0");
  const [preset, setPreset] = useState<StreamPreset>("gqrx");
  const [path, setPath] = useState("");
  const [customUrl, setCustomUrl] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [probe, setProbe] = useState<ProbeResult | null>(null);
  const [message, setMessage] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const [sources, setSources] = useState<SourceItem[]>([]);

  const [sourcesKey, setSourcesKey] = useState(0);
  const loadSources = () => setSourcesKey((value) => value + 1);

  useEffect(() => {
    let cancelled = false;
    apiFetch<{ sources: SourceItem[] }>("/api/sources")
      .then((data) => {
        if (!cancelled) {
          setSources(data.sources.filter((source) => source.type === "remote_sdr"));
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [sourcesKey]);

  const selectKind = (next: Kind) => {
    setKind(next);
    setProbe(null);
    setMessage(null);
    if (next === "rtl_tcp") {
      setPort("1234");
      setModulation("nfm");
    } else if (next === "kiwisdr") {
      setPort("8073");
      setModulation("am");
      setFrequency("7.100");
    }
  };

  const url = useMemo(() => {
    const params = new URLSearchParams();
    const audio = Number(audioGain);
    if (kind === "rtl_tcp" || kind === "kiwisdr") {
      if (!host.trim()) {
        return "";
      }
      const hz = mhzToHz(frequency);
      if (hz === null) {
        return "";
      }
      params.set("freq", String(hz));
      params.set("mod", modulation);
      if (kind === "rtl_tcp") {
        params.set("gain", gain.trim() || "auto");
      }
      if (squelch.trim() && squelch.trim() !== "auto") {
        params.set("squelch", squelch.trim());
      }
      if (Number.isFinite(audio) && audio !== 1) {
        params.set("audio_gain", String(audio));
      }
      const scheme = kind === "rtl_tcp" ? "rtl_tcp" : "kiwisdr";
      return `${scheme}://${host.trim()}:${port.trim() || (kind === "rtl_tcp" ? "1234" : "8073")}?${params.toString()}`;
    }
    if (preset === "custom") {
      return customUrl.trim();
    }
    const p = PRESETS[preset];
    if (p.format) {
      params.set("format", p.format);
      params.set("rate", p.rate);
    }
    if (Number.isFinite(audio) && audio !== 1) {
      params.set("audio_gain", String(audio));
    }
    const target = p.scheme === "udp" ? host.trim() || "0.0.0.0" : host.trim();
    if (!target) {
      return "";
    }
    const query = params.toString();
    const suffix = p.scheme === "http" || p.scheme === "rtsp" ? `/${path.replace(/^\//, "")}` : "";
    return `${p.scheme}://${target}:${port.trim() || p.port}${suffix}${query ? `?${query}` : ""}`;
  }, [kind, host, port, frequency, modulation, gain, squelch, audioGain, preset, path, customUrl]);

  const runProbe = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await apiFetch<ProbeResult>("/api/sources/remote-sdr/probe", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      setProbe(result);
      if (!name && result.page_name) {
        setName(result.page_name);
      }
    } catch (error) {
      setProbe(null);
      setMessage({ tone: "danger", text: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await apiFetch("/api/sources", {
        method: "POST",
        body: JSON.stringify({ name: name.trim() || probe?.page_name || url, type: "remote_sdr", url }),
      });
      setMessage({ tone: "ok", text: t("sdr.saved") });
      onSourcesChanged();
      loadSources();
    } catch (error) {
      setMessage({ tone: "danger", text: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await apiFetch(`/api/sources/${id}`, { method: "DELETE" });
      onSourcesChanged();
      loadSources();
    } catch (error) {
      setMessage({ tone: "danger", text: errorMessage(error) });
    }
  };

  const showRf = kind === "rtl_tcp" || kind === "kiwisdr";

  return (
    <div className="page-grid two">
      <div className="card">
        <div className="card-head">
          <span className="card-title">{t("page.remote_sdr")}</span>
          <div className="seg" style={{ marginLeft: "auto" }}>
            {KINDS.map((item) => (
              <button key={item.id} type="button" className={kind === item.id ? "active" : ""} onClick={() => selectKind(item.id)}>
                {item.title}
              </button>
            ))}
          </div>
        </div>
        <div className="card-body" style={{ display: "grid", gap: 14 }}>
          <p className="help-text">{KINDS.find((item) => item.id === kind)?.hint}</p>

          {kind === "audio_stream" && (
            <label className="field">
              <span className="field-label">Preset</span>
              <select
                value={preset}
                onChange={(event) => {
                  const next = event.target.value as StreamPreset;
                  setPreset(next);
                  setPort(PRESETS[next].port);
                }}
              >
                {(Object.keys(PRESETS) as StreamPreset[]).map((key) => (
                  <option key={key} value={key}>
                    {PRESETS[key].label}
                  </option>
                ))}
              </select>
              {preset === "gqrx" && (
                <span className="field-hint">
                  GQRX: enable “UDP” in the audio panel and send to this gateway's IP, port 7355. The gateway listens.
                </span>
              )}
            </label>
          )}

          <div className="form-grid">
            {(kind !== "audio_stream" || preset !== "custom") && (
              <>
                <label className="field">
                  <span className="field-label">
                    {kind === "audio_stream" && preset === "gqrx" ? "Listen address" : t("sdr.host")}
                  </span>
                  <input
                    value={host}
                    placeholder={kind === "audio_stream" && preset === "gqrx" ? "0.0.0.0" : "192.168.1.50"}
                    onChange={(event) => setHost(event.target.value)}
                  />
                </label>
                <label className="field">
                  <span className="field-label">{t("sdr.port")}</span>
                  <input value={port} inputMode="numeric" onChange={(event) => setPort(event.target.value)} />
                </label>
              </>
            )}
            {kind === "audio_stream" && (preset === "http" || preset === "rtsp") && (
              <label className="field wide">
                <span className="field-label">Path</span>
                <input value={path} placeholder="stream.mp3" onChange={(event) => setPath(event.target.value)} />
              </label>
            )}
            {kind === "audio_stream" && preset === "custom" && (
              <label className="field wide">
                <span className="field-label">{t("sdr.url")}</span>
                <input
                  value={customUrl}
                  placeholder="udp://0.0.0.0:7355?format=s16le&rate=48000"
                  onChange={(event) => setCustomUrl(event.target.value)}
                />
              </label>
            )}
            {showRf && (
              <>
                <label className="field">
                  <span className="field-label">{t("sdr.frequency")}</span>
                  <input value={frequency} inputMode="decimal" onChange={(event) => setFrequency(event.target.value)} />
                </label>
                <label className="field">
                  <span className="field-label">{t("sdr.modulation")}</span>
                  <select value={modulation} onChange={(event) => setModulation(event.target.value)}>
                    {(kind === "rtl_tcp" ? ["nfm", "am"] : ["am", "amn", "nbfm", "usb", "lsb", "cw"]).map((mod) => (
                      <option key={mod} value={mod}>
                        {mod.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </label>
                {kind === "rtl_tcp" && (
                  <label className="field">
                    <span className="field-label">{t("sdr.gain")}</span>
                    <input value={gain} placeholder="auto or dB" onChange={(event) => setGain(event.target.value)} />
                  </label>
                )}
                <label className="field">
                  <span className="field-label">{t("sdr.squelch")}</span>
                  <input value={squelch} placeholder="auto / off / -45" onChange={(event) => setSquelch(event.target.value)} />
                  <span className="field-hint">
                    {kind === "rtl_tcp" ? "auto = noise floor + 10 dB; or a level in dBFS" : "auto, off, or an S-meter level in dBm"}
                  </span>
                </label>
              </>
            )}
            <label className="field">
              <span className="field-label">{t("sdr.audio_gain")}</span>
              <input value={audioGain} inputMode="decimal" onChange={(event) => setAudioGain(event.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">{t("sdr.name")}</span>
              <input value={name} placeholder="SR5 repeater via rtl_tcp" onChange={(event) => setName(event.target.value)} />
            </label>
          </div>

          <div className="field">
            <span className="field-label">{t("sdr.preview")}</span>
            <div className="code-preview">{url || "—"}</div>
          </div>

          {message && <div className={`banner banner-${message.tone}`} style={{ margin: 0 }}>{message.text}</div>}
          {probe && (
            <div className={`banner ${probe.reachable ? "banner-ok" : "banner-warn"}`} style={{ margin: 0 }}>
              <div>
                <strong>{probe.reachable ? "Reachable" : "Not reachable"}</strong>
                {probe.listening ? " · gateway will listen for pushed audio" : ""}
                {probe.error ? ` · ${probe.error}` : ""}
                {probe.receiver_info && (
                  <div style={{ fontFamily: "var(--mono)", fontSize: 11, marginTop: 4, color: "var(--text2)" }}>
                    {Object.entries(probe.receiver_info)
                      .filter(([, value]) => value !== null && value !== undefined && value !== "")
                      .map(([key, value]) => `${key}: ${String(value)}`)
                      .join(" · ")}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="btn-row">
            <button type="button" className="btn" disabled={!url || busy} onClick={() => void runProbe()}>
              <Icon name="search" /> {t("sdr.probe")}
            </button>
            <button type="button" className="btn btn-primary" disabled={!url || busy} onClick={() => void save()}>
              <Icon name="plus" /> {t("sdr.save")}
            </button>
            <button type="button" className="btn" onClick={onOpenRoutes} style={{ marginLeft: "auto" }}>
              <Icon name="routes" /> {t("page.routes")}
            </button>
          </div>
          <p className="help-text" style={{ fontSize: 11.5, color: "var(--text3)" }}>
            {t("sdr.legal")}
          </p>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <span className="card-title">{t("page.remote_sdr")}</span>
          <span className="card-sub">{sources.length}</span>
        </div>
        <div className="card-body flush path-list">
          {sources.length === 0 && <div className="empty-state">—</div>}
          {sources.map((source) => (
            <div className="path-row" key={source.id}>
              <div className="path-desc" style={{ color: "var(--text)" }}>
                {source.name}
                <small>{source.url}</small>
              </div>
              <span className={`pill ${source.probe?.reachable ? "pill-ok" : "pill-warn"}`}>
                {source.probe?.reachable ? "OK" : "?"}
              </span>
              <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove(source.id)}>
                ✕
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
