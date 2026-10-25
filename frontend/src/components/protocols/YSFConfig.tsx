import type { YSFConfig as YSFConfigType } from "../../types/radio";
import AmbeVocoderFields from "./AmbeVocoderFields";

type YSFConfigProps = {
  value: YSFConfigType;
  onChange: (value: YSFConfigType) => void;
};

function YSFConfig({ value, onChange }: YSFConfigProps) {
  const set = <K extends keyof YSFConfigType>(key: K, next: YSFConfigType[K]) => onChange({ ...value, [key]: next });

  return (
    <div className="protocol-config">
      <h3>System Fusion (C4FM, DN / V-D mode 2)</h3>
      <div className="form-grid">
        <label>
          Frequency (MHz)
          <input value={value.frequency} inputMode="decimal" onChange={(e) => set("frequency", e.target.value)} />
        </label>
        <label>
          Source callsign
          <input
            value={value.callsign}
            maxLength={10}
            onChange={(e) => set("callsign", e.target.value.toUpperCase())}
          />
          <span className="field-hint">Shown on Fusion radios; also used as the MMDVM-Host callsign.</span>
        </label>
        <label>
          Destination
          <input
            value={value.destination}
            maxLength={10}
            onChange={(e) => set("destination", e.target.value.toUpperCase())}
          />
        </label>
        <label>
          DG-ID
          <input type="number" min="0" max="99" value={value.dgId} onChange={(e) => set("dgId", e.target.value)} />
          <span className="field-hint">0 = radios in DN/AMS mode with DG-ID 00 open their squelch.</span>
        </label>
        <label>
          Deviation
          <select value={value.lowDeviation} onChange={(e) => set("lowDeviation", e.target.value as "on" | "off")}>
            <option value="off">Normal (wide)</option>
            <option value="on">Low (narrow)</option>
          </select>
        </label>
      </div>
      <AmbeVocoderFields value={value} onChange={onChange} />
    </div>
  );
}

export default YSFConfig;
