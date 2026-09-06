# RF Gateway

RF Gateway is an experimental software-defined radio gateway that routes supported internet audio sources to RF through a configurable digital radio stack.

The project combines:

- a **FastAPI** backend,
- a **React + TypeScript + Vite** frontend,
- **SoapySDR** hardware discovery and control,
- **MMDVM-Host**,
- **MMDVM-IQ**,
- an **IMBE vocoder** path for P25,
- Broadcastify Calls and Broadcastify Live Audio source handling.

The current development focus is **P25 / C4FM end-to-end audio routing** through an SXceiver/SoapySX RF path.

> **Project status:** active development / experimental.  
> P25 end-to-end transmission has been tested. FM, DMR and TETRA configuration exists, but their source-audio bridge paths are not yet at the same level of completion.

---

## Features

### RF and modem stack

- SoapySDR device discovery
- SXceiver / SoapySX integration
- MMDVM-IQ process management
- MMDVM-Host process management
- runtime generation of MMDVM-Host configuration
- RF runtime status and telemetry
- CW calibration/test support
- configurable operating modes:
  - FM
  - DMR
  - P25
  - TETRA

### P25

- 8 kHz mono signed 16-bit PCM input
- native IMBE encoding
- P25 network record formatting
- UDP transport to MMDVM-Host
- P25 C4FM transmission through MMDVM-IQ and SXceiver
- configurable:
  - RF frequency
  - NAC
  - talkgroup
  - radio ID
  - modulation

### Internet audio sources

RF Gateway currently has two Broadcastify source models.

#### Broadcastify Calls

Discrete-call workflow:

```text
Broadcastify Calls
        |
        v
Calls API polling
        |
        v
Call queue
        |
        v
Audio download / decode
        |
        v
PCM 8 kHz mono
        |
        v
IMBE
        |
        v
P25 network records
        |
        v
MMDVM-Host
        |
        v
MMDVM-IQ
        |
        v
RF
```

#### Broadcastify Live Audio

Continuous-stream workflow:

```text
Broadcastify Live Audio
        |
        v
HLS transport
        |
        v
FFmpeg decode
        |
        v
PCM 8 kHz mono / 20 ms chunks
        |
        v
Audio activity gate
        |
        +---- silence ----> no RF TX
        |
        +---- activity ---> P25 TX session
                              |
                              v
                            IMBE
                              |
                              v
                        P25 network records
                              |
                              v
                         MMDVM-Host
                              |
                              v
                          MMDVM-IQ
                              |
                              v
                              RF
```

The Live Audio path uses an activity detector with pre-roll, attack, hysteresis and TX hang so that silence in a continuous internet stream does not keep the RF transmitter keyed continuously.

Current tuned defaults:

| Parameter | Default |
|---|---:|
| PCM sample rate | 8000 Hz |
| Channels | 1 |
| Sample width | 16-bit |
| Chunk duration | 20 ms |
| Pre-roll | 400 ms |
| Attack | 100 ms |
| Hang | 3000 ms |
| Minimum trigger | -60 dBFS |
| Hysteresis | 6 dB |

---

## Architecture

```text
                        +-----------------------+
                        |   React / TypeScript   |
                        |        Vite UI         |
                        +-----------+-----------+
                                    |
                                    | HTTP / JSON
                                    v
                        +-----------------------+
                        |       FastAPI         |
                        |       backend         |
                        +-----------+-----------+
                                    |
                 +------------------+------------------+
                 |                                     |
                 v                                     v
      +----------------------+              +----------------------+
      | Broadcastify Calls   |              | Broadcastify Live    |
      | discrete calls       |              | Audio / HLS          |
      +----------+-----------+              +----------+-----------+
                 |                                     |
                 v                                     v
         +---------------+                     +---------------+
         | Call queue    |                     | Activity gate |
         +-------+-------+                     +-------+-------+
                 |                                     |
                 +------------------+------------------+
                                    |
                                    v
                         +---------------------+
                         | PCM 8 kHz mono s16le |
                         +----------+----------+
                                    |
                                    v
                         +---------------------+
                         |    IMBE vocoder     |
                         +----------+----------+
                                    |
                                    v
                         +---------------------+
                         | P25 network format  |
                         +----------+----------+
                                    |
                             UDP 42020 -> 32010
                                    |
                                    v
                         +---------------------+
                         |     MMDVM-Host      |
                         +----------+----------+
                                    |
                              UDP 3335 -> 3334
                                    |
                                    v
                         +---------------------+
                         |      MMDVM-IQ       |
                         +----------+----------+
                                    |
                                    v
                         +---------------------+
                         | SoapySX / SX1255    |
                         +----------+----------+
                                    |
                                    v
                                   RF
```

---

## Repository layout

```text
rf-gateway/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── routes.py
│   │   ├── sources.py
│   │   ├── audio_decoder.py
│   │   ├── audio_activity_gate.py
│   │   ├── broadcastify_calls_client.py
│   │   ├── broadcastify_worker.py
│   │   ├── broadcastify_live_audio_client.py
│   │   ├── broadcastify_live_audio_pipeline.py
│   │   ├── call_processor.py
│   │   ├── call_queue.py
│   │   ├── imbe_encoder.py
│   │   ├── p25_network_formatter.py
│   │   ├── p25_network_sender.py
│   │   ├── p25_streaming_session.py
│   │   ├── route_runtime.py
│   │   ├── config_store.py
│   │   ├── mmdvm/
│   │   └── rf/
│   ├── data/
│   ├── native/
│   │   ├── build_imbe_wrapper.sh
│   │   ├── imbe_wrapper.cpp
│   │   └── libimbe_vocoder_wrapper.so
│   ├── requirements.txt
│   └── .env
├── config/
│   └── mmdvm/
│       └── MMDVM-IQ.ini
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── scripts/
│   ├── install-debian.sh
│   └── run-dev.sh
├── third_party/
│   ├── MMDVM-Host/
│   ├── MMDVM-IQ/
│   └── imbe_vocoder/
├── .gitmodules
└── README.md
```

---

# Requirements

The installer is currently designed for:

- Debian
- Raspberry Pi OS
- preferably a **64-bit** installation

Development is currently focused on Linux.

Main dependencies include:

- Python 3
- Python venv
- FastAPI
- Uvicorn
- Node.js 22.x
- npm
- SoapySDR
- SoapySDR tools
- FFmpeg
- Mosquitto MQTT
- C/C++ build tools
- MMDVM-IQ
- MMDVM-Host
- IMBE vocoder sources

For the tested RF path, an SXceiver/SoapySX-compatible device is expected.

---

# Installation

## 1. Clone the repository

```bash
git clone --recurse-submodules \
  https://github.com/hbohatix/rf-gateway.git

cd rf-gateway
```

If the repository was cloned without submodules:

```bash
git submodule sync --recursive

git submodule update \
  --init \
  --recursive
```

The repository currently uses these submodules:

```text
third_party/MMDVM-IQ
third_party/MMDVM-Host
third_party/imbe_vocoder
```

---

## 2. Run the Debian / Raspberry Pi OS installer

```bash
chmod +x scripts/install-debian.sh

./scripts/install-debian.sh
```

The installer performs the main development setup:

- installs system packages,
- enables Mosquitto,
- installs/checks Node.js 22.x,
- initializes Git submodules,
- creates `backend/.venv`,
- installs Python dependencies,
- builds MMDVM-IQ,
- builds MMDVM-Host,
- installs frontend dependencies,
- verifies the frontend production build,
- checks FFmpeg,
- checks SoapySDR,
- displays detected USB and PCI devices.

---

## 3. Build the native IMBE wrapper

The P25 source-to-RF path requires the native IMBE wrapper.

```bash
cd backend/native

chmod +x build_imbe_wrapper.sh

./build_imbe_wrapper.sh
```

Expected output library:

```text
backend/native/libimbe_vocoder_wrapper.so
```

Quick verification:

```bash
file backend/native/libimbe_vocoder_wrapper.so

nm -D backend/native/libimbe_vocoder_wrapper.so \
  | grep rf_gateway_imbe_
```

---

# Broadcastify Calls configuration

Broadcastify Calls API credentials must be provided locally.

Create:

```text
backend/.env
```

Example template:

```dotenv
BROADCASTIFY_CALLS_BASE_URL=https://api.bcfy.io

BROADCASTIFY_CALLS_KEY_ID=
BROADCASTIFY_CALLS_SIGNING_SECRET=
BROADCASTIFY_CALLS_ISSUER=

BROADCASTIFY_CALLS_JWT_TTL_SECONDS=3600
BROADCASTIFY_CALLS_TIMEOUT_SECONDS=15

BROADCASTIFY_CALLS_PLAYLIST_PATH=
BROADCASTIFY_CALLS_LIVE_CALLS_PATH=https://www.broadcastify.com/calls/apis/live-calls
BROADCASTIFY_CALLS_CALL_PATH=
BROADCASTIFY_CALLS_GROUP_ARCHIVE_PATH=
```

Use endpoint values and credentials appropriate for your approved Broadcastify Calls API access.

Do **not** commit real secrets.

Recommended permissions:

```bash
chmod 600 backend/.env
```

The backend loads `backend/.env` at startup.

---

# Running RF Gateway

## Development mode

The easiest way to start both backend and frontend is:

```bash
./scripts/run-dev.sh
```

The script starts:

```text
Frontend:   http://localhost:5173
Backend:    http://localhost:8000
Swagger UI: http://localhost:8000/docs
```

Press `Ctrl+C` to stop the development runtime.

---

## Start the backend manually

```bash
cd backend

source .venv/bin/activate

python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000
```

For development with reload:

```bash
python -m uvicorn app.main:app \
  --reload \
  --host 0.0.0.0 \
  --port 8000
```

---

## Start the frontend manually

```bash
cd frontend

npm install

npm run dev -- \
  --host 0.0.0.0 \
  --port 5173
```

Production build check:

```bash
npm run build
```

---

# MMDVM runtime

RF Gateway manages MMDVM-IQ and MMDVM-Host from the backend.

Avoid starting another copy of MMDVM-IQ or MMDVM-Host manually while the backend-managed RF runtime is active.

A manually started MMDVM-IQ may already own the SXceiver GPIO/device and cause a second probe to fail with errors such as:

```text
Failed to request GPIO line
```

The managed runtime marks the `sx` driver as open so discovery can avoid re-opening the same hardware unnecessarily.

---

## Runtime configuration files

MMDVM-IQ:

```text
config/mmdvm/MMDVM-IQ.ini
```

Generated MMDVM-Host runtime configuration:

```text
backend/data/runtime/mmdvm/MMDVM-Host.ini
```

---

# Important UDP/TCP ports

| Port | Protocol | Purpose |
|---:|---|---|
| 5173 | TCP | Vite development frontend |
| 8000 | TCP | FastAPI backend |
| 1883 | TCP | Mosquitto MQTT |
| 3334 | UDP | MMDVM-IQ local port |
| 3335 | UDP | MMDVM-Host modem local port |
| 32010 | UDP | MMDVM-Host P25 network port |
| 42020 | UDP | RF Gateway P25 sender local port |

Typical P25 path:

```text
RF Gateway
  UDP 42020
      |
      v
MMDVM-Host
  UDP 32010

MMDVM-Host
  UDP 3335
      |
      v
MMDVM-IQ
  UDP 3334
      |
      v
SoapySX / SXceiver
      |
      v
RF
```

---

# API

Interactive API documentation is available at:

```text
http://localhost:8000/docs
```

OpenAPI schema:

```text
http://localhost:8000/openapi.json
```

The API version currently used by the backend is `0.11.x`.

---

## Health

### `GET /`

Returns basic service information.

### `GET /api/health`

Example:

```bash
curl -s \
  http://127.0.0.1:8000/api/health \
  | jq
```

---

# Mode configuration API

### `GET /api/config/modes`

Returns all saved mode configurations.

### `GET /api/config/modes/{protocol}`

Supported protocol names:

```text
fm
dmr
p25
tetra
```

Example:

```bash
curl -s \
  http://127.0.0.1:8000/api/config/modes/p25 \
  | jq
```

### `PUT /api/config/modes`

Example P25 configuration:

```bash
curl -s -X PUT \
  http://127.0.0.1:8000/api/config/modes \
  -H 'Content-Type: application/json' \
  -d '{
    "protocol": "p25",
    "frequency_hz": 438800000,
    "nac": "293",
    "talkgroup": 260,
    "radio_id": 1000,
    "modulation": "c4fm"
  }' \
  | jq
```

> The RF frequency and protocol-specific parameters are owned by the mode configuration. Routes reference a source, device and protocol rather than duplicating those radio parameters.

---

# Device API

### `GET /api/devices`

Discover currently available SoapySDR devices.

```bash
curl -s \
  http://127.0.0.1:8000/api/devices \
  | jq
```

### `POST /api/devices/refresh`

Force device discovery refresh.

### `POST /api/devices/{device_id}/open`

Open a directly managed SoapySDR device.

### `GET /api/devices/{device_id}/status`

Return direct-device runtime state.

### `POST /api/devices/{device_id}/configure`

Configure direct SoapySDR parameters.

### `POST /api/devices/{device_id}/close`

Close a directly managed device.

Direct Soapy access is intentionally blocked while the MMDVM runtime owns the SXceiver.

---

# RF / MMDVM API

### `GET /api/rf/status`

Current RF runtime status.

```bash
curl -s \
  http://127.0.0.1:8000/api/rf/status \
  | jq
```

### `POST /api/rf/start`

Starts the backend-managed MMDVM RF runtime.

Example P25 request:

```bash
curl -s -X POST \
  http://127.0.0.1:8000/api/rf/start \
  -H 'Content-Type: application/json' \
  -d '{
    "protocol": "p25",
    "device_id": "soapy-0",
    "frequency_hz": 438800000,
    "nac": "293",
    "talkgroup": 260,
    "radio_id": 1000,
    "modulation": "c4fm"
  }' \
  | jq
```

### `POST /api/rf/stop`

Stops the managed RF runtime.

### `GET /api/mmdvm/status`

Returns MMDVM runtime telemetry.

```bash
curl -s \
  http://127.0.0.1:8000/api/mmdvm/status \
  | jq
```

### `GET /api/mmdvm/logs`

Returns recent MMDVM logs.

### `POST /api/calibration/cw-id`

Transmit a short CW calibration/test ID while the runtime is active.

Example:

```bash
curl -s -X POST \
  http://127.0.0.1:8000/api/calibration/cw-id \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "SP5OPS"
  }' \
  | jq
```

---

# Source API

Base path:

```text
/api/sources
```

### `GET /api/sources`

List configured internet sources.

### `POST /api/sources`

Create a source.

---

## Broadcastify Calls source example

```bash
curl -s -X POST \
  http://127.0.0.1:8000/api/sources \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Example Calls Playlist",
    "type": "broadcastify_calls",
    "url": "https://www.broadcastify.com/calls/playlists/?uuid=YOUR-UUID&view=list"
  }' \
  | jq
```

---

## Broadcastify Live Audio source example

```bash
curl -s -X POST \
  http://127.0.0.1:8000/api/sources \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Example Live Audio Feed",
    "type": "broadcastify_live_audio",
    "url": "https://www.broadcastify.com/listen/feed/FEED_ID"
  }' \
  | jq
```

Live Audio transport currently uses the stream model used by the normal web player and decodes HLS media to local PCM with `curl` and FFmpeg.

### `POST /api/sources/broadcastify/probe`

Probe a Broadcastify source URL.

### `GET /api/sources/broadcastify/api-status`

Return Broadcastify Calls API configuration status and Live Audio transport readiness.

### `POST /api/sources/{source_id}/probe`

Re-probe an existing source.

### `DELETE /api/sources/{source_id}`

Delete a source.

---

# Route API

Base path:

```text
/api/routes
```

A Route connects:

```text
Source
  +
RF Device
  +
Protocol
```

The protocol's actual RF parameters come from the saved mode configuration.

---

## List routes

### `GET /api/routes`

```bash
curl -s \
  http://127.0.0.1:8000/api/routes \
  | jq
```

---

## Create a route

### `POST /api/routes`

Example:

```bash
curl -s -X POST \
  http://127.0.0.1:8000/api/routes \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Example P25 Route",
    "source_id": "SOURCE_UUID",
    "device_id": "soapy-0",
    "protocol": "p25",
    "enabled": true
  }' \
  | jq
```

---

## Route details

### `GET /api/routes/{route_id}`

Returns route configuration plus runtime/source pipeline information.

---

## Runtime status

### `GET /api/routes/{route_id}/runtime`

Returns:

- Route runtime state
- Calls worker state, when applicable
- Live Audio pipeline state, when applicable
- queue statistics

---

## Preflight

### `POST /api/routes/{route_id}/preflight`

Checks whether the route can run.

Preflight currently checks items including:

```text
route enabled
source reachable / source transport ready
RF device available
protocol configuration ready
audio bridge ready
device/runtime conflicts
```

A successful P25 preflight should report:

```json
{
  "state": "ready",
  "source_ready": true,
  "rf_ready": true,
  "config_ready": true,
  "audio_bridge_ready": true,
  "runtime_ready": true,
  "blocked_reason": null
}
```

---

## Start route

### `POST /api/routes/{route_id}/start`

This is the preferred route-level start operation.

For Broadcastify Calls it starts:

```text
Broadcastify worker
+
Call processor
```

For Broadcastify Live Audio it starts:

```text
Live Audio stream
+
activity gate
+
P25 streaming session
```

Example:

```bash
curl -s -X POST \
  http://127.0.0.1:8000/api/routes/ROUTE_UUID/start \
  | jq
```

---

## Stop route

### `POST /api/routes/{route_id}/stop`

```bash
curl -s -X POST \
  http://127.0.0.1:8000/api/routes/ROUTE_UUID/stop \
  | jq
```

The P25 path sends a terminator when an active P25 session is ended normally.

---

## Enable / disable route

### `PUT /api/routes/{route_id}`

Example:

```bash
curl -s -X PUT \
  http://127.0.0.1:8000/api/routes/ROUTE_UUID \
  -H 'Content-Type: application/json' \
  -d '{
    "enabled": false
  }' \
  | jq
```

`enabled` is a configuration flag.

It does **not** mean that RF is currently transmitting.

Disabling a route stops/removes its active source pipeline.

---

## Delete route

### `DELETE /api/routes/{route_id}`

---

## Calls-specific route endpoints

These are primarily for the discrete Broadcastify Calls pipeline:

```text
GET  /api/routes/workers
GET  /api/routes/processors
GET  /api/routes/{route_id}/worker
GET  /api/routes/{route_id}/processor
GET  /api/routes/{route_id}/queue
POST /api/routes/{route_id}/worker/start
POST /api/routes/{route_id}/worker/stop
```

For normal UI operation, prefer the generic route-level:

```text
POST /api/routes/{route_id}/start
POST /api/routes/{route_id}/stop
```

---

# Live Audio runtime status

### `GET /api/routes/live-audio`

Returns all active Broadcastify Live Audio pipelines.

Example:

```bash
curl -s \
  http://127.0.0.1:8000/api/routes/live-audio \
  | jq
```

Useful fields include:

```text
state
running
pcm_chunks_received
pcm_bytes_received
tx_start_count
tx_end_count
transport_gap_end_count
last_activity_level_dbfs
last_noise_floor_dbfs
last_trigger_dbfs
gate
stream
p25
```

Typical states:

```text
starting
connecting
listening
transmitting
stopping
stopped
error
```

Example compact monitor:

```bash
watch -n 0.5 \
  'curl -s http://127.0.0.1:8000/api/routes/live-audio |
   jq ".pipelines[0] |
   {
     state,
     running,
     pcm_chunks_received,
     tx_start_count,
     tx_end_count,
     last_activity_level_dbfs,
     p25_active: .p25.active
   }"'
```

---

# P25 runtime diagnostics

## Verify MMDVM processes

```bash
pgrep -af \
  'MMDVM-IQ|MMDVM-Host'
```

## Verify UDP ports

```bash
ss -lunp \
  | grep -E \
  ':3334|:3335|:32010|:42020'
```

## MMDVM status

```bash
curl -s \
  http://127.0.0.1:8000/api/mmdvm/status \
  | jq
```

## Live Audio status

```bash
curl -s \
  http://127.0.0.1:8000/api/routes/live-audio \
  | jq
```

## Confirm that the P25 sender is still advancing

```bash
curl -s \
  http://127.0.0.1:8000/api/routes/live-audio \
  | jq '.pipelines[0].p25.network_records_sent'

sleep 3

curl -s \
  http://127.0.0.1:8000/api/routes/live-audio \
  | jq '.pipelines[0].p25.network_records_sent'
```

If the value increases, the backend is still producing P25 network records.

---

# Data and generated files

Runtime data is stored under:

```text
backend/data/
```

Important examples:

```text
backend/data/sources.json
backend/data/routes.yaml
backend/data/runtime/mmdvm/MMDVM-Host.ini
backend/data/runtime/mmdvm/MMDVM-Host.log
backend/data/runtime/mmdvm/MMDVM-IQ.log
```

Do not treat generated runtime files as static configuration.

---

# Current implementation status

## Working / tested

- React/Vite frontend
- FastAPI backend
- SoapySDR discovery
- SXceiver / SoapySX runtime
- MMDVM-IQ startup and telemetry
- MMDVM-Host startup and telemetry
- mode configuration persistence
- Route CRUD
- Route preflight
- Broadcastify Calls source model
- Calls polling / queue processing
- FFmpeg audio decoding
- native IMBE wrapper
- PCM -> IMBE
- P25 network formatting
- P25 UDP sender
- MMDVM-Host P25 network input
- MMDVM-IQ P25 C4FM output
- physical P25 RF transmission
- Broadcastify Live Audio HLS transport
- Live Audio -> PCM
- adaptive activity gate
- automatic TX start/end based on audio activity
- Live Audio Route -> physical P25 RF

## In progress / experimental

- long continuous Live Audio P25 transmission rollover
- DMR source-audio bridge
- TETRA source-audio bridge
- FM source-audio bridge
- authentication/login
- production deployment/service management
- additional hardware support
- frontend polish and compact route cards

---

# Known issue: long continuous P25 transmissions

MMDVM-Host currently uses a transmission timeout.

A continuous P25 source session that remains open beyond the configured MMDVM timeout may be terminated by MMDVM-Host while the backend still considers the P25 streaming session active.

Observed behavior:

```text
backend:
  state = transmitting
  p25.active = true
  network_records_sent continues increasing

MMDVM:
  modem_mode = Idle
  rf_tx_active = false
```

The intended fix is to perform a controlled P25 session rollover before the MMDVM timeout:

```text
P25 TX
  |
  | max continuous TX window
  v
P25 terminator
  |
  v
new P25 session
  |
  v
continue audio
```

A target rollover around 150 seconds leaves margin below a 180-second MMDVM timeout.

---

# Security

Authentication is not yet implemented.

Do **not** expose the development FastAPI or Vite ports directly to the public Internet.

Until authentication and production deployment are implemented, use the project only on a trusted/private network or place it behind your own authenticated reverse proxy/VPN/access-control layer.

Never commit:

- API credentials
- signing secrets
- private keys
- `.env` files containing secrets

---

# Legal / RF use

RF Gateway is an experimental radio project.

You are responsible for:

- operating only on frequencies you are legally authorized to use,
- complying with local radio regulations,
- using appropriate transmitter power and hardware,
- avoiding interference,
- complying with the terms and permissions of internet audio/content providers,
- obtaining any required authorization before retransmitting third-party audio over RF.

Broadcastify Calls API access or the technical ability to receive a Live Audio feed should not be assumed to grant permission to retransmit that content over RF.

---

# Development checks

## Backend import

```bash
cd backend

source .venv/bin/activate

python -c \
  'from app.main import app; print("MAIN IMPORT OK")'
```

## Compile a backend module

```bash
python -m py_compile \
  app/example.py
```

## Frontend build

```bash
cd frontend

npm run build
```

## Frontend lint

```bash
npm run lint
```

---

# Updating submodules

```bash
git submodule sync --recursive

git submodule update \
  --init \
  --recursive
```

To inspect current submodule revisions:

```bash
git submodule status
```

---

# Typical development startup sequence

```text
1. Start backend + frontend
2. Verify SoapySDR device discovery
3. Save protocol configuration
4. Start RF/MMDVM runtime
5. Add or select an internet source
6. Create a Route
7. Run Route preflight
8. Start Route
9. Monitor Route / MMDVM telemetry
10. Stop Route before changing runtime-critical settings
```

Example quick checks:

```bash
curl -s \
  http://127.0.0.1:8000/api/health \
  | jq

curl -s \
  http://127.0.0.1:8000/api/devices \
  | jq

curl -s \
  http://127.0.0.1:8000/api/mmdvm/status \
  | jq

curl -s \
  http://127.0.0.1:8000/api/routes \
  | jq
```