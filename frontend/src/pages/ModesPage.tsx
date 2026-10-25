import Icon from "../components/Icon";
import ProtocolSelector from "../components/ProtocolSelector";
import DMRConfigForm from "../components/protocols/DMRConfig";
import FMConfigForm from "../components/protocols/FMConfig";
import P25ConfigForm from "../components/protocols/P25Config";
import TETRAConfigForm from "../components/protocols/TETRAConfig";
import YSFConfigForm from "../components/protocols/YSFConfig";
import DStarConfigForm from "../components/protocols/DStarConfig";
import NXDNConfigForm from "../components/protocols/NXDNConfig";
import { useI18n } from "../i18n";
import { getDeviceDisplayName } from "../lib/format";
import type {
  DMRConfig,
  DStarConfig,
  FMConfig,
  NXDNConfig,
  P25Config,
  Protocol,
  TETRAConfig,
  VoiceCapabilities,
  YSFConfig,
} from "../types/radio";
import type { RFDevice } from "../types/rfDevice";

type Props = {
  activeProtocol: Protocol | null;
  onToggleProtocol: (protocol: Protocol) => void;
  runtimeActive: boolean;
  runtimeReady: boolean;
  rfTxActive: boolean;
  capabilities: VoiceCapabilities | null;
  devices: RFDevice[];
  selectedDevice: RFDevice | null;
  onSelectDevice: (device: RFDevice) => void;
  fmConfig: FMConfig;
  setFmConfig: (value: FMConfig) => void;
  dmrConfig: DMRConfig;
  setDmrConfig: (value: DMRConfig) => void;
  p25Config: P25Config;
  setP25Config: (value: P25Config) => void;
  nxdnConfig: NXDNConfig;
  setNxdnConfig: (value: NXDNConfig) => void;
  dstarConfig: DStarConfig;
  setDstarConfig: (value: DStarConfig) => void;
  ysfConfig: YSFConfig;
  setYsfConfig: (value: YSFConfig) => void;
  tetraConfig: TETRAConfig;
  setTetraConfig: (value: TETRAConfig) => void;
  runtimeMessage: string | null;
  runtimeError: string | null;
  onStart: () => void;
  onStop: () => void;
  onCalibrate: () => void;
};

export default function ModesPage(props: Props) {
  const { t } = useI18n();
  const {
    activeProtocol,
    runtimeActive,
    rfTxActive,
    devices,
    selectedDevice,
    capabilities,
  } = props;
  const usable = devices.filter((device) => device.available && device.probe_ok);
  const capability = activeProtocol ? capabilities?.[activeProtocol] : undefined;

  return (
    <div className="page-grid two">
      <div className="card">
        <div className="card-head">
          <span className="card-title">{t("rf.protocol")}</span>
          <span className="card-sub">{t("rf.autosave")}</span>
          <div className="card-actions">
            {rfTxActive ? (
              <span className="pill pill-tx">TX</span>
            ) : (
              <span className={`pill ${runtimeActive ? "pill-ok" : "pill-idle"}`}>
                {runtimeActive ? t("status.active") : t("status.stopped")}
              </span>
            )}
          </div>
        </div>
        <div className="card-body">
          <ProtocolSelector
            activeProtocol={activeProtocol}
            disabled={runtimeActive}
            onToggle={props.onToggleProtocol}
            capabilities={capabilities}
          />
          {activeProtocol === null && <div className="empty-state">{t("rf.disabled")}</div>}
          {activeProtocol === "fm" && <FMConfigForm value={props.fmConfig} onChange={props.setFmConfig} />}
          {activeProtocol === "dmr" && <DMRConfigForm value={props.dmrConfig} onChange={props.setDmrConfig} />}
          {activeProtocol === "ysf" && <YSFConfigForm value={props.ysfConfig} onChange={props.setYsfConfig} />}
          {activeProtocol === "dstar" && <DStarConfigForm value={props.dstarConfig} onChange={props.setDstarConfig} />}
          {activeProtocol === "nxdn" && <NXDNConfigForm value={props.nxdnConfig} onChange={props.setNxdnConfig} />}
          {activeProtocol === "p25" && <P25ConfigForm value={props.p25Config} onChange={props.setP25Config} />}
          {activeProtocol === "tetra" && <TETRAConfigForm value={props.tetraConfig} onChange={props.setTetraConfig} />}
          {capability && capability.bridge_state !== "ready" && (
            <div className="banner banner-warn" style={{ marginTop: 14, marginBottom: 0 }}>
              {capability.bridge_state === "not_implemented"
                ? "This protocol can be configured, but source audio cannot be transmitted on it yet."
                : `Source audio is unavailable: ${capability.vocoder?.error ?? capability.blocking_reason}`}
            </div>
          )}
        </div>
      </div>

      <div>
        <div className="card">
          <div className="card-head">
            <span className="card-title">{t("rf.device")}</span>
          </div>
          <div className="card-body" style={{ display: "grid", gap: 12 }}>
            <select
              value={selectedDevice?.id ?? ""}
              disabled={runtimeActive}
              onChange={(event) => {
                const device = devices.find((item) => item.id === event.target.value);
                if (device) {
                  props.onSelectDevice(device);
                }
              }}
            >
              <option value="" disabled>
                {t("rf.no_device")}
              </option>
              {devices.map((device) => (
                <option key={device.id} value={device.id} disabled={!device.available || !device.probe_ok}>
                  {getDeviceDisplayName(device)} · {device.backend} · {device.driver}
                  {!device.probe_ok ? " (probe error)" : ""}
                </option>
              ))}
            </select>
            {usable.length === 0 && <div className="banner banner-warn" style={{ margin: 0 }}>{t("rf.no_devices")}</div>}

            {props.runtimeMessage && <div className="banner banner-ok" style={{ margin: 0 }}>{props.runtimeMessage}</div>}
            {props.runtimeError && <div className="banner banner-danger" style={{ margin: 0 }}>{props.runtimeError}</div>}

            <div className="btn-row">
              <button
                type="button"
                className="btn btn-primary"
                disabled={!activeProtocol || !selectedDevice || runtimeActive}
                onClick={props.onStart}
              >
                <Icon name="play" /> {t("rf.start")}
              </button>
              <button type="button" className="btn btn-danger" disabled={!runtimeActive} onClick={props.onStop}>
                <Icon name="stop" /> {t("rf.stop")}
              </button>
              <button
                type="button"
                className="btn"
                disabled={!activeProtocol || !selectedDevice || !runtimeActive || !props.runtimeReady || rfTxActive}
                onClick={props.onCalibrate}
              >
                <Icon name="calibrate" /> {t("rf.calibrate")}
              </button>
            </div>
            <p className="help-text">
              Starting the runtime keys nothing by itself; routes decide when audio is transmitted. Operate only on
              frequencies you are licensed for.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
