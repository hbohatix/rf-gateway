export type RFDeviceCapabilities = {
  hardware_version?: string;
  clock?: string;

  soapysx_commit?: string;
  soapysx_tag?: string;

  hardware?: string;

  rx_channels?: number;
  tx_channels?: number;

  timestamps?: boolean;
  full_duplex?: boolean;
  agc?: boolean;

  rx_gain_range_db?: string;
  tx_gain_range_db?: string;

  rx_sample_rates?: string;
  tx_sample_rates?: string;

  connection?: string;
  profile?: string;

  uart_port?: string;
  uart_resolved_port?: string;
  uart_speed?: number;

  mmdvm_compatible?: boolean;
  mmdvm_host_protocol?: string;
  mmdvm_iq_required?: boolean;

  frequency_policy?: string;
  frequency_ranges_hz?: number[][];
};


export type RFDevice = {
  id: string;

  type: string;
  backend: string;

  driver: string;
  label: string;

  available: boolean;

  probe_ok: boolean;
  probe_error: string | null;

  capabilities: RFDeviceCapabilities;
};


export type RFDevicesResponse = {
  backend: string;

  available: boolean;

  device_count: number;

  devices: RFDevice[];

  warnings?: string[];

  error: string | null;
};
