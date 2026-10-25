import type { DMRConfig as DMRConfigType } from "../../types/radio";
import AmbeVocoderFields from "./AmbeVocoderFields";

type DMRConfigProps = {
  value: DMRConfigType;
  onChange: (value: DMRConfigType) => void;
};

function DMRConfig({ value, onChange }: DMRConfigProps) {
  const set = <K extends keyof DMRConfigType>(key: K, next: DMRConfigType[K]) => onChange({ ...value, [key]: next });

  return (
    <div className="protocol-config">
      <h3>DMR (Tier II, simplex hotspot)</h3>
      <div className="form-grid">
        <label>
          Frequency (MHz)
          <input value={value.frequency} inputMode="decimal" onChange={(e) => set("frequency", e.target.value)} />
        </label>
        <label>
          Color code
          <input type="number" min="0" max="15" value={value.colorCode} onChange={(e) => set("colorCode", e.target.value)} />
        </label>
        <label>
          Timeslot
          <select value={value.timeslot} onChange={(e) => set("timeslot", e.target.value as "1" | "2")}>
            <option value="2">TS2</option>
            <option value="1">TS1 (duplex only)</option>
          </select>
          {value.timeslot === "1" && (
            <span className="field-hint" style={{ color: "var(--warn)" }}>
              A simplex hotspot transmits on TS2 only.
            </span>
          )}
        </label>
        <label>
          Call type
          <select value={value.callType} onChange={(e) => set("callType", e.target.value as "group" | "private")}>
            <option value="group">Group call (talkgroup)</option>
            <option value="private">Private call (radio ID)</option>
          </select>
        </label>
        <label>
          {value.callType === "group" ? "Talkgroup" : "Destination ID"}
          <input value={value.talkgroup} inputMode="numeric" onChange={(e) => set("talkgroup", e.target.value)} />
        </label>
        <label>
          Source radio ID
          <input value={value.radioId} inputMode="numeric" onChange={(e) => set("radioId", e.target.value)} />
        </label>
      </div>

      <AmbeVocoderFields value={value} onChange={onChange} />
    </div>
  );
}

export default DMRConfig;
