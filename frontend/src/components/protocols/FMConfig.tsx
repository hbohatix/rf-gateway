import type { FMConfig as FMConfigType } from "../../types/radio";

type FMConfigProps = {
  value: FMConfigType;
  onChange: (value: FMConfigType) => void;
};

function FMConfig({
  value,
  onChange,
}: FMConfigProps) {
  return (
    <div className="protocol-config">
      <h3>Analog FM Configuration</h3>

      <div className="form-grid">
        <label>
          Frequency
          <input
            value={value.frequency}
            onChange={(event) =>
              onChange({
                ...value,
                frequency: event.target.value,
              })
            }
          />
        </label>

        <label>
          Channel Spacing
          <select
            value={value.channelSpacing}
            onChange={(event) =>
              onChange({
                ...value,
                channelSpacing:
                  event.target.value as "12.5" | "25",
              })
            }
          >
            <option value="12.5">12.5 kHz</option>
            <option value="25">25 kHz</option>
          </select>
        </label>

        <label>
          Deviation
          <select
            value={value.deviation}
            onChange={(event) =>
              onChange({
                ...value,
                deviation:
                  event.target.value as "2.5" | "5",
              })
            }
          >
            <option value="2.5">2.5 kHz</option>
            <option value="5">5.0 kHz</option>
          </select>
        </label>

        <label>
          TX CTCSS
          <input
            value={value.txCtcss}
            placeholder="None"
            onChange={(event) =>
              onChange({
                ...value,
                txCtcss: event.target.value,
              })
            }
          />
        </label>

        <label>
          RX CTCSS
          <input
            value={value.rxCtcss}
            placeholder="None"
            onChange={(event) =>
              onChange({
                ...value,
                rxCtcss: event.target.value,
              })
            }
          />
        </label>

        <label>
          Pre-emphasis
          <select
            value={value.preEmphasis}
            onChange={(event) =>
              onChange({
                ...value,
                preEmphasis:
                  event.target.value as "on" | "off",
              })
            }
          >
            <option value="on">On</option>
            <option value="off">Off</option>
          </select>
        </label>
      </div>
    </div>
  );
}

export default FMConfig;