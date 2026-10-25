import type { NXDNConfig as NXDNConfigType } from "../../types/radio";
import AmbeVocoderFields from "./AmbeVocoderFields";

type NXDNConfigProps = {
  value: NXDNConfigType;
  onChange: (value: NXDNConfigType) => void;
};

function NXDNConfig({ value, onChange }: NXDNConfigProps) {
  const set = <K extends keyof NXDNConfigType>(key: K, next: NXDNConfigType[K]) => onChange({ ...value, [key]: next });

  return (
    <div className="protocol-config">
      <h3>NXDN (4800 bps EHR)</h3>
      <div className="form-grid">
        <label>
          Frequency (MHz)
          <input value={value.frequency} inputMode="decimal" onChange={(e) => set("frequency", e.target.value)} />
        </label>
        <label>
          RAN
          <input type="number" min="0" max="63" value={value.ran} onChange={(e) => set("ran", e.target.value)} />
        </label>
        <label>
          Call type
          <select value={value.callType} onChange={(e) => set("callType", e.target.value as "group" | "private")}>
            <option value="group">Group call</option>
            <option value="private">Private call</option>
          </select>
        </label>
        <label>
          {value.callType === "group" ? "Talkgroup" : "Destination unit ID"}
          <input value={value.talkgroup} inputMode="numeric" onChange={(e) => set("talkgroup", e.target.value)} />
        </label>
        <label>
          Source unit ID
          <input value={value.radioId} inputMode="numeric" onChange={(e) => set("radioId", e.target.value)} />
          <span className="field-hint">NXDN IDs are 16-bit (1–65519).</span>
        </label>
      </div>
      <AmbeVocoderFields value={value} onChange={onChange} />
    </div>
  );
}

export default NXDNConfig;
