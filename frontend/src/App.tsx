import {
  useEffect,
  useState,
} from "react";

import "./App.css";

import CalibrationPanel from "./components/CalibrationPanel";
import SourcesPanel from "./components/SourcesPanel";
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


type MMDVMProcessStatus = {
  running: boolean;
  ready: boolean;

  pid:
    number
    | null;

  udp_port: number;
};


type MMDVMStatus = {
  runtime_active: boolean;
  runtime_ready: boolean;

  protocol:
    Protocol
    | null;

  frequency_hz:
    number
    | null;

  channel_frequency_hz:
    number
    | null;

  sdr_tx_center_frequency_hz:
    number
    | null;

  sdr_rx_center_frequency_hz:
    number
    | null;

  digital_if_hz:
    number
    | null;

  sample_rate_hz:
    number
    | null;

  actual_tx_rate_hz:
    number
    | null;

  actual_rx_rate_hz:
    number
    | null;

  modem_mode:
    string
    | null;

  rf_tx_active: boolean;
  tx_stream_active: boolean;

  hardware_open: boolean;
  iq_streams_active: boolean;

  hardware_version:
    string
    | null;

  driver_name:
    string
    | null;

  mmdvm_iq:
    MMDVMProcessStatus;

  mmdvm_host:
    MMDVMProcessStatus;

  runtime_config: string;

  last_error:
    string
    | null;
};


type RFStatus = {
  tx: boolean;

  runtime_active: boolean;
  rf_tx_active: boolean;
  tx_stream_active: boolean;

  protocol:
    Protocol
    | null;

  device_id?:
    string
    | null;

  config: unknown;

  mmdvm?:
    MMDVMStatus
    | null;

  error?:
    string
    | null;
};


type SavedFMConfig = {
  frequency_hz: number;
  channel_spacing_khz: number;
  deviation_khz: number;

  tx_ctcss_hz:
    number
    | null;

  rx_ctcss_hz:
    number
    | null;

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
    fm?:
      SavedFMConfig;

    dmr?:
      SavedDMRConfig;

    p25?:
      SavedP25Config;

    tetra?:
      SavedTETRAConfig;
  };
};


const API_BASE_URL =
  `${window.location.protocol}//${window.location.hostname}:8000`;


const STORAGE_KEYS = {
  activeProtocol:
    "rf-gateway.activeProtocol",

  selectedDeviceId:
    "rf-gateway.selectedDeviceId",

  fmConfig:
    "rf-gateway.fmConfig",

  dmrConfig:
    "rf-gateway.dmrConfig",

  p25Config:
    "rf-gateway.p25Config",

  tetraConfig:
    "rf-gateway.tetraConfig",
};


const DEFAULT_FM_CONFIG:
  FMConfig = {
    frequency:
      "145.500000",

    channelSpacing:
      "12.5",

    deviation:
      "2.5",

    txCtcss:
      "",

    rxCtcss:
      "",

    preEmphasis:
      "on",
  };


const DEFAULT_DMR_CONFIG:
  DMRConfig = {
    frequency:
      "438.800000",

    colorCode:
      "1",

    timeslot:
      "2",

    talkgroup:
      "260",

    radioId:
      "2601292",
  };


const DEFAULT_P25_CONFIG:
  P25Config = {
    frequency:
      "145.500000",

    nac:
      "293",

    talkgroup:
      "260",

    radioId:
      "2601292",

    modulation:
      "c4fm",
  };


const DEFAULT_TETRA_CONFIG:
  TETRAConfig = {
    frequency:
      "430.000000",

    mode:
      "dmo",

    mcc:
      "901",

    mnc:
      "9999",

    colorCode:
      "1",

    gssi:
      "1",
  };


function loadFromStorage<T>(
  key: string,
  defaultValue: T
): T {
  try {
    const storedValue =
      localStorage.getItem(
        key
      );

    if (
      !storedValue
    ) {
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
  Protocol
  | null {
  const storedValue =
    localStorage.getItem(
      STORAGE_KEYS
        .activeProtocol
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
  string
  | null {
  return (
    localStorage.getItem(
      STORAGE_KEYS
        .selectedDeviceId
    )
  );
}


function frequencyToHz(
  frequency: string
): number {
  const mhz =
    Number(
      frequency
    );

  if (
    !Number.isFinite(
      mhz
    ) ||
    mhz <= 0
  ) {
    throw new Error(
      "Invalid frequency"
    );
  }

  return Math.round(
    mhz *
    1_000_000
  );
}


function hzToMHzString(
  frequencyHz: number
): string {
  return (
    frequencyHz /
    1_000_000
  ).toFixed(
    6
  );
}


function formatFrequency(
  frequencyHz:
    number
    | null
    | undefined
): string {
  if (
    frequencyHz ===
      null ||
    frequencyHz ===
      undefined
  ) {
    return "--";
  }

  return (
    frequencyHz /
    1_000_000
  ).toFixed(
    6
  ) + " MHz";
}


function formatSignedFrequency(
  frequencyHz:
    number
    | null
    | undefined
): string {
  if (
    frequencyHz ===
      null ||
    frequencyHz ===
      undefined
  ) {
    return "--";
  }

  const sign =
    frequencyHz > 0
      ? "+"
      : "";

  if (
    Math.abs(
      frequencyHz
    ) >=
    1000
  ) {
    return (
      sign +
      (
        frequencyHz /
        1000
      ).toFixed(
        3
      ) +
      " kHz"
    );
  }

  return (
    sign +
    frequencyHz
      .toFixed(
        0
      ) +
    " Hz"
  );
}


function formatSampleRate(
  sampleRate:
    number
    | null
    | undefined
): string {
  if (
    sampleRate ===
      null ||
    sampleRate ===
      undefined
  ) {
    return "--";
  }

  return (
    sampleRate /
    1000
  ).toFixed(
    0
  ) + " kS/s";
}


function optionalNumberToString(
  value:
    number
    | null
    | undefined
): string {
  if (
    value === null ||
    value === undefined
  ) {
    return "";
  }

  return String(
    value
  );
}


function requiredInteger(
  value: string,
  fieldName: string
): number {
  const parsed =
    Number(
      value
    );

  if (
    !Number.isInteger(
      parsed
    )
  ) {
    throw new Error(
      `${fieldName} must be an integer`
    );
  }

  return parsed;
}


function optionalNumber(
  value: string
):
  number
  | null {
  const trimmed =
    value.trim();

  if (
    trimmed === ""
  ) {
    return null;
  }

  const parsed =
    Number(
      trimmed
    );

  if (
    !Number.isFinite(
      parsed
    )
  ) {
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
    device.driver
      .toLowerCase() ===
    "sx"
  ) {
    return "SXceiver";
  }

  if (
    device.label
      .trim()
      .length >
    0
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
    useState<
      Health
      | null
    >(
      null
    );


  const [
    backendError,
    setBackendError,
  ] =
    useState<
      string
      | null
    >(
      null
    );


  const [
    activeProtocol,
    setActiveProtocol,
  ] =
    useState<
      Protocol
      | null
    >(
      () =>
        loadProtocolFromStorage()
    );


  const [
    selectedDeviceId,
    setSelectedDeviceId,
  ] =
    useState<
      string
      | null
    >(
      () =>
        loadSelectedDeviceId()
    );


  const [
    devicesResponse,
    setDevicesResponse,
  ] =
    useState<
      RFDevicesResponse
      | null
    >(
      null
    );


  const [
    devicesLoading,
    setDevicesLoading,
  ] =
    useState(
      false
    );


  const [
    devicesError,
    setDevicesError,
  ] =
    useState<
      string
      | null
    >(
      null
    );


  const [
    modeConfigsLoaded,
    setModeConfigsLoaded,
  ] =
    useState(
      false
    );


  const [
    runtimeActive,
    setRuntimeActive,
  ] =
    useState(
      false
    );


  const [
    rfTxActive,
    setRfTxActive,
  ] =
    useState(
      false
    );


  const [
    mmdvmStatus,
    setMmdvmStatus,
  ] =
    useState<
      MMDVMStatus
      | null
    >(
      null
    );


  const [
    runtimeMessage,
    setRuntimeMessage,
  ] =
    useState<
      string
      | null
    >(
      null
    );


  const [
    runtimeError,
    setRuntimeError,
  ] =
    useState<
      string
      | null
    >(
      null
    );


  const [
    calibrationOpen,
    setCalibrationOpen,
  ] =
    useState(
      false
    );


  const [
    sourceCount,
    setSourceCount,
  ] =
    useState(
      0
    );


  const [
    fmConfig,
    setFmConfig,
  ] =
    useState<FMConfig>(
      () =>
        loadFromStorage(
          STORAGE_KEYS
            .fmConfig,

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
          STORAGE_KEYS
            .dmrConfig,

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
          STORAGE_KEYS
            .p25Config,

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
          STORAGE_KEYS
            .tetraConfig,

          DEFAULT_TETRA_CONFIG
        )
    );


  const selectedDevice =
    devicesResponse
      ?.devices
      .find(
        (
          device
        ) =>
          device.id ===
          selectedDeviceId
      ) ?? null;


  const deviceCount =
    devicesResponse
      ?.device_count ??
    0;


  const loadDevices =
    async () => {
      setDevicesLoading(
        true
      );

      setDevicesError(
        null
      );

      try {
        const response =
          await fetch(
            `${API_BASE_URL}/api/devices`
          );

        if (
          !response.ok
        ) {
          throw new Error(
            `HTTP ${response.status}`
          );
        }

        const data =
          (
            await response
              .json()
          ) as RFDevicesResponse;

        setDevicesResponse(
          data
        );

        if (
          data.error
        ) {
          setDevicesError(
            data.error
          );
        }

      } catch (
        error
      ) {
        if (
          error instanceof
          Error
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
        setDevicesLoading(
          false
        );
      }
    };


  const loadSavedModeConfigs =
    async () => {
      try {
        const response =
          await fetch(
            `${API_BASE_URL}/api/config/modes`
          );

        if (
          !response.ok
        ) {
          throw new Error(
            `HTTP ${response.status}`
          );
        }

        const data =
          (
            await response
              .json()
          ) as SavedModesResponse;


        if (
          data.modes.fm
        ) {
          const saved =
            data.modes.fm;

          setFmConfig({
            frequency:
              hzToMHzString(
                saved
                  .frequency_hz
              ),

            channelSpacing:
              saved
                .channel_spacing_khz ===
              25
                ? "25"
                : "12.5",

            deviation:
              saved
                .deviation_khz ===
              5
                ? "5"
                : "2.5",

            txCtcss:
              optionalNumberToString(
                saved
                  .tx_ctcss_hz
              ),

            rxCtcss:
              optionalNumberToString(
                saved
                  .rx_ctcss_hz
              ),

            preEmphasis:
              saved
                .pre_emphasis
                ? "on"
                : "off",
          });
        }


        if (
          data.modes.dmr
        ) {
          const saved =
            data.modes.dmr;

          setDmrConfig({
            frequency:
              hzToMHzString(
                saved
                  .frequency_hz
              ),

            colorCode:
              String(
                saved
                  .color_code
              ),

            timeslot:
              saved
                .timeslot ===
              1
                ? "1"
                : "2",

            talkgroup:
              String(
                saved
                  .talkgroup
              ),

            radioId:
              String(
                saved
                  .radio_id
              ),
          });
        }


        if (
          data.modes.p25
        ) {
          const saved =
            data.modes.p25;

          setP25Config({
            frequency:
              hzToMHzString(
                saved
                  .frequency_hz
              ),

            nac:
              saved.nac,

            talkgroup:
              String(
                saved
                  .talkgroup
              ),

            radioId:
              String(
                saved
                  .radio_id
              ),

            modulation:
              saved
                .modulation ===
              "cqpsk"
                ? "cqpsk"
                : "c4fm",
          });
        }


        if (
          data.modes.tetra
        ) {
          const saved =
            data.modes.tetra;

          setTetraConfig({
            frequency:
              hzToMHzString(
                saved
                  .frequency_hz
              ),

            mode:
              saved.mode ===
              "tmo"
                ? "tmo"
                : "dmo",

            mcc:
              saved.mcc,

            mnc:
              saved.mnc,

            colorCode:
              String(
                saved
                  .color_code
              ),

            gssi:
              String(
                saved
                  .gssi
              ),
          });
        }

      } catch (
        error
      ) {
        console.error(
          "Unable to load saved mode configurations:",
          error
        );

      } finally {
        setModeConfigsLoaded(
          true
        );
      }
    };


  const applyRFStatus =
    (
      data: RFStatus
    ) => {
      setRuntimeActive(
        Boolean(
          data
            .runtime_active
        )
      );

      setRfTxActive(
        Boolean(
          data
            .rf_tx_active
        )
      );

      setMmdvmStatus(
        data.mmdvm ??
        null
      );


      if (
        data.protocol
      ) {
        setActiveProtocol(
          data.protocol
        );
      }


      if (
        data.device_id
      ) {
        setSelectedDeviceId(
          data.device_id
        );
      }
    };


  const loadRFStatus =
    async () => {
      try {
        const response =
          await fetch(
            `${API_BASE_URL}/api/rf/status`,
            {
              cache:
                "no-store",
            }
          );

        if (
          !response.ok
        ) {
          return;
        }

        const data =
          (
            await response
              .json()
          ) as RFStatus;

        applyRFStatus(
          data
        );

      } catch {
        // Backend health handles connectivity.
      }
    };


  const saveModeConfig =
    async (
      payload: object
    ) => {
      try {
        const response =
          await fetch(
            `${API_BASE_URL}/api/config/modes`,
            {
              method:
                "PUT",

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

        if (
          !response.ok
        ) {
          const data =
            await response
              .json();

          throw new Error(
            typeof data.detail ===
              "string"
              ? data.detail
              : JSON.stringify(
                  data.detail
                )
          );
        }

      } catch (
        error
      ) {
        console.error(
          "Unable to save mode configuration:",
          error
        );
      }
    };


  useEffect(
    () => {
      fetch(
        `${API_BASE_URL}/api/health`
      )
        .then(
          (
            response
          ) => {
            if (
              !response.ok
            ) {
              throw new Error(
                `HTTP ${response.status}`
              );
            }

            return (
              response.json()
            );
          }
        )
        .then(
          (
            data:
              Health
          ) => {
            setHealth(
              data
            );

            setBackendError(
              null
            );
          }
        )
        .catch(
          (
            error:
              Error
          ) => {
            setBackendError(
              error.message
            );
          }
        );


      void loadSavedModeConfigs();
      void loadDevices();
      void loadRFStatus();


      const statusTimer =
        window.setInterval(
          () => {
            void loadRFStatus();
          },
          750
        );


      return () => {
        window.clearInterval(
          statusTimer
        );
      };
    },
    []
  );


  useEffect(
    () => {
      if (
        !devicesResponse
      ) {
        return;
      }


      const usableDevices =
        devicesResponse
          .devices
          .filter(
            (
              device
            ) =>
              device.available &&
              device.probe_ok
          );


      if (
        selectedDeviceId &&
        usableDevices
          .some(
            (
              device
            ) =>
              device.id ===
              selectedDeviceId
          )
      ) {
        return;
      }


      if (
        usableDevices
          .length ===
        1
      ) {
        setSelectedDeviceId(
          usableDevices[0].id
        );

        return;
      }


      if (
        selectedDeviceId !==
        null
      ) {
        setSelectedDeviceId(
          null
        );
      }
    },
    [
      devicesResponse,
      selectedDeviceId,
    ]
  );


  useEffect(
    () => {
      if (
        activeProtocol
      ) {
        localStorage
          .setItem(
            STORAGE_KEYS
              .activeProtocol,

            activeProtocol
          );
      } else {
        localStorage
          .removeItem(
            STORAGE_KEYS
              .activeProtocol
          );
      }
    },
    [
      activeProtocol,
    ]
  );


  useEffect(
    () => {
      if (
        selectedDeviceId
      ) {
        localStorage
          .setItem(
            STORAGE_KEYS
              .selectedDeviceId,

            selectedDeviceId
          );
      } else {
        localStorage
          .removeItem(
            STORAGE_KEYS
              .selectedDeviceId
          );
      }
    },
    [
      selectedDeviceId,
    ]
  );


  useEffect(
    () => {
      localStorage
        .setItem(
          STORAGE_KEYS
            .fmConfig,

          JSON.stringify(
            fmConfig
          )
        );
    },
    [
      fmConfig,
    ]
  );


  useEffect(
    () => {
      localStorage
        .setItem(
          STORAGE_KEYS
            .dmrConfig,

          JSON.stringify(
            dmrConfig
          )
        );
    },
    [
      dmrConfig,
    ]
  );


  useEffect(
    () => {
      localStorage
        .setItem(
          STORAGE_KEYS
            .p25Config,

          JSON.stringify(
            p25Config
          )
        );
    },
    [
      p25Config,
    ]
  );


  useEffect(
    () => {
      localStorage
        .setItem(
          STORAGE_KEYS
            .tetraConfig,

          JSON.stringify(
            tetraConfig
          )
        );
    },
    [
      tetraConfig,
    ]
  );


  useEffect(
    () => {
      if (
        !modeConfigsLoaded
      ) {
        return;
      }

      const timer =
        window.setTimeout(
          () => {
            try {
              void saveModeConfig({
                protocol:
                  "fm",

                frequency_hz:
                  frequencyToHz(
                    fmConfig
                      .frequency
                  ),

                channel_spacing_khz:
                  Number(
                    fmConfig
                      .channelSpacing
                  ),

                deviation_khz:
                  Number(
                    fmConfig
                      .deviation
                  ),

                tx_ctcss_hz:
                  optionalNumber(
                    fmConfig
                      .txCtcss
                  ),

                rx_ctcss_hz:
                  optionalNumber(
                    fmConfig
                      .rxCtcss
                  ),

                pre_emphasis:
                  fmConfig
                    .preEmphasis ===
                  "on",
              });

            } catch {
              // Incomplete input.
            }
          },
          700
        );

      return () => {
        window.clearTimeout(
          timer
        );
      };
    },
    [
      fmConfig,
      modeConfigsLoaded,
    ]
  );


  useEffect(
    () => {
      if (
        !modeConfigsLoaded
      ) {
        return;
      }

      const timer =
        window.setTimeout(
          () => {
            try {
              void saveModeConfig({
                protocol:
                  "dmr",

                frequency_hz:
                  frequencyToHz(
                    dmrConfig
                      .frequency
                  ),

                color_code:
                  requiredInteger(
                    dmrConfig
                      .colorCode,

                    "Color Code"
                  ),

                timeslot:
                  requiredInteger(
                    dmrConfig
                      .timeslot,

                    "Timeslot"
                  ),

                talkgroup:
                  requiredInteger(
                    dmrConfig
                      .talkgroup,

                    "Talkgroup"
                  ),

                radio_id:
                  requiredInteger(
                    dmrConfig
                      .radioId,

                    "Radio ID"
                  ),
              });

            } catch {
              // Incomplete input.
            }
          },
          700
        );

      return () => {
        window.clearTimeout(
          timer
        );
      };
    },
    [
      dmrConfig,
      modeConfigsLoaded,
    ]
  );


  useEffect(
    () => {
      if (
        !modeConfigsLoaded
      ) {
        return;
      }

      const timer =
        window.setTimeout(
          () => {
            try {
              void saveModeConfig({
                protocol:
                  "p25",

                frequency_hz:
                  frequencyToHz(
                    p25Config
                      .frequency
                  ),

                nac:
                  p25Config
                    .nac
                    .trim(),

                talkgroup:
                  requiredInteger(
                    p25Config
                      .talkgroup,

                    "Talkgroup"
                  ),

                radio_id:
                  requiredInteger(
                    p25Config
                      .radioId,

                    "Radio ID"
                  ),

                modulation:
                  p25Config
                    .modulation,
              });

            } catch {
              // Incomplete input.
            }
          },
          700
        );

      return () => {
        window.clearTimeout(
          timer
        );
      };
    },
    [
      p25Config,
      modeConfigsLoaded,
    ]
  );


  useEffect(
    () => {
      if (
        !modeConfigsLoaded
      ) {
        return;
      }

      const timer =
        window.setTimeout(
          () => {
            try {
              void saveModeConfig({
                protocol:
                  "tetra",

                frequency_hz:
                  frequencyToHz(
                    tetraConfig
                      .frequency
                  ),

                mode:
                  tetraConfig
                    .mode,

                mcc:
                  tetraConfig
                    .mcc
                    .trim(),

                mnc:
                  tetraConfig
                    .mnc
                    .trim(),

                color_code:
                  requiredInteger(
                    tetraConfig
                      .colorCode,

                    "Color Code"
                  ),

                gssi:
                  requiredInteger(
                    tetraConfig
                      .gssi,

                    "GSSI"
                  ),
              });

            } catch {
              // Incomplete input.
            }
          },
          700
        );

      return () => {
        window.clearTimeout(
          timer
        );
      };
    },
    [
      tetraConfig,
      modeConfigsLoaded,
    ]
  );


  const toggleProtocol =
    (
      protocol:
        Protocol
    ) => {
      if (
        runtimeActive
      ) {
        return;
      }

      setRuntimeMessage(
        null
      );

      setRuntimeError(
        null
      );

      setActiveProtocol(
        (
          current
        ) =>
          current ===
          protocol
            ? null
            : protocol
      );
    };


  const selectDevice =
    (
      device:
        RFDevice
    ) => {
      if (
        runtimeActive
      ) {
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

      setRuntimeMessage(
        null
      );

      setRuntimeError(
        null
      );
    };


  const buildStartPayload =
    () => {
      if (
        !activeProtocol
      ) {
        throw new Error(
          "Select an RF protocol first"
        );
      }

      if (
        !selectedDevice
      ) {
        throw new Error(
          "Select an RF device first"
        );
      }


      if (
        activeProtocol ===
        "fm"
      ) {
        return {
          protocol:
            "fm",

          device_id:
            selectedDevice.id,

          frequency_hz:
            frequencyToHz(
              fmConfig.frequency
            ),

          channel_spacing_khz:
            Number(
              fmConfig
                .channelSpacing
            ),

          deviation_khz:
            Number(
              fmConfig
                .deviation
            ),

          tx_ctcss_hz:
            optionalNumber(
              fmConfig
                .txCtcss
            ),

          rx_ctcss_hz:
            optionalNumber(
              fmConfig
                .rxCtcss
            ),

          pre_emphasis:
            fmConfig
              .preEmphasis ===
            "on",
        };
      }


      if (
        activeProtocol ===
        "dmr"
      ) {
        return {
          protocol:
            "dmr",

          device_id:
            selectedDevice.id,

          frequency_hz:
            frequencyToHz(
              dmrConfig
                .frequency
            ),

          color_code:
            requiredInteger(
              dmrConfig
                .colorCode,

              "Color Code"
            ),

          timeslot:
            requiredInteger(
              dmrConfig
                .timeslot,

              "Timeslot"
            ),

          talkgroup:
            requiredInteger(
              dmrConfig
                .talkgroup,

              "Talkgroup"
            ),

          radio_id:
            requiredInteger(
              dmrConfig
                .radioId,

              "Radio ID"
            ),
        };
      }


      if (
        activeProtocol ===
        "p25"
      ) {
        return {
          protocol:
            "p25",

          device_id:
            selectedDevice.id,

          frequency_hz:
            frequencyToHz(
              p25Config
                .frequency
            ),

          nac:
            p25Config
              .nac
              .trim(),

          talkgroup:
            requiredInteger(
              p25Config
                .talkgroup,

              "Talkgroup"
            ),

          radio_id:
            requiredInteger(
              p25Config
                .radioId,

              "Radio ID"
            ),

          modulation:
            p25Config
              .modulation,
        };
      }


      return {
        protocol:
          "tetra",

        device_id:
          selectedDevice.id,

        frequency_hz:
          frequencyToHz(
            tetraConfig
              .frequency
          ),

        mode:
          tetraConfig
            .mode,

        mcc:
          tetraConfig
            .mcc
            .trim(),

        mnc:
          tetraConfig
            .mnc
            .trim(),

        color_code:
          requiredInteger(
            tetraConfig
              .colorCode,

            "Color Code"
          ),

        gssi:
          requiredInteger(
            tetraConfig
              .gssi,

            "GSSI"
          ),
      };
    };


  const handleStart =
    async () => {
      try {
        setRuntimeMessage(
          null
        );

        setRuntimeError(
          null
        );


        if (
          !selectedDevice
        ) {
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
              method:
                "POST",

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
          await response
            .json();


        if (
          !response.ok
        ) {
          throw new Error(
            typeof data.detail ===
              "string"
              ? data.detail
              : JSON.stringify(
                  data.detail
                )
          );
        }


        if (
          data.error
        ) {
          throw new Error(
            data.error
          );
        }


        applyRFStatus(
          data as RFStatus
        );


        setRuntimeMessage(
          `${activeProtocol?.toUpperCase()} runtime started on ${getDeviceDisplayName(selectedDevice)}`
        );

      } catch (
        error
      ) {
        if (
          error instanceof
          Error
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
        setCalibrationOpen(
          false
        );

        setRuntimeMessage(
          null
        );

        setRuntimeError(
          null
        );


        const response =
          await fetch(
            `${API_BASE_URL}/api/rf/stop`,
            {
              method:
                "POST",
            }
          );


        const data =
          await response
            .json();


        if (
          !response.ok
        ) {
          throw new Error(
            `HTTP ${response.status}`
          );
        }


        if (
          data.error
        ) {
          throw new Error(
            data.error
          );
        }


        applyRFStatus(
          data as RFStatus
        );


        setRuntimeMessage(
          "RF runtime stopped"
        );

      } catch (
        error
      ) {
        if (
          error instanceof
          Error
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


  const runtimeLabel =
    activeProtocol
      ? (
          rfTxActive
            ? `${activeProtocol.toUpperCase()} · TX`
            : runtimeActive
              ? `${activeProtocol.toUpperCase()} · ACTIVE`
              : activeProtocol.toUpperCase()
        )
      : "DISABLED";


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
              health?.status ===
              "ok"
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
          <h2>
            Sources
          </h2>

          <strong>
            {sourceCount}
          </strong>

          <p>
            Internet audio sources
          </p>
        </section>


        <section className="card">
          <h2>
            RF Devices
          </h2>

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
          <h2>
            Routes
          </h2>

          <strong>
            {runtimeActive
              ? 1
              : 0}
          </strong>

          <p>
            Active RF runtime
          </p>
        </section>


        <section className="card">
          <h2>
            Calibration
          </h2>

          <strong>
            {runtimeActive
              ? "READY"
              : "--"}
          </strong>

          <p>
            Controlled RF diagnostics
          </p>
        </section>


        <SourcesPanel
          onCountChange={
            setSourceCount
          }
        />


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
                runtimeActive
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
            deviceCount ===
              0 && (
              <div className="protocol-disabled">
                No RF devices detected.
              </div>
            )}


          {devicesResponse &&
            devicesResponse
              .devices
              .length >
              0 && (
              <div className="rf-device-grid">
                {devicesResponse
                  .devices
                  .map(
                    (
                      device
                    ) => (
                      <RFDeviceCard
                        key={
                          device.id
                        }

                        device={
                          device
                        }

                        selected={
                          device.id ===
                          selectedDeviceId
                        }

                        onSelect={
                          runtimeActive
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
                runtimeActive
                  ? "runtime-badge tx-on"
                  : "runtime-badge"
              }
            >
              {runtimeLabel}
            </span>
          </div>


          <ProtocolSelector
            activeProtocol={
              activeProtocol
            }

            disabled={
              runtimeActive
            }

            onToggle={
              toggleProtocol
            }
          />


          {activeProtocol ===
            null && (
            <div className="protocol-disabled">
              RF output is disabled.
              <br />
              Select a protocol above
              to configure it.
            </div>
          )}


          {activeProtocol ===
            "fm" && (
            <FMConfigForm
              value={
                fmConfig
              }

              onChange={
                setFmConfig
              }
            />
          )}


          {activeProtocol ===
            "dmr" && (
            <DMRConfigForm
              value={
                dmrConfig
              }

              onChange={
                setDmrConfig
              }
            />
          )}


          {activeProtocol ===
            "p25" && (
            <P25ConfigForm
              value={
                p25Config
              }

              onChange={
                setP25Config
              }
            />
          )}


          {activeProtocol ===
            "tetra" && (
            <TETRAConfigForm
              value={
                tetraConfig
              }

              onChange={
                setTetraConfig
              }
            />
          )}


          {selectedDevice && (
            <div className="runtime-message">
              RF device:{" "}
              {getDeviceDisplayName(
                selectedDevice
              )}
              {" · "}
              {selectedDevice
                .backend}
              {" · "}
              {selectedDevice
                .driver}
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
                runtimeActive
              }

              onClick={
                handleStart
              }
            >
              START
            </button>


            <button
              disabled={
                !runtimeActive
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
                !runtimeActive ||
                !mmdvmStatus
                  ?.runtime_ready ||
                rfTxActive
              }

              onClick={
                () => {
                  setCalibrationOpen(
                    true
                  );
                }
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
            <span>
              Runtime
            </span>

            <strong
              className={
                runtimeActive
                  ? "tx-value"
                  : ""
              }
            >
              {runtimeActive
                ? "ACTIVE"
                : "STOPPED"}
            </strong>
          </div>


          <div>
            <span>
              RF TX
            </span>

            <strong
              className={
                rfTxActive
                  ? "tx-value"
                  : ""
              }
            >
              {rfTxActive
                ? "ON"
                : "OFF"}
            </strong>
          </div>


          <div>
            <span>
              Modem Mode
            </span>

            <strong>
              {mmdvmStatus
                ?.modem_mode
                ?.toUpperCase()
                ?? "--"}
            </strong>
          </div>


          <div>
            <span>
              Protocol
            </span>

            <strong>
              {activeProtocol
                ? activeProtocol
                    .toUpperCase()
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
            <span>
              Channel
            </span>

            <strong>
              {formatFrequency(
                mmdvmStatus
                  ?.channel_frequency_hz
              )}
            </strong>
          </div>


          <div>
            <span>
              SDR Center
            </span>

            <strong>
              {formatFrequency(
                mmdvmStatus
                  ?.sdr_tx_center_frequency_hz
              )}
            </strong>
          </div>


          <div>
            <span>
              Digital IF
            </span>

            <strong>
              {formatSignedFrequency(
                mmdvmStatus
                  ?.digital_if_hz
              )}
            </strong>
          </div>


          <div>
            <span>
              Sample Rate
            </span>

            <strong>
              {formatSampleRate(
                mmdvmStatus
                  ?.sample_rate_hz
              )}
            </strong>
          </div>


          <div>
            <span>
              IQ Streams
            </span>

            <strong>
              {mmdvmStatus
                ?.iq_streams_active
                ? "ACTIVE"
                : "OFF"}
            </strong>
          </div>


          <div>
            <span>
              MMDVM-IQ
            </span>

            <strong>
              {mmdvmStatus
                ?.mmdvm_iq
                ?.running
                ? (
                    mmdvmStatus
                      .mmdvm_iq
                      .ready
                      ? "READY"
                      : "STARTING"
                  )
                : "STOPPED"}
            </strong>
          </div>


          <div>
            <span>
              MMDVM-Host
            </span>

            <strong>
              {mmdvmStatus
                ?.mmdvm_host
                ?.running
                ? (
                    mmdvmStatus
                      .mmdvm_host
                      .ready
                      ? "READY"
                      : "STARTING"
                  )
                : "STOPPED"}
            </strong>
          </div>


          <div>
            <span>
              BER
            </span>

            <strong>
              N/A
            </strong>
          </div>


          <div>
            <span>
              Frequency Error
            </span>

            <strong>
              N/A
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
              N/A
            </strong>
          </div>
        </section>
      </main>


      <CalibrationPanel
        open={
          calibrationOpen
        }

        runtimeActive={
          runtimeActive
        }

        runtimeReady={
          Boolean(
            mmdvmStatus
              ?.runtime_ready
          )
        }

        rfTxActive={
          rfTxActive
        }

        protocol={
          activeProtocol
        }

        channelFrequencyHz={
          mmdvmStatus
            ?.channel_frequency_hz
        }

        sdrCenterFrequencyHz={
          mmdvmStatus
            ?.sdr_tx_center_frequency_hz
        }

        digitalIfHz={
          mmdvmStatus
            ?.digital_if_hz
        }

        onClose={
          () => {
            setCalibrationOpen(
              false
            );
          }
        }
      />
    </div>
  );
}


export default App;