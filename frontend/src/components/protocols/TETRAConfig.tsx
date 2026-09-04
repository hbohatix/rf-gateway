import type { TETRAConfig as TETRAConfigType } from "../../types/radio";

type TETRAConfigProps = {
  value: TETRAConfigType;
  onChange: (value: TETRAConfigType) => void;
};

function TETRAConfig({
  value,
  onChange,
}: TETRAConfigProps) {
  return (
    <div className="protocol-config">
      <h3>TETRA Configuration</h3>

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
          Mode
          <select
            value={value.mode}
            onChange={(event) =>
              onChange({
                ...value,
                mode:
                  event.target.value as "dmo" | "tmo",
              })
            }
          >
            <option value="dmo">DMO</option>
            <option value="tmo">TMO</option>
          </select>
        </label>

        <label>
          MCC
          <input
            value={value.mcc}
            onChange={(event) =>
              onChange({
                ...value,
                mcc: event.target.value,
              })
            }
          />
        </label>

        <label>
          MNC
          <input
            value={value.mnc}
            onChange={(event) =>
              onChange({
                ...value,
                mnc: event.target.value,
              })
            }
          />
        </label>

        <label>
          Color Code
          <input
            value={value.colorCode}
            onChange={(event) =>
              onChange({
                ...value,
                colorCode: event.target.value,
              })
            }
          />
        </label>

        <label>
          GSSI
          <input
            value={value.gssi}
            onChange={(event) =>
              onChange({
                ...value,
                gssi: event.target.value,
              })
            }
          />
        </label>
      </div>
    </div>
  );
}

export default TETRAConfig;