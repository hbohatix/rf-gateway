import { useI18n } from "../i18n";
import { formatFrequency, formatSampleRate, formatSignedFrequency } from "../lib/format";
import type { MMDVMProcessStatus, MMDVMStatus } from "../types/runtime";

function processLabel(process: MMDVMProcessStatus | undefined, t: ReturnType<typeof useI18n>["t"]) {
  if (!process?.running) {
    return { text: t("status.stopped"), tone: "" };
  }
  return process.ready ? { text: t("status.ready"), tone: "ok" } : { text: t("status.starting"), tone: "warn" };
}

type Props = {
  status: MMDVMStatus | null;
  runtimeActive: boolean;
  rfTxActive: boolean;
  compact?: boolean;
};

export default function TelemetryTiles({ status, runtimeActive, rfTxActive, compact = false }: Props) {
  const { t } = useI18n();
  const iq = processLabel(status?.mmdvm_iq, t);
  const host = processLabel(status?.mmdvm_host, t);

  const tiles: { label: string; value: string; tone?: string }[] = [
    {
      label: t("status.runtime"),
      value: runtimeActive ? t("status.active") : t("status.stopped"),
      tone: runtimeActive ? "ok" : "",
    },
    { label: "RF TX", value: rfTxActive ? "ON" : "OFF", tone: rfTxActive ? "danger" : "" },
    { label: t("tel.modem_mode"), value: status?.modem_mode?.toUpperCase() ?? "—", tone: "info" },
    { label: t("tel.channel"), value: formatFrequency(status?.channel_frequency_hz, 6) },
  ];

  if (!compact) {
    tiles.push(
      { label: t("tel.sdr_center"), value: formatFrequency(status?.sdr_tx_center_frequency_hz, 6) },
      { label: t("tel.digital_if"), value: formatSignedFrequency(status?.digital_if_hz) },
      { label: t("tel.sample_rate"), value: formatSampleRate(status?.sample_rate_hz) },
      {
        label: t("tel.iq_streams"),
        value: status?.iq_streams_active ? t("status.active") : "OFF",
        tone: status?.iq_streams_active ? "ok" : "",
      },
      { label: "MMDVM-IQ", value: iq.text, tone: iq.tone },
      { label: "MMDVM-Host", value: host.text, tone: host.tone },
      { label: "Driver", value: status?.driver_name ?? "—" },
      { label: "HW", value: status?.hardware_version ?? "—" },
    );
  }

  return (
    <>
      <div className="tile-grid">
        {tiles.map((tile) => (
          <div className="tile" key={tile.label}>
            <span className="tile-label">{tile.label}</span>
            <span className={`tile-value ${tile.tone ?? ""}`}>{tile.value}</span>
          </div>
        ))}
      </div>
      {!compact && status?.last_error && (
        <div className="banner banner-danger" style={{ marginTop: 12, marginBottom: 0 }}>
          <strong>{t("tel.last_error")}:</strong>&nbsp;{status.last_error}
        </div>
      )}
    </>
  );
}
