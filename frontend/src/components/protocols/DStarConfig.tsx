import type { DStarConfig as DStarConfigType } from "../../types/radio";

type DStarConfigProps = {
  value: DStarConfigType;
  onChange: (value: DStarConfigType) => void;
};

function DStarConfig({ value, onChange }: DStarConfigProps) {
  const set = <K extends keyof DStarConfigType>(key: K, next: DStarConfigType[K]) => onChange({ ...value, [key]: next });

  return (
    <div className="protocol-config">
      <h3>D-Star DV (simplex)</h3>
      <div className="form-grid">
        <label>
          Frequency (MHz)
          <input value={value.frequency} inputMode="decimal" onChange={(e) => set("frequency", e.target.value)} />
        </label>
        <label>
          Callsign (MY)
          <input value={value.callsign} maxLength={8} onChange={(e) => set("callsign", e.target.value.toUpperCase())} />
          <span className="field-hint">Also used as the MMDVM-Host callsign.</span>
        </label>
        <label>
          Suffix
          <input value={value.suffix} maxLength={4} onChange={(e) => set("suffix", e.target.value.toUpperCase())} />
        </label>
        <label>
          YOUR call
          <input value={value.yourCall} maxLength={8} onChange={(e) => set("yourCall", e.target.value.toUpperCase())} />
        </label>
        <label>
          Module
          <select value={value.module} onChange={(e) => set("module", e.target.value)}>
            {["A", "B", "C", "D"].map((module) => (
              <option key={module} value={module}>
                {module}
              </option>
            ))}
          </select>
        </label>
        <label>
          Slow-data message
          <input value={value.message} maxLength={20} onChange={(e) => set("message", e.target.value)} />
          <span className="field-hint">Up to 20 characters, shown on D-Star radios.</span>
        </label>
        <label>
          Encoder gain
          <input value={value.vocoderGainDb} inputMode="decimal" onChange={(e) => set("vocoderGainDb", e.target.value)} />
          <span className="field-hint">AMBE 2400 software encoder (OP25). 0 = calibrated level.</span>
        </label>
      </div>
    </div>
  );
}

export default DStarConfig;
