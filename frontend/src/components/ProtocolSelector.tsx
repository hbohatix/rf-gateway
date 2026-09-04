import type { Protocol } from "../types/radio";

type ProtocolSelectorProps = {
  activeProtocol: Protocol | null;
  disabled: boolean;
  onToggle: (protocol: Protocol) => void;
};

function ProtocolSelector({
  activeProtocol,
  disabled,
  onToggle,
}: ProtocolSelectorProps) {
  return (
    <div className="protocol-selector">
      <button
        type="button"
        disabled={disabled}
        className={`protocol-card ${
          activeProtocol === "fm" ? "active" : ""
        }`}
        onClick={() => onToggle("fm")}
      >
        <strong>FM</strong>
        <small>Analog FM</small>
      </button>

      <button
        type="button"
        disabled={disabled}
        className={`protocol-card ${
          activeProtocol === "dmr" ? "active" : ""
        }`}
        onClick={() => onToggle("dmr")}
      >
        <strong>DMR</strong>
        <small>Digital Mobile Radio</small>
      </button>

      <button
        type="button"
        disabled={disabled}
        className={`protocol-card ${
          activeProtocol === "p25" ? "active" : ""
        }`}
        onClick={() => onToggle("p25")}
      >
        <strong>P25</strong>
        <small>APCO Project 25</small>
      </button>

      <button
        type="button"
        disabled={disabled}
        className={`protocol-card ${
          activeProtocol === "tetra" ? "active" : ""
        }`}
        onClick={() => onToggle("tetra")}
      >
        <strong>TETRA</strong>
        <small>Terrestrial Trunked Radio</small>
      </button>
    </div>
  );
}

export default ProtocolSelector;