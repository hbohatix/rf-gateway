import type { AmbeVocoder } from "../../types/radio";

export type AmbeVocoderValue = {
  vocoder: AmbeVocoder;
  vocoderDevice: string;
  vocoderBaud: string;
  vocoderHost: string;
  vocoderPort: string;
  vocoderGainDb: string;
};

type Props<T extends AmbeVocoderValue> = {
  value: T;
  onChange: (value: T) => void;
};

/** AMBE+2 encoder selection shared by DMR and YSF (DN). */
function AmbeVocoderFields<T extends AmbeVocoderValue>({ value, onChange }: Props<T>) {
  const set = <K extends keyof AmbeVocoderValue>(key: K, next: AmbeVocoderValue[K]) => onChange({ ...value, [key]: next });

  return (
    <>
      <h3 style={{ marginTop: 18 }}>AMBE+2 vocoder</h3>
      <div className="form-grid">
        <label>
          Encoder
          <select value={value.vocoder} onChange={(e) => set("vocoder", e.target.value as AmbeVocoder)}>
            <option value="software">Software (OP25, no hardware)</option>
            <option value="dv3000_serial">DVSI AMBE-3000 — serial (ThumbDV, DV3000)</option>
            <option value="ambeserver">DVSI AMBE-3000 — AMBEServer (UDP)</option>
          </select>
          <span className="field-hint">
            {value.vocoder === "software"
              ? "Built with backend/native/build_ambe_wrapper.sh."
              : "Experimental: needs a DVSI chip; audio quality is better than the software encoder."}
          </span>
        </label>
        {value.vocoder === "dv3000_serial" && (
          <>
            <label>
              Serial device
              <input value={value.vocoderDevice} onChange={(e) => set("vocoderDevice", e.target.value)} />
            </label>
            <label>
              Baud rate
              <select value={value.vocoderBaud} onChange={(e) => set("vocoderBaud", e.target.value)}>
                <option value="460800">460800 (ThumbDV)</option>
                <option value="230400">230400 (DV3000 hat)</option>
                <option value="921600">921600</option>
                <option value="115200">115200</option>
              </select>
            </label>
          </>
        )}
        {value.vocoder === "ambeserver" && (
          <>
            <label>
              AMBEServer host
              <input value={value.vocoderHost} onChange={(e) => set("vocoderHost", e.target.value)} />
            </label>
            <label>
              UDP port
              <input value={value.vocoderPort} inputMode="numeric" onChange={(e) => set("vocoderPort", e.target.value)} />
            </label>
          </>
        )}
        {value.vocoder === "software" && (
          <label>
            Encoder gain (dB)
            <input value={value.vocoderGainDb} inputMode="decimal" onChange={(e) => set("vocoderGainDb", e.target.value)} />
          </label>
        )}
      </div>
    </>
  );
}

export default AmbeVocoderFields;
