import { PROTOCOLS, PROTOCOL_INFO } from "../lib/modes";
import type { Protocol, VoiceCapabilities } from "../types/radio";

type ProtocolSelectorProps = {
  activeProtocol: Protocol | null;
  disabled: boolean;
  onToggle: (protocol: Protocol) => void;
  capabilities?: VoiceCapabilities | null;
};

function ProtocolSelector({ activeProtocol, disabled, onToggle, capabilities }: ProtocolSelectorProps) {
  return (
    <div className="protocol-selector">
      {PROTOCOLS.map((protocol) => {
        const info = PROTOCOL_INFO[protocol];
        const capability = capabilities?.[protocol];
        const state = capability?.bridge_state;
        return (
          <button
            key={protocol}
            type="button"
            disabled={disabled}
            className={`protocol-card ${activeProtocol === protocol ? "active" : ""}`}
            onClick={() => onToggle(protocol)}
          >
            <strong>{info.name}</strong>
            <small>{info.description}</small>
            <span className="protocol-card__codec">
              {info.codec}
              {state && (
                <i
                  className={`protocol-card__dot ${state === "ready" ? "ok" : state === "not_implemented" ? "idle" : "warn"}`}
                  title={state === "ready" ? "Source audio supported" : capability?.blocking_reason ?? state}
                />
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export default ProtocolSelector;
