import type { Protocol } from "./radio";
import type { RFStatus } from "./runtime";

export type OnAir = {
  route_id: string;
  source_id: string | null;
  protocol: Protocol | null;
  state: string;
  started_at: string | null;
  error: string | null;
  live_audio: {
    state?: string;
    running?: boolean;
    error?: string | null;
    pcm_bytes_received?: number;
    tx_start_count?: number;
    tx_end_count?: number;
    last_activity_level_dbfs?: number | null;
    last_pcm_at?: string | null;
  } | null;
  calls: {
    worker_state?: string;
    calls_observed?: number;
    processor_state?: string;
    calls_sent?: number;
    current_call?: string | null;
  } | null;
};

export type TransmitState = {
  mode: { protocol: Protocol | null; summary: string | null; configured: boolean };
  device_id: string | null;
  rf: RFStatus;
  on_air: OnAir | null;
  errors: Record<string, string>;
};

export type Source = {
  id: string;
  name: string;
  type: string;
  url: string;
  probe?: {
    reachable?: boolean;
    audio_api_configured?: boolean;
    playback_error?: string | null;
    page_name?: string | null;
  } | null;
};
