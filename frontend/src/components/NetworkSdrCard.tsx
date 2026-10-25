import { useEffect, useState } from "react";
import { apiFetch, errorMessage } from "../lib/api";
import Icon from "./Icon";

type SdrType = "plutosdr" | "libresdr" | "limesdr" | "limemini" | "usrp";

type TypeInfo = { label: string; rx_gain: number; tx_gain: number; uri_example: string };

type NetworkDevice = {
  id: string;
  sdr_type: SdrType;
  uri: string;
  label: string;
  rx_gain: number;
  tx_gain: number;
};

type Props = {
  onChanged: () => void;
  disabled: boolean;
};

/** Register network SDR transmitters that MMDVM-IQ can drive (PlutoSDR, LibreSDR, Lime, USRP). */
export default function NetworkSdrCard({ onChanged, disabled }: Props) {
  const [types, setTypes] = useState<Record<string, TypeInfo>>({});
  const [devices, setDevices] = useState<NetworkDevice[]>([]);
  const [reloadKey, setReloadKey] = useState(0);
  const [sdrType, setSdrType] = useState<SdrType>("plutosdr");
  const [uri, setUri] = useState("ip:192.168.2.1");
  const [label, setLabel] = useState("");
  const [rxGain, setRxGain] = useState("30");
  const [txGain, setTxGain] = useState("0");
  const [message, setMessage] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<{ types: Record<string, TypeInfo>; devices: NetworkDevice[] }>("/api/devices/network")
      .then((data) => {
        if (!cancelled) {
          setTypes(data.types);
          setDevices(data.devices);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const chooseType = (next: SdrType) => {
    setSdrType(next);
    const info = types[next];
    if (info) {
      setUri(info.uri_example);
      setRxGain(String(info.rx_gain));
    }
  };

  const add = async () => {
    setMessage(null);
    try {
      await apiFetch("/api/devices/network", {
        method: "POST",
        body: JSON.stringify({
          sdr_type: sdrType,
          uri: uri.trim(),
          label: label.trim() || null,
          rx_gain: Number(rxGain),
          tx_gain: Number(txGain),
        }),
      });
      setMessage({ tone: "ok", text: "Added. It now appears in the device list and in route setup." });
      setReloadKey((value) => value + 1);
      onChanged();
    } catch (error) {
      setMessage({ tone: "danger", text: errorMessage(error) });
    }
  };

  const remove = async (id: string) => {
    try {
      await apiFetch(`/api/devices/network/${id}`, { method: "DELETE" });
      setReloadKey((value) => value + 1);
      onChanged();
    } catch (error) {
      setMessage({ tone: "danger", text: errorMessage(error) });
    }
  };

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">Network SDR (TX)</span>
        <span className="card-sub">PlutoSDR · LibreSDR · LimeSDR · USRP via MMDVM-IQ</span>
      </div>
      <div className="card-body" style={{ display: "grid", gap: 14 }}>
        <p className="help-text">
          Use an SDR on the network (or on USB with a custom SoapySDR URI) as the transmitter. MMDVM-IQ drives it
          with the matching SoapySDR module, which must be installed on this gateway. TX gain starts at 0 — raise it
          carefully while watching the output power.
        </p>
        <div className="form-grid">
          <label className="field">
            <span className="field-label">Type</span>
            <select value={sdrType} onChange={(event) => chooseType(event.target.value as SdrType)} disabled={disabled}>
              {(Object.keys(types).length ? Object.keys(types) : ["plutosdr", "libresdr", "limesdr", "limemini", "usrp"]).map(
                (key) => (
                  <option key={key} value={key}>
                    {types[key]?.label ?? key}
                  </option>
                ),
              )}
            </select>
          </label>
          <label className="field">
            <span className="field-label">SoapySDR URI</span>
            <input value={uri} onChange={(event) => setUri(event.target.value)} disabled={disabled} />
          </label>
          <label className="field">
            <span className="field-label">Label</span>
            <input value={label} placeholder="Pluto on the mast" onChange={(event) => setLabel(event.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">RX gain</span>
            <input value={rxGain} inputMode="numeric" onChange={(event) => setRxGain(event.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">TX gain</span>
            <input value={txGain} inputMode="numeric" onChange={(event) => setTxGain(event.target.value)} />
          </label>
        </div>
        {message && <div className={`banner banner-${message.tone}`} style={{ margin: 0 }}>{message.text}</div>}
        <div className="btn-row">
          <button type="button" className="btn btn-primary" disabled={disabled} onClick={() => void add()}>
            <Icon name="plus" /> Add network SDR
          </button>
        </div>
      </div>
      {devices.length > 0 && (
        <div className="card-body flush path-list" style={{ borderTop: "1px solid var(--border)" }}>
          {devices.map((device) => (
            <div className="path-row" key={device.id}>
              <span className="path-name" style={{ width: "auto" }}>
                {types[device.sdr_type]?.label ?? device.sdr_type}
              </span>
              <div className="path-desc">
                {device.label}
                <small>
                  {device.uri || "(default URI)"} · RX {device.rx_gain} · TX {device.tx_gain} · {device.id}
                </small>
              </div>
              <button type="button" className="btn btn-sm btn-danger" disabled={disabled} onClick={() => void remove(device.id)}>
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
