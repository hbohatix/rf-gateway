import type { P25Config as P25ConfigType } from "../../types/radio";

type P25ConfigProps = {
  value: P25ConfigType;
  onChange: (value: P25ConfigType) => void;
};

function P25Config({
  value,
  onChange,
}: P25ConfigProps) {
  return (
    <div className="protocol-config">
      <h3>P25 Configuration</h3>

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
          NAC
          <input
            value={value.nac}
            onChange={(event) =>
              onChange({
                ...value,
                nac: event.target.value,
              })
            }
          />
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

        <label>
          Modulation
          <select
            value={value.modulation}
            onChange={(event) =>
              onChange({
                ...value,
                modulation:
                  event.target.value as "c4fm" | "cqpsk",
              })
            }
          >
            <option value="c4fm">C4FM</option>
            <option value="cqpsk">CQPSK</option>
          </select>
        </label>
      </div>
    </div>
  );
}

export default P25Config;