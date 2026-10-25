import type { Protocol } from "./radio";

export type Health = {
  status: string;
  service: string;
  version: string;
};

export type MMDVMProcessStatus = {
  running: boolean;
  ready: boolean;
  pid: number | null;
  udp_port: number;
};

export type MMDVMStatus = {
  runtime_active: boolean;
  runtime_ready: boolean;
  protocol: Protocol | null;
  frequency_hz: number | null;
  channel_frequency_hz: number | null;
  sdr_tx_center_frequency_hz: number | null;
  sdr_rx_center_frequency_hz: number | null;
  digital_if_hz: number | null;
  sample_rate_hz: number | null;
  actual_tx_rate_hz: number | null;
  actual_rx_rate_hz: number | null;
  modem_mode: string | null;
  rf_tx_active: boolean;
  tx_stream_active: boolean;
  hardware_open: boolean;
  iq_streams_active: boolean;
  hardware_version: string | null;
  driver_name: string | null;
  mmdvm_iq: MMDVMProcessStatus;
  mmdvm_host: MMDVMProcessStatus;
  runtime_config: string;
  last_error: string | null;
};

export type RFStatus = {
  tx: boolean;
  runtime_active: boolean;
  rf_tx_active: boolean;
  tx_stream_active: boolean;
  protocol: Protocol | null;
  device_id?: string | null;
  config: unknown;
  mmdvm?: MMDVMStatus | null;
  error?: string | null;
};

export type SavedModesResponse = {
  version: number;
  modes: Partial<Record<Protocol, Record<string, unknown>>>;
};
