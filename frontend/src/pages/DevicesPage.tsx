import Icon from "../components/Icon";
import RFDeviceCard from "../components/RFDeviceCard";
import { useI18n } from "../i18n";
import type { RFDevice } from "../types/rfDevice";

type Props = {
  devices: RFDevice[];
  loading: boolean;
  error: string | null;
  warnings: string[];
  selectedDeviceId: string | null;
  runtimeActive: boolean;
  onRefresh: () => void;
  onSelect: (device: RFDevice) => void;
};

export default function DevicesPage({ devices, loading, error, warnings, selectedDeviceId, runtimeActive, onRefresh, onSelect }: Props) {
  const { t } = useI18n();
  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">{t("page.devices")}</span>
        <span className="card-sub">SoapySDR · MMDVM UART/USB/GPIO</span>
        <div className="card-actions">
          <button type="button" className="btn btn-sm" disabled={loading || runtimeActive} onClick={onRefresh}>
            <Icon name="refresh" /> {loading ? t("rf.scanning") : t("rf.refresh")}
          </button>
        </div>
      </div>
      <div className="card-body">
        {error && <div className="banner banner-danger">{error}</div>}
        {warnings.map((warning) => (
          <div className="banner banner-warn" key={warning}>
            {warning}
          </div>
        ))}
        {!loading && !error && devices.length === 0 && <div className="empty-state">{t("rf.no_devices")}</div>}
        {devices.length > 0 && (
          <div className="rf-device-grid">
            {devices.map((device) => (
              <RFDeviceCard
                key={device.id}
                device={device}
                selected={device.id === selectedDeviceId}
                onSelect={runtimeActive ? undefined : onSelect}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
