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

  error: string | null;
};
