import { useI18n } from "../i18n";
import { PROTOCOLS, PROTOCOL_INFO } from "../lib/modes";
import type { VoiceCapabilities } from "../types/radio";

const REASONS: Record<string, string> = {
  p25_imbe_encoder_unavailable: "IMBE wrapper missing — run backend/native/build_imbe_wrapper.sh",
  dmr_ambe_vocoder_unavailable: "AMBE+2 encoder missing — run backend/native/build_ambe_wrapper.sh",
  dstar_ambe_vocoder_unavailable: "AMBE encoder missing — run backend/native/build_ambe_wrapper.sh",
  nxdn_ambe_vocoder_unavailable: "AMBE+2 encoder missing — run backend/native/build_ambe_wrapper.sh",
  ysf_ambe_vocoder_unavailable: "AMBE+2 encoder missing — run backend/native/build_ambe_wrapper.sh",
  tetra_vocoder_and_framing_not_implemented: "MMDVM has no TETRA mode (FlowStation is a TETRA base station)",
};

export default function VoicePaths({ capabilities }: { capabilities: VoiceCapabilities | null }) {
  const { t } = useI18n();
  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">{t("dash.voice_paths")}</span>
        <span className="card-sub">{t("dash.voice_paths.sub")}</span>
      </div>
      <div className="card-body flush path-list">
        {PROTOCOLS.map((protocol) => {
          const capability = capabilities?.[protocol];
          const info = PROTOCOL_INFO[protocol];
          const ready = capability?.bridge_state === "ready";
          const notImplemented = capability?.bridge_state === "not_implemented";
          const reason = capability?.blocking_reason;
          const vocoder = capability?.vocoder;
          return (
            <div className="path-row" key={protocol}>
              <span className="path-name">{info.name}</span>
              <div className="path-desc">
                {info.description}
                <small>
                  {info.codec}
                  {vocoder?.backend ? ` · ${vocoder.backend}` : ""}
                  {reason ? ` · ${REASONS[reason] ?? reason}` : ""}
                </small>
              </div>
              {capability === undefined ? (
                <span className="pill pill-idle">—</span>
              ) : ready ? (
                <span className="pill pill-ok">{t("status.ready")}</span>
              ) : notImplemented ? (
                <span className="pill pill-idle">{t("status.not_implemented")}</span>
              ) : (
                <span className="pill pill-warn">{t("status.unavailable")}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
