import { useEffect, useState } from "react";

import "./App.css";

import ProtocolSelector from "./components/ProtocolSelector";
import RFDeviceCard from "./components/RFDeviceCard";

import FMConfigForm from "./components/protocols/FMConfig";
import DMRConfigForm from "./components/protocols/DMRConfig";
import P25ConfigForm from "./components/protocols/P25Config";
import TETRAConfigForm from "./components/protocols/TETRAConfig";

import type {
  DMRConfig,
  FMConfig,
  P25Config,
  Protocol,
  TETRAConfig,
} from "./types/radio";

import type {
  RFDevice,
  RFDevicesResponse,
} from "./types/rfDevice";


type Health = {
  status: string;
  service: string;
  version: string;
};


type RFStatus = {
  tx: boolean;
  protocol: Protocol | null;
  device_id?: string | null;
  config: unknown;
  error?: string | null;
};


type SavedFMConfig = {
  frequency_hz: number;
  channel_spacing_khz: number;
  deviation_khz: number;
  tx_ctcss_hz: number | null;
  rx_ctcss_hz: number | null;
  pre_emphasis: boolean;
  updated_at?: string;
};


type SavedDMRConfig = {
  frequency_hz: number;
  color_code: number;
  timeslot: number;
  talkgroup: number;
  radio_id: number;
  updated_at?: string;
};


type SavedP25Config = {
  frequency_hz: number;
  nac: string;
  talkgroup: number;
  radio_id: number;
  modulation: string;
  updated_at?: string;
};


type SavedTETRAConfig = {
  frequency_hz: number;
  mode: string;
  mcc: string;
  mnc: string;
  color_code: number;
  gssi: number;
  updated_at?: string;
};


type SavedModesResponse = {
  version: number;

  modes: {
    fm?: SavedFMConfig;
    dmr?: SavedDMRConfig;
    p25?: SavedP25Config;
    tetra?: SavedTETRAConfig;
  };
};


const API_BASE_URL =
  `${window.location.protocol}//${window.location.hostname}:8000`;


const STORAGE_KEYS = {
  activeProtocol: "rf-gateway.activeProtocol",
  selectedDeviceId: "rf-gateway.selectedDeviceId",

  fmConfig: "rf-gateway.fmConfig",
  dmrConfig: "rf-gateway.dmrConfig",
  p25Config: "rf-gateway.p25Config",
  tetraConfig: "rf-gateway.tetraConfig",
};


const DEFAULT_FM_CONFIG: FMConfig = {
  frequency: "145.500000",
  channelSpacing: "12.5",
  deviation: "2.5",
  txCtcss: "",
  rxCtcss: "",
  preEmphasis: "on",
};


const DEFAULT_DMR_CONFIG: DMRConfig = {
  frequency: "438.800000",
  colorCode: "1",
  timeslot: "2",
  talkgroup: "260",
  radioId: "2601292",
};


const DEFAULT_P25_CONFIG: P25Config = {
  frequency: "145.500000",
  nac: "293",
  talkgroup: "260",
  radioId: "2601292",
  modulation: "c4fm",
};


const DEFAULT_TETRA_CONFIG: TETRAConfig = {
  frequency: "430.000000",
  mode: "dmo",
  mcc: "901",
  mnc: "9999",
  colorCode: "1",
  gssi: "1",
};


function loadFromStorage<T>(
  key: string,
  defaultValue: T
): T {
  try {
    const storedValue =
      localStorage.getItem(key);

    if (!storedValue) {
      return defaultValue;
    }

    return JSON.parse(
      storedValue
    ) as T;
  } catch {
    return defaultValue;
  }
}


function loadProtocolFromStorage():
  Protocol | null {
  const storedValue =
    localStorage.getItem(
      STORAGE_KEYS.activeProtocol
    );

  if (
    storedValue === "fm" ||
    storedValue === "dmr" ||
    storedValue === "p25" ||
    storedValue === "tetra"
  ) {
    return storedValue;
  }

  return null;
}


function loadSelectedDeviceId():
  string | null {
  return localStorage.getItem(
    STORAGE_KEYS.selectedDeviceId
  );
}


function frequencyToHz(
  frequency: string
): number {
  const mhz = Number(frequency);

  if (
    !Number.isFinite(mhz) ||
    mhz <= 0
  ) {
    throw new Error(
      "Invalid frequency"
    );
  }

  return Math.round(
    mhz * 1_000_000
  );
}


function hzToMHzString(
  frequencyHz: number
): string {
  return (
    frequencyHz /
    1_000_000
  ).toFixed(6);
}


function optionalNumberToString(
  value: number | null | undefined
): string {
  if (
    value === null ||
    value === undefined
  ) {
    return "";
  }

  return String(value);
}


function requiredInteger(
  value: string,
  fieldName: string
): number {
  const parsed = Number(value);

  if (!Number.isInteger(parsed)) {
    throw new Error(
      `${fieldName} must be an integer`
    );
  }

  return parsed;
}


function optionalNumber(
  value: string
): number | null {
  const trimmed =
    value.trim();

  if (trimmed === "") {
    return null;
  }

  const parsed =
    Number(trimmed);

  if (!Number.isFinite(parsed)) {
    throw new Error(
      `Invalid numeric value: ${value}`
    );
  }

  return parsed;
}


function getDeviceDisplayName(
  device: RFDevice
): string {
  if (
    device.driver.toLowerCase() === "sx"
  ) {
    return "SXceiver";
  }

  if (
    device.label.trim().length > 0
  ) {
    return device.label;
  }

  return device.driver;
}


function App() {
  const [
    health,
    setHealth,
  ] =
    useState<Health | null>(
      null
    );


  const [
    backendError,
    setBackendError,
  ] =
    useState<string | null>(
      null
    );


  const [
    activeProtocol,
    setActiveProtocol,
  ] =
    useState<Protocol | null>(
      () =>
        loadProtocolFromStorage()
    );


  const [
    selectedDeviceId,
    setSelectedDeviceId,
  ] =
    useState<string | null>(
      () =>
        loadSelectedDeviceId()
    );


  const [
    devicesResponse,
    setDevicesResponse,
  ] =
    useState<RFDevicesResponse | null>(
      null
    );


  const [
    devicesLoading,
    setDevicesLoading,
  ] =
    useState(false);


  const [
    devicesError,
    setDevicesError,
  ] =
    useState<string | null>(
      null
    );


  const [
    txActive,
    setTxActive,
  ] =
    useState(false);


  const [
    runtimeMessage,
    setRuntimeMessage,
  ] =
    useState<string | null>(
      null
    );


  const [
    runtimeError,
    setRuntimeError,
  ] =
    useState<string | null>(
      null
    );


  const [
    fmConfig,
    setFmConfig,
  ] =
    useState<FMConfig>(
      () =>
        loadFromStorage(
          STORAGE_KEYS.fmConfig,
          DEFAULT_FM_CONFIG
        )
    );


  const [
    dmrConfig,
    setDmrConfig,
  ] =
    useState<DMRConfig>(
      () =>
        loadFromStorage(
          STORAGE_KEYS.dmrConfig,
          DEFAULT_DMR_CONFIG
        )
    );


  const [
    p25Config,
    setP25Config,
  ] =
    useState<P25Config>(
      () =>
        loadFromStorage(
          STORAGE_KEYS.p25Config,
          DEFAULT_P25_CONFIG
        )
    );


  const [
    tetraConfig,
    setTetraConfig,
  ] =
    useState<TETRAConfig>(
      () =>
        loadFromStorage(
          STORAGE_KEYS.tetraConfig,
          DEFAULT_TETRA_CONFIG
        )
    );


  const selectedDevice =
    devicesResponse?.devices.find(
      (device) =>
        device.id ===
        selectedDeviceId
    ) ?? null;


  const deviceCount =
    devicesResponse
      ?.device_count ?? 0;


  const loadDevices =
    async () => {
      setDevicesLoading(true);
      setDevicesError(null);

      try {
        const response =
          await fetch(
            `${API_BASE_URL}/api/devices`
          );

        if (!response.ok) {
          throw new Error(
            `HTTP ${response.status}`
          );
        }

        const data =
          (await response.json()) as RFDevicesResponse;

        setDevicesResponse(
          data
        );

        if (data.error) {
          setDevicesError(
            data.error
          );
        }
      } catch (error) {
        if (
          error instanceof Error
        ) {
          setDevicesError(
            error.message
          );
        } else {
          setDevicesError(
            "Unknown device discovery error"
          );
        }
      } finally {
        setDevicesLoading(false);
      }
    };


  const loadSavedModeConfigs =
    async () => {
      try {
        const response =
          await fetch(
            `${API_BASE_URL}/api/config/modes`
          );

        if (!response.ok) {
          throw new Error(
            `HTTP ${response.status}`
          );
        }

        const data =
          (await response.json()) as SavedModesResponse;


        if (data.modes.fm) {
          const saved =
            data.modes.fm;

          setFmConfig({
            frequency:
              hzToMHzString(
                saved.frequency_hz
              ),

            channelSpacing:
              saved.channel_spacing_khz === 25
                ? "25"
                : "12.5",

            deviation:
              saved.deviation_khz === 5
                ? "5"
                : "2.5",

            txCtcss:
              optionalNumberToString(
                saved.tx_ctcss_hz
              ),

            rxCtcss:
              optionalNumberToString(
                saved.rx_ctcss_hz
              ),

            preEmphasis:
              saved.pre_emphasis
                ? "on"
                : "off",
          });
        }


        if (data.modes.dmr) {
          const saved =
            data.modes.dmr;

          setDmrConfig({
            frequency:
              hzToMHzString(
                saved.frequency_hz
              ),

            colorCode:
              String(
                saved.color_code
              ),

            timeslot:
              saved.timeslot === 1
                ? "1"
                : "2",

            talkgroup:
              String(
                saved.talkgroup
              ),

            radioId:
              String(
                saved.radio_id
              ),
          });
        }


        if (data.modes.p25) {
          const saved =
            data.modes.p25;

          setP25Config({
            frequency:
              hzToMHzString(
                saved.frequency_hz
              ),

            nac:
              saved.nac,

            talkgroup:
              String(
                saved.talkgroup
              ),

            radioId:
              String(
                saved.radio_id
              ),

            modulation:
              saved.modulation === "cqpsk"
                ? "cqpsk"
                : "c4fm",
          });
        }


        if (data.modes.tetra) {
          const saved =
            data.modes.tetra;

          setTetraConfig({
            frequency:
              hzToMHzString(
                saved.frequency_hz
              ),

            mode:
              saved.mode === "tmo"
                ? "tmo"
                : "dmo",

            mcc:
              saved.mcc,

            mnc:
              saved.mnc,

            colorCode:
              String(
                saved.color_code
              ),

            gssi:
              String(
                saved.gssi
              ),
          });
        }
      } catch (error) {
        console.error(
          "Unable to load saved mode configurations:",
          error
        );
      }
    };


  useEffect(() => {
    fetch(
      `${API_BASE_URL}/api/health`
    )
      .then((response) => {
        if (!response.ok) {
          throw new Error(
            `HTTP ${response.status}`
          );
        }

        return response.json();
      })
      .then((data: Health) => {
        setHealth(data);
        setBackendError(null);
      })
      .catch(
        (error: Error) => {
          setBackendError(
            error.message
          );
        }
      );


    fetch(
      `${API_BASE_URL}/api/rf/status`
    )
      .then((response) => {
        if (!response.ok) {
          throw new Error(
            `HTTP ${response.status}`
          );
        }

        return response.json();
      })
      .then((data: RFStatus) => {
        setTxActive(
          data.tx
        );

        if (data.protocol) {
          setActiveProtocol(
            data.protocol
          );
        }

        if (data.device_id) {
          setSelectedDeviceId(
            data.device_id
          );
        }
      })
      .catch(() => {
        // Backend health state handles connectivity.
      });


    void loadSavedModeConfigs();
    void loadDevices();
  }, []);


  useEffect(() => {
    if (
      !devicesResponse
    ) {
      return;
    }

    const usableDevices =
      devicesResponse
        .devices
        .filter(
          (device) =>
            device.available &&
            device.probe_ok
        );


    if (
      selectedDeviceId &&
      usableDevices.some(
        (device) =>
          device.id ===
          selectedDeviceId
      )
    ) {
      return;
    }


    if (
      usableDevices.length === 1
    ) {
      setSelectedDeviceId(
        usableDevices[0].id
      );

      return;
    }


    if (
      selectedDeviceId !== null
    ) {
      setSelectedDeviceId(
        null
      );
    }
  }, [
    devicesResponse,
    selectedDeviceId,
  ]);


  useEffect(() => {
    if (activeProtocol) {
      localStorage.setItem(
        STORAGE_KEYS.activeProtocol,
        activeProtocol
      );
    } else {
      localStorage.removeItem(
        STORAGE_KEYS.activeProtocol
      );
    }
  }, [
    activeProtocol,
  ]);


  useEffect(() => {
    if (selectedDeviceId) {
      localStorage.setItem(
        STORAGE_KEYS.selectedDeviceId,
        selectedDeviceId
      );
    } else {
      localStorage.removeItem(
        STORAGE_KEYS.selectedDeviceId
      );
    }
  }, [
    selectedDeviceId,
  ]);


  useEffect(() => {
    localStorage.setItem(
      STORAGE_KEYS.fmConfig,
      JSON.stringify(
        fmConfig
      )
    );
  }, [
    fmConfig,
  ]);


  useEffect(() => {
    localStorage.setItem(
      STORAGE_KEYS.dmrConfig,
      JSON.stringify(
        dmrConfig
      )
    );
  }, [
    dmrConfig,
  ]);


  useEffect(() => {
    localStorage.setItem(
      STORAGE_KEYS.p25Config,
      JSON.stringify(
        p25Config
      )
    );
  }, [
    p25Config,
  ]);


  useEffect(() => {
    localStorage.setItem(
      STORAGE_KEYS.tetraConfig,
      JSON.stringify(
        tetraConfig
      )
    );
  }, [
    tetraConfig,
  ]);


  const toggleProtocol = (
    protocol: Protocol
  ) => {
    if (txActive) {
      return;
    }

    setRuntimeMessage(null);
    setRuntimeError(null);

    setActiveProtocol(
      (current) =>
        current === protocol
          ? null
          : protocol
    );
  };


  const selectDevice = (
    device: RFDevice
  ) => {
    if (txActive) {
      return;
    }

    if (
      !device.available ||
      !device.probe_ok
    ) {
      return;
    }

    setSelectedDeviceId(
      device.id
    );

    setRuntimeMessage(null);
    setRuntimeError(null);
  };


  const buildStartPayload =
    () => {
      if (!activeProtocol) {
        throw new Error(
          "Select an RF protocol first"
        );
      }

      if (!selectedDevice) {
        throw new Error(
          "Select an RF device first"
        );
      }


      if (
        activeProtocol === "fm"
      ) {
        return {
          protocol: "fm",

          device_id:
            selectedDevice.id,

          frequency_hz:
            frequencyToHz(
              fmConfig.frequency
            ),

          channel_spacing_khz:
            Number(
              fmConfig.channelSpacing
            ),

          deviation_khz:
            Number(
              fmConfig.deviation
            ),

          tx_ctcss_hz:
            optionalNumber(
              fmConfig.txCtcss
            ),

          rx_ctcss_hz:
            optionalNumber(
              fmConfig.rxCtcss
            ),

          pre_emphasis:
            fmConfig.preEmphasis ===
            "on",
        };
      }


      if (
        activeProtocol === "dmr"
      ) {
        return {
          protocol: "dmr",

          device_id:
            selectedDevice.id,

          frequency_hz:
            frequencyToHz(
              dmrConfig.frequency
            ),

          color_code:
            requiredInteger(
              dmrConfig.colorCode,
              "Color Code"
            ),

          timeslot:
            requiredInteger(
              dmrConfig.timeslot,
              "Timeslot"
            ),

          talkgroup:
            requiredInteger(
              dmrConfig.talkgroup,
              "Talkgroup"
            ),

          radio_id:
            requiredInteger(
              dmrConfig.radioId,
              "Radio ID"
            ),
        };
      }


      if (
        activeProtocol === "p25"
      ) {
        return {
          protocol: "p25",

          device_id:
            selectedDevice.id,

          frequency_hz:
            frequencyToHz(
              p25Config.frequency
            ),

          nac:
            p25Config.nac.trim(),

          talkgroup:
            requiredInteger(
              p25Config.talkgroup,
              "Talkgroup"
            ),

          radio_id:
            requiredInteger(
              p25Config.radioId,
              "Radio ID"
            ),

          modulation:
            p25Config.modulation,
        };
      }


      return {
        protocol: "tetra",

        device_id:
          selectedDevice.id,

        frequency_hz:
          frequencyToHz(
            tetraConfig.frequency
          ),

        mode:
          tetraConfig.mode,

        mcc:
          tetraConfig.mcc.trim(),

        mnc:
          tetraConfig.mnc.trim(),

        color_code:
          requiredInteger(
            tetraConfig.colorCode,
            "Color Code"
          ),

        gssi:
          requiredInteger(
            tetraConfig.gssi,
            "GSSI"
          ),
      };
    };


  const handleStart =
    async () => {
      try {
        setRuntimeMessage(null);
        setRuntimeError(null);


        if (!selectedDevice) {
          throw new Error(
            "Select an RF device first"
          );
        }


        const payload =
          buildStartPayload();


        const response =
          await fetch(
            `${API_BASE_URL}/api/rf/start`,
            {
              method: "POST",

              headers: {
                "Content-Type":
                  "application/json",
              },

              body:
                JSON.stringify(
                  payload
                ),
            }
          );


        const data =
          await response.json();


        if (!response.ok) {
          throw new Error(
            typeof data.detail ===
              "string"
              ? data.detail
              : JSON.stringify(
                  data.detail
                )
          );
        }


        if (data.error) {
          throw new Error(
            data.error
          );
        }


        setTxActive(
          data.tx
        );


        if (data.device_id) {
          setSelectedDeviceId(
            data.device_id
          );
        }


        setRuntimeMessage(
          `${activeProtocol?.toUpperCase()} runtime started on ${getDeviceDisplayName(selectedDevice)}`
        );
      } catch (error) {
        if (
          error instanceof Error
        ) {
          setRuntimeError(
            error.message
          );
        } else {
          setRuntimeError(
            "Unknown error"
          );
        }
      }
    };


  const handleStop =
    async () => {
      try {
        setRuntimeMessage(null);
        setRuntimeError(null);


        const response =
          await fetch(
            `${API_BASE_URL}/api/rf/stop`,
            {
              method: "POST",
            }
          );


        const data =
          await response.json();


        if (!response.ok) {
          throw new Error(
            `HTTP ${response.status}`
          );
        }


        if (data.error) {
          throw new Error(
            data.error
          );
        }


        setTxActive(
          data.tx
        );


        setRuntimeMessage(
          "RF runtime stopped"
        );
      } catch (error) {
        if (
          error instanceof Error
        ) {
          setRuntimeError(
            error.message
          );
        } else {
          setRuntimeError(
            "Unknown error"
          );
        }
      }
    };


  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>
            RF Gateway
          </h1>

          <p>
            Universal Radio Gateway Platform
          </p>
        </div>


        <div className="backend-status">
          <span
            className={
              health?.status === "ok"
                ? "status-dot online"
                : "status-dot offline"
            }
          />

          {health
            ? `Backend online · v${health.version}`
            : backendError
              ? `Backend error: ${backendError}`
              : "Connecting..."}
        </div>
      </header>


      <main className="dashboard">
        <section className="card">
          <h2>Sources</h2>
          <strong>0</strong>

          <p>
            Internet audio streams
          </p>
        </section>


        <section className="card">
          <h2>RF Devices</h2>

          <strong>
            {devicesLoading
              ? "--"
              : deviceCount}
          </strong>

          <p>
            MMDVM / SDR devices
          </p>
        </section>


        <section className="card">
          <h2>Routes</h2>

          <strong>
            {txActive
              ? 1
              : 0}
          </strong>

          <p>
            Active audio → RF routes
          </p>
        </section>


        <section className="card">
          <h2>Calibration</h2>
          <strong>--</strong>

          <p>
            BER / frequency offset
          </p>
        </section>


        <section className="rf-panel">
          <div className="panel-title">
            <div>
              <h2>
                RF Devices
              </h2>

              <p className="panel-description">
                Detected RF hardware
              </p>
            </div>


            <button
              type="button"
              disabled={
                devicesLoading ||
                txActive
              }
              onClick={
                () => {
                  void loadDevices();
                }
              }
            >
              {devicesLoading
                ? "SCANNING..."
                : "REFRESH"}
            </button>
          </div>


          {devicesError && (
            <div className="runtime-error">
              {devicesError}
            </div>
          )}


          {!devicesLoading &&
            !devicesError &&
            deviceCount === 0 && (
              <div className="protocol-disabled">
                No RF devices detected.
              </div>
            )}


          {devicesResponse &&
            devicesResponse.devices.length > 0 && (
              <div className="rf-device-grid">
                {devicesResponse.devices.map(
                  (device) => (
                    <RFDeviceCard
                      key={device.id}
                      device={device}

                      selected={
                        device.id ===
                        selectedDeviceId
                      }

                      onSelect={
                        txActive
                          ? undefined
                          : selectDevice
                      }
                    />
                  )
                )}
              </div>
            )}
        </section>


        <section className="rf-panel">
          <div className="panel-title">
            <div>
              <h2>
                RF Output
              </h2>

              <p className="panel-description">
                Select one RF protocol
              </p>
            </div>

            <span
              className={
                txActive
                  ? "runtime-badge tx-on"
                  : "runtime-badge"
              }
            >
              {activeProtocol
                ? `${activeProtocol.toUpperCase()}${
                    txActive
                      ? " · TX"
                      : ""
                  }`
                : "DISABLED"}
            </span>
          </div>


          <ProtocolSelector
            activeProtocol={
              activeProtocol
            }

            disabled={
              txActive
            }

            onToggle={
              toggleProtocol
            }
          />


          {activeProtocol === null && (
            <div className="protocol-disabled">
              RF output is disabled.
              <br />
              Select a protocol above
              to configure it.
            </div>
          )}


          {activeProtocol === "fm" && (
            <FMConfigForm
              value={fmConfig}
              onChange={setFmConfig}
            />
          )}


          {activeProtocol === "dmr" && (
            <DMRConfigForm
              value={dmrConfig}
              onChange={setDmrConfig}
            />
          )}


          {activeProtocol === "p25" && (
            <P25ConfigForm
              value={p25Config}
              onChange={setP25Config}
            />
          )}


          {activeProtocol === "tetra" && (
            <TETRAConfigForm
              value={tetraConfig}
              onChange={setTetraConfig}
            />
          )}


          {selectedDevice && (
            <div className="runtime-message">
              RF device:{" "}
              {getDeviceDisplayName(
                selectedDevice
              )}
              {" · "}
              {selectedDevice.backend}
              {" · "}
              {selectedDevice.driver}
            </div>
          )}


          {runtimeMessage && (
            <div className="runtime-message">
              {runtimeMessage}
            </div>
          )}


          {runtimeError && (
            <div className="runtime-error">
              {runtimeError}
            </div>
          )}


          <div className="buttons">
            <button
              className="start"

              disabled={
                !activeProtocol ||
                !selectedDevice ||
                txActive
              }

              onClick={
                handleStart
              }
            >
              START
            </button>


            <button
              disabled={
                !txActive
              }

              onClick={
                handleStop
              }
            >
              STOP
            </button>


            <button
              disabled={
                !activeProtocol ||
                !selectedDevice ||
                txActive
              }
            >
              CALIBRATE
            </button>
          </div>
        </section>


        <section className="telemetry">
          <h2>
            Live Telemetry
          </h2>


          <div>
            <span>TX</span>

            <strong
              className={
                txActive
                  ? "tx-value"
                  : ""
              }
            >
              {txActive
                ? "ON"
                : "OFF"}
            </strong>
          </div>


          <div>
            <span>
              Protocol
            </span>

            <strong>
              {activeProtocol
                ? activeProtocol.toUpperCase()
                : "--"}
            </strong>
          </div>


          <div>
            <span>
              RF Device
            </span>

            <strong>
              {selectedDevice
                ? getDeviceDisplayName(
                    selectedDevice
                  )
                : "--"}
            </strong>
          </div>


          <div>
            <span>BER</span>
            <strong>-- %</strong>
          </div>


          <div>
            <span>
              Frequency Error
            </span>

            <strong>
              -- Hz
            </strong>
          </div>


          <div>
            <span>
              TX Offset
            </span>

            <strong>
              -- Hz
            </strong>
          </div>


          <div>
            <span>
              Audio
            </span>

            <strong>
              -- dBFS
            </strong>
          </div>
        </section>
      </main>
    </div>
  );
}


export default App;
