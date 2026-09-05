import type {
  Protocol,
} from "./radio";


export interface Route {
  id: string;
  name: string;
  source_id: string;
  device_id: string;
  protocol: Protocol;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}


export interface RoutesResponse {
  version: number;
  count: number;
  enabled_count: number;
  routes: Route[];
}


export interface RouteCreateRequest {
  name: string;
  source_id: string;
  device_id: string;
  protocol: Protocol;
  enabled: boolean;
}


export interface RouteUpdateRequest {
  name?: string;
  source_id?: string;
  device_id?: string;
  protocol?: Protocol;
  enabled?: boolean;
}


export type RouteRuntimeState =
  | "stopped"
  | "starting"
  | "ready"
  | "running"
  | "blocked"
  | "error";


export type AudioBridgeState =
  | "not_implemented"
  | "ready"
  | "error";


export interface AudioBridgeCapability {
  protocol: Protocol;

  audio_input_supported: boolean;

  encoder_required: boolean;
  framing_required: boolean;

  bridge_state: AudioBridgeState;

  blocking_reason:
    string
    | null;
}


export interface RouteRuntimeStatus {
  route_id: string;

  state: RouteRuntimeState;

  active: boolean;

  protocol:
    Protocol
    | null;

  source_id:
    string
    | null;

  device_id:
    string
    | null;

  source_ready: boolean;

  rf_ready: boolean;

  config_ready: boolean;

  audio_bridge_ready: boolean;

  audio_bridge:
    AudioBridgeCapability
    | null;

  runtime_ready: boolean;

  blocked_reason:
    string
    | null;

  error:
    string
    | null;

  started_at:
    string
    | null;

  updated_at: string;
}


export type RouteWorkerState =
  | "stopped"
  | "starting"
  | "waiting_for_api_configuration"
  | "polling"
  | "idle"
  | "stopping"
  | "error";


export interface RouteQueueStats {
  route_id: string;

  queue_size: number;
  max_queue_size: number;

  seen_count: number;
  max_seen_items: number;

  total_enqueued: number;
  total_dequeued: number;
  total_duplicates: number;
  total_dropped: number;

  created_at: string;
  updated_at: string;
}


export interface RouteWorkerStatus {
  route_id: string;

  source_id:
    string
    | null;

  playlist_uuid:
    string
    | null;

  state: RouteWorkerState;

  running: boolean;

  poll_interval_seconds: number;

  poll_count: number;

  calls_received: number;
  calls_enqueued: number;
  calls_duplicates: number;
  calls_dropped: number;

  last_poll_at:
    string
    | null;

  last_success_at:
    string
    | null;

  last_error_at:
    string
    | null;

  error:
    string
    | null;

  started_at:
    string
    | null;

  updated_at: string;

  queue: RouteQueueStats;
}


export interface RouteWorkerResponse {
  exists: boolean;

  worker:
    RouteWorkerStatus
    | null;

  queue: RouteQueueStats;
}


export interface RouteWorkerStartResponse {
  worker_started: boolean;

  route: Route;

  worker: RouteWorkerStatus;

  queue: RouteQueueStats;
}


export interface RouteWorkerStopResponse {
  worker_stopped: boolean;

  worker:
    RouteWorkerStatus
    | null;

  queue: RouteQueueStats;
}


export interface RouteRuntimeResponse {
  runtime: RouteRuntimeStatus;

  worker:
    RouteWorkerStatus
    | null;

  queue: RouteQueueStats;
}


export interface RoutePreflightResponse {
  route: Route;

  runtime: RouteRuntimeStatus;

  worker:
    RouteWorkerStatus
    | null;

  queue: RouteQueueStats;
}


export interface RouteDetailsResponse
  extends Route {
  runtime: RouteRuntimeStatus;

  worker:
    RouteWorkerStatus
    | null;

  queue: RouteQueueStats;
}