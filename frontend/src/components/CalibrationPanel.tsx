import {
  useEffect,
  useState,
} from "react";

import "./CalibrationPanel.css";


type CalibrationPanelProps = {
  open: boolean;

  runtimeActive: boolean;
  runtimeReady: boolean;
  rfTxActive: boolean;

  protocol: string | null;

  channelFrequencyHz:
    number
    | null
    | undefined;

  sdrCenterFrequencyHz:
    number
    | null
    | undefined;

  digitalIfHz:
    number
    | null
    | undefined;

  onClose: () => void;
};


type MMDVMStatus = {
  runtime_active: boolean;
  runtime_ready: boolean;

  modem_mode:
    string
    | null;

  rf_tx_active: boolean;
};


type CWCommandResponse = {
  accepted: boolean;

  text: string;

  mqtt_topic: string;
  command: string;

  runtime_active: boolean;

  protocol:
    string
    | null;

  frequency_hz:
    number
    | null;
};


type TestState =
  | "idle"
  | "sending"
  | "waiting"
  | "tx"
  | "success"
  | "warning"
  | "error";


const API_BASE_URL =
  `${window.location.protocol}//${window.location.hostname}:8000`;


function formatFrequency(
  frequencyHz:
    number
    | null
    | undefined
): string {
  if (
    frequencyHz === null ||
    frequencyHz === undefined
  ) {
    return "--";
  }

  return (
    frequencyHz /
    1_000_000
  ).toFixed(6) + " MHz";
}


function formatSignedFrequency(
  frequencyHz:
    number
    | null
    | undefined
): string {
  if (
    frequencyHz === null ||
    frequencyHz === undefined
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
    ) >= 1000
  ) {
    return (
      sign +
      (
        frequencyHz /
        1000
      ).toFixed(3) +
      " kHz"
    );
  }

  return (
    sign +
    frequencyHz.toFixed(0) +
    " Hz"
  );
}


function sleep(
  milliseconds: number
): Promise<void> {
  return new Promise(
    (resolve) => {
      window.setTimeout(
        resolve,
        milliseconds
      );
    }
  );
}


async function getMMDVMStatus():
  Promise<MMDVMStatus> {
  const response =
    await fetch(
      `${API_BASE_URL}/api/mmdvm/status`,
      {
        cache: "no-store",
      }
    );

  if (
    !response.ok
  ) {
    throw new Error(
      `Unable to read MMDVM status: HTTP ${response.status}`
    );
  }

  return (
    await response.json()
  ) as MMDVMStatus;
}


function CalibrationPanel(
  props: CalibrationPanelProps
) {
  const {
    open,

    runtimeActive,
    runtimeReady,
    rfTxActive,

    protocol,

    channelFrequencyHz,
    sdrCenterFrequencyHz,
    digitalIfHz,

    onClose,
  } = props;


  const [
    cwText,
    setCwText,
  ] =
    useState(
      "SP5OPS"
    );


  const [
    testState,
    setTestState,
  ] =
    useState<TestState>(
      "idle"
    );


  const [
    statusMessage,
    setStatusMessage,
  ] =
    useState(
      "Ready for controlled CW transmission test."
    );


  const [
    lastDurationMs,
    setLastDurationMs,
  ] =
    useState<
      number
      | null
    >(
      null
    );


  const [
    lastCommand,
    setLastCommand,
  ] =
    useState<
      string
      | null
    >(
      null
    );


  const [
    lastTestTime,
    setLastTestTime,
  ] =
    useState<
      Date
      | null
    >(
      null
    );


  const testBusy =
    testState === "sending" ||
    testState === "waiting" ||
    testState === "tx";


  useEffect(
    () => {
      if (
        !runtimeActive &&
        open
      ) {
        setTestState(
          "idle"
        );

        setStatusMessage(
          "MMDVM runtime is stopped."
        );
      }
    },
    [
      runtimeActive,
      open,
    ]
  );


  const observeTxCycle =
    async () => {
      const deadline =
        performance.now()
        + 12_000;

      let txObserved =
        false;

      let txStart:
        number
        | null =
        null;


      setTestState(
        "waiting"
      );

      setStatusMessage(
        "Command accepted. Waiting for RF TX..."
      );


      while (
        performance.now()
        < deadline
      ) {
        const status =
          await getMMDVMStatus();


        if (
          !status.runtime_active
        ) {
          throw new Error(
            "MMDVM runtime stopped during test."
          );
        }


        if (
          status.rf_tx_active &&
          !txObserved
        ) {
          txObserved =
            true;

          txStart =
            performance.now();

          setTestState(
            "tx"
          );

          setStatusMessage(
            "CW / Morse transmission is active."
          );
        }


        if (
          txObserved &&
          !status.rf_tx_active
        ) {
          const txEnd =
            performance.now();

          const duration =
            txStart !== null
              ? txEnd - txStart
              : null;


          setLastDurationMs(
            duration
          );

          setLastTestTime(
            new Date()
          );

          setTestState(
            "success"
          );

          setStatusMessage(
            "CW test completed. RF TX ON → OFF cycle observed."
          );

          return;
        }


        await sleep(
          100
        );
      }


      setLastTestTime(
        new Date()
      );


      if (
        txObserved
      ) {
        setTestState(
          "warning"
        );

        setStatusMessage(
          "RF TX started, but TX OFF was not observed before timeout."
        );

      } else {
        setTestState(
          "warning"
        );

        setStatusMessage(
          "Command was accepted, but no RF TX cycle was observed."
        );
      }
    };


  const sendCWTest =
    async () => {
      try {
        if (
          !runtimeActive
        ) {
          throw new Error(
            "Start the RF runtime before running the test."
          );
        }


        if (
          !runtimeReady
        ) {
          throw new Error(
            "MMDVM runtime is not ready."
          );
        }


        if (
          rfTxActive
        ) {
          throw new Error(
            "RF transmitter is already active."
          );
        }


        const normalizedText =
          cwText
            .trim()
            .toUpperCase();


        if (
          normalizedText.length === 0
        ) {
          throw new Error(
            "CW text cannot be empty."
          );
        }


        setTestState(
          "sending"
        );

        setStatusMessage(
          "Sending CW command to MMDVM-Host..."
        );

        setLastDurationMs(
          null
        );


        const response =
          await fetch(
            `${API_BASE_URL}/api/calibration/cw-id`,
            {
              method: "POST",

              headers: {
                "Content-Type":
                  "application/json",
              },

              body:
                JSON.stringify({
                  text:
                    normalizedText,
                }),
            }
          );


        const data =
          await response.json();


        if (
          !response.ok
        ) {
          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : JSON.stringify(
                  data.detail
                )
          );
        }


        const result =
          data as CWCommandResponse;


        if (
          !result.accepted
        ) {
          throw new Error(
            "CW command was not accepted."
          );
        }


        setLastCommand(
          result.command
        );


        await observeTxCycle();

      } catch (
        error
      ) {
        setLastTestTime(
          new Date()
        );

        setTestState(
          "error"
        );

        if (
          error instanceof Error
        ) {
          setStatusMessage(
            error.message
          );

        } else {
          setStatusMessage(
            "Unknown calibration error."
          );
        }
      }
    };


  if (
    !open
  ) {
    return null;
  }


  const resultLabel = (() => {
    switch (
      testState
    ) {
      case "sending":
        return "SENDING";

      case "waiting":
        return "WAITING";

      case "tx":
        return "RF TX";

      case "success":
        return "SUCCESS";

      case "warning":
        return "WARNING";

      case "error":
        return "ERROR";

      default:
        return "READY";
    }
  })();


  const resultClass = (() => {
    switch (
      testState
    ) {
      case "tx":
        return "cal-result-state cal-result-state-tx";

      case "success":
        return "cal-result-state cal-result-state-ok";

      case "warning":
        return "cal-result-state cal-result-state-warning";

      case "error":
        return "cal-result-state cal-result-state-error";

      default:
        return "cal-result-state";
    }
  })();


  return (
    <div
      className="cal-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="RF Calibration"
    >
      <div className="cal-panel">

        <header className="cal-header">
          <div>
            <h2>
              RF Calibration
            </h2>

            <p>
              Controlled transmission and
              diagnostic console
            </p>
          </div>


          <button
            type="button"
            className="cal-close"
            disabled={
              testBusy
            }
            onClick={
              onClose
            }
          >
            CLOSE
          </button>
        </header>


        <section className="cal-status-strip">

          <div className="cal-status-item">
            <span
              className={
                runtimeReady
                  ? "cal-dot cal-dot-ok"
                  : "cal-dot"
              }
            />

            <div>
              <span className="cal-status-label">
                Runtime
              </span>

              <strong>
                {runtimeReady
                  ? "READY"
                  : runtimeActive
                    ? "STARTING"
                    : "STOPPED"}
              </strong>
            </div>
          </div>


          <div className="cal-status-item">
            <span
              className={
                rfTxActive
                  ? "cal-dot cal-dot-tx"
                  : "cal-dot cal-dot-idle"
              }
            />

            <div>
              <span className="cal-status-label">
                RF TX
              </span>

              <strong
                className={
                  rfTxActive
                    ? "cal-text-tx"
                    : ""
                }
              >
                {rfTxActive
                  ? "ON"
                  : "OFF"}
              </strong>
            </div>
          </div>


          <div className="cal-status-item">
            <div>
              <span className="cal-status-label">
                Active Runtime
              </span>

              <strong>
                {protocol
                  ? protocol.toUpperCase()
                  : "--"}
              </strong>
            </div>
          </div>


          <div className="cal-status-item">
            <div>
              <span className="cal-status-label">
                Test Modulation
              </span>

              <strong>
                CW / Morse
              </strong>
            </div>
          </div>

        </section>


        <section className="cal-rf-line">

          <div>
            <span>
              CHANNEL
            </span>

            <strong>
              {formatFrequency(
                channelFrequencyHz
              )}
            </strong>
          </div>


          <div>
            <span>
              SDR CENTER
            </span>

            <strong>
              {formatFrequency(
                sdrCenterFrequencyHz
              )}
            </strong>
          </div>


          <div>
            <span>
              DIGITAL IF
            </span>

            <strong>
              {formatSignedFrequency(
                digitalIfHz
              )}
            </strong>
          </div>

        </section>


        <section className="cal-section">

          <div className="cal-section-heading">
            <div>
              <span className="cal-section-kicker">
                TEST TRANSMISSION
              </span>

              <h3>
                CW / Morse
              </h3>
            </div>

            <span className="cal-test-tag">
              ANALOG
            </span>
          </div>


          <div className="cal-field-row">

            <label className="cal-field">
              <span>
                CW text
              </span>

              <input
                type="text"
                value={
                  cwText
                }
                maxLength={
                  32
                }
                disabled={
                  testBusy
                }
                onChange={
                  (
                    event
                  ) => {
                    setCwText(
                      event
                        .target
                        .value
                    );
                  }
                }
              />
            </label>


            <button
              type="button"
              className={
                rfTxActive
                  ? "cal-send cal-send-active"
                  : "cal-send"
              }
              disabled={
                testBusy ||
                !runtimeActive ||
                !runtimeReady ||
                rfTxActive
              }
              onClick={
                () => {
                  void sendCWTest();
                }
              }
            >
              {testState === "sending"
                ? "SENDING..."
                : testState === "waiting"
                  ? "WAITING..."
                  : testState === "tx"
                    ? "RF TX ACTIVE"
                    : "▶ SEND CW TEST"}
            </button>

          </div>


          <div className="cal-warning-line">
            <span>
              ⚠
            </span>

            <p>
              This command generates a real RF
              transmission on{" "}
              <strong>
                {formatFrequency(
                  channelFrequencyHz
                )}
              </strong>
              . The modem remains in IDLE while
              the analog CW generator is active.
            </p>
          </div>

        </section>


        <section className="cal-section cal-result-section">

          <div className="cal-section-heading">
            <div>
              <span className="cal-section-kicker">
                LAST TEST
              </span>

              <h3>
                Transmission result
              </h3>
            </div>


            <span
              className={
                resultClass
              }
            >
              {resultLabel}
            </span>
          </div>


          <div className="cal-result-summary">

            <div className="cal-result-command">
              <span>
                COMMAND
              </span>

              <strong>
                {lastCommand
                  ?? "--"}
              </strong>
            </div>


            <div>
              <span>
                TX DURATION
              </span>

              <strong>
                {lastDurationMs !== null
                  ? `${(
                      lastDurationMs /
                      1000
                    ).toFixed(2)} s`
                  : "--"}
              </strong>
            </div>


            <div>
              <span>
                TIME
              </span>

              <strong>
                {lastTestTime
                  ? lastTestTime
                      .toLocaleTimeString()
                  : "--"}
              </strong>
            </div>

          </div>


          <div className="cal-result-message">
            {statusMessage}
          </div>

        </section>


        <section className="cal-measurements">

          <div className="cal-measurements-title">
            Measurements
          </div>


          <div className="cal-measurement">
            <span>
              BER
            </span>

            <strong>
              N/A
            </strong>
          </div>


          <div className="cal-measurement">
            <span>
              Frequency Error
            </span>

            <strong>
              N/A
            </strong>
          </div>


          <div className="cal-measurement">
            <span>
              RSSI
            </span>

            <strong>
              N/A
            </strong>
          </div>


          <div className="cal-measurement">
            <span>
              TX Offset
            </span>

            <strong>
              0 Hz
            </strong>
          </div>

        </section>


        <footer className="cal-footer">
          Measurement fields remain N/A until
          RF Gateway has a real measurement
          source. No synthetic BER, RSSI or
          frequency-error values are displayed.
        </footer>

      </div>
    </div>
  );
}


export default CalibrationPanel;
