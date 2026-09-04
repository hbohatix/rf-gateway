import type { DMRConfig as DMRConfigType } from "../../types/radio";

type DMRConfigProps = {
  value: DMRConfigType;
  onChange: (value: DMRConfigType) => void;
};

function DMRConfig({
  value,
  onChange,
}: DMRConfigProps) {
  return (
    <div className="protocol-config">
      <h3>DMR Configuration</h3>

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
          Color Code
          <input
            type="number"
            min="0"
            max="15"
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
          Timeslot
          <select
            value={value.timeslot}
            onChange={(event) =>
              onChange({
                ...value,
                timeslot:
                  event.target.value as "1" | "2",
              })
            }
          >
            <option value="1">TS1</option>
            <option value="2">TS2</option>
          </select>
        </label>

        <label>
          Talkgroup
          <input
            value={value.talkgroup}
            onChange={(event) =>
              onChange({
                ...value,
                talkgroup: event.target.value,
              })
            }
          />
        </label>

        <label>
          Radio ID
          <input
            value={value.radioId}
            onChange={(event) =>
              onChange({
                ...value,
                radioId: event.target.value,
              })
            }
          />
        </label>
      </div>
    </div>
  );
}

export default DMRConfig;