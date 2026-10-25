import type { FMConfig as FMConfigType } from "../../types/radio";

type FMConfigProps = {
  value: FMConfigType;
  onChange: (value: FMConfigType) => void;
};

function FMConfig({ value, onChange }: FMConfigProps) {
  const set = <K extends keyof FMConfigType>(key: K, next: FMConfigType[K]) => onChange({ ...value, [key]: next });

  return (
    <div className="protocol-config">
      <h3>Analog FM</h3>
      <div className="form-grid">
        <label>
          Frequency (MHz)
          <input value={value.frequency} inputMode="decimal" onChange={(e) => set("frequency", e.target.value)} />
        </label>
        <label>
          Channel spacing
          <select value={value.channelSpacing} onChange={(e) => set("channelSpacing", e.target.value as "12.5" | "25")}>
            <option value="12.5">12.5 kHz</option>
            <option value="25">25 kHz</option>
          </select>
        </label>
        <label>
          Deviation
          <select value={value.deviation} onChange={(e) => set("deviation", e.target.value as "2.5" | "5")}>
            <option value="2.5">2.5 kHz</option>
            <option value="5">5.0 kHz</option>
          </select>
        </label>
        <label>
          TX CTCSS (Hz)
          <input value={value.txCtcss} placeholder="none" onChange={(e) => set("txCtcss", e.target.value)} />
        </label>
        <label>
          RX CTCSS (Hz)
          <input value={value.rxCtcss} placeholder="none" onChange={(e) => set("rxCtcss", e.target.value)} />
        </label>
        <label>
          Pre-emphasis
          <select value={value.preEmphasis} onChange={(e) => set("preEmphasis", e.target.value as "on" | "off")}>
            <option value="on">On</option>
            <option value="off">Off</option>
          </select>
        </label>
        <label>
          Source audio gain
          <input value={value.audioGain} inputMode="decimal" onChange={(e) => set("audioGain", e.target.value)} />
          <span className="field-hint">Linear factor before MMDVM-Host (1.0 = unchanged).</span>
        </label>
      </div>
    </div>
  );
}

export default FMConfig;
