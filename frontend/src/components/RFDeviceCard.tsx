import type { RFDevice } from "../types/rfDevice";


type RFDeviceCardProps = {
  device: RFDevice;
  selected?: boolean;
  onSelect?: (device: RFDevice) => void;
};


function getDeviceName(device: RFDevice): string {
  if (device.driver.toLowerCase() === "sx") {
    return "SXceiver";
  }

  if (device.label.trim().length > 0) {
    return device.label;
  }

  return device.driver;
}


function getDeviceStatus(device: RFDevice): string {
  if (!device.available) {
    return "UNAVAILABLE";
  }

  if (!device.probe_ok) {
    return "PROBE ERROR";
  }

  return "READY";
}


function yesNo(value: boolean | undefined): string {
  if (value === undefined) {
    return "—";
  }

  return value ? "YES" : "NO";
}


function RFDeviceCard({
  device,
  selected = false,
  onSelect,
}: RFDeviceCardProps) {
  const capabilities = device.capabilities;

  const deviceName = getDeviceName(device);
  const status = getDeviceStatus(device);

  const selectable =
    device.available &&
    device.probe_ok &&
    onSelect !== undefined;

  function handleClick() {
    if (!selectable) {
      return;
    }

    onSelect(device);
  }

  return (
    <button
      type="button"
      className={[
        "rf-device-card",
        selected ? "selected" : "",
        !device.probe_ok ? "error" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={handleClick}
      disabled={!device.available}
    >
      <div className="rf-device-card-header">
        <div>
          <div className="rf-device-name">
            {deviceName}
          </div>

          <div className="rf-device-backend">
            {device.backend}
            {" · "}
            {device.driver}
          </div>
        </div>

        <div
          className={[
            "rf-device-status",
            device.probe_ok ? "ready" : "error",
          ].join(" ")}
        >
          {status}
        </div>
      </div>

      <div className="rf-device-details">
        <div className="rf-device-detail">
          <span>Hardware</span>
          <strong>
            {capabilities.hardware ?? "—"}
          </strong>
        </div>

        <div className="rf-device-detail">
          <span>HW version</span>
          <strong>
            {capabilities.hardware_version ?? "—"}
          </strong>
        </div>

        <div className="rf-device-detail">
          <span>Clock</span>
          <strong>
            {capabilities.clock ?? "—"}
          </strong>
        </div>

        <div className="rf-device-detail">
          <span>RX channels</span>
          <strong>
            {capabilities.rx_channels ?? "—"}
          </strong>
        </div>

        <div className="rf-device-detail">
          <span>TX channels</span>
          <strong>
            {capabilities.tx_channels ?? "—"}
          </strong>
        </div>

        <div className="rf-device-detail">
          <span>Full duplex</span>
          <strong>
            {yesNo(capabilities.full_duplex)}
          </strong>
        </div>

        <div className="rf-device-detail">
          <span>Timestamps</span>
          <strong>
            {yesNo(capabilities.timestamps)}
          </strong>
        </div>

        <div className="rf-device-detail">
          <span>AGC</span>
          <strong>
            {yesNo(capabilities.agc)}
          </strong>
        </div>

        <div className="rf-device-detail">
          <span>RX gain</span>
          <strong>
            {capabilities.rx_gain_range_db
              ? `${capabilities.rx_gain_range_db} dB`
              : "—"}
          </strong>
        </div>

        <div className="rf-device-detail">
          <span>TX gain</span>
          <strong>
            {capabilities.tx_gain_range_db
              ? `${capabilities.tx_gain_range_db} dB`
              : "—"}
          </strong>
        </div>
      </div>

      {device.probe_error && (
        <div className="rf-device-probe-error">
          {device.probe_error}
        </div>
      )}

      {selected && (
        <div className="rf-device-selected">
          SELECTED
        </div>
      )}
    </button>
  );
}


export default RFDeviceCard;
