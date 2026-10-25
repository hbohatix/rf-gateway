# RF Gateway

RF Gateway is an experimental software-defined radio gateway that routes internet and remote-SDR audio to RF through MMDVM.

The project combines:

- a **FastAPI** backend,
- a **React + TypeScript + Vite** frontend in the style of the TETRA FlowStation dashboard (dark / light / blue themes, PL / EN),
- **SoapySDR** hardware discovery and control,
- **MMDVM-Host** and **MMDVM-IQ**,
- software vocoders: **IMBE** (P25) and **AMBE+2 / AMBE** (DMR, System Fusion DN, NXDN, D-Star) from OP25,
- sources: Broadcastify Calls, authorized HTTP audio and **remote SDRs** (rtl_tcp, KiwiSDR, GQRX / SDR++ / SDRangel / OpenWebRX audio).

Source audio can be transmitted as **FM, DMR, System Fusion (YSF DN), D-Star, NXDN or P25**.

> **Project status:** active development / experimental.
> P25 end-to-end transmission has been validated on SXceiver/SoapySX. The DMR, YSF, D-Star, NXDN and FM paths are validated against the real MMDVM-Host binary with a simulated modem (`backend/tools/mmdvm_loopback.py`) and against MMDVM-Host's own decoders, but have not yet been checked on air with a receiving radio.

---

## Features

### RF and modem stack

- unified RF hardware discovery
- conventional MMDVM modem discovery over UART/USB/GPIO
- SoapySDR device discovery
- MMDVM-IQ SDR integration
- SXceiver / SoapySX integration as the first validated SDR path
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

## Digital and analog voice modes

Every mode takes 8 kHz mono PCM from a route (Calls, Live/HTTP audio or remote SDR), runs it through the same activity gate and hands the encoded audio to MMDVM-Host over its local network interface. MMDVM-Host then drives the SDR (MMDVM-IQ) or MMDVM modem.

| Mode | Vocoder | MMDVM-Host interface | RF Gateway port → MMDVM-Host port |
|---|---|---|---|
| FM | none (PCM) | `[FM Network]` `FMD` packets | UDP 4810 → 3810 |
| DMR | AMBE+2 3600x2450 | `[DMR Network]` `DMRD` (Homebrew data) | UDP 62031 → 62032 |
| System Fusion | AMBE+2 (DN, V/D mode 2) | `[System Fusion Network]` `YSFD` | UDP 4200 → 3200 |
| D-Star | AMBE 3600x2400 | `[D-Star Network]` `DSRP` | UDP 20010 → 20011 |
| NXDN | AMBE+2 (EHR 4800) | `[NXDN Network]` Icom protocol | UDP 14020 → 14021 |
| P25 | IMBE | `[P25 Network]` | UDP 42020 → 32010 |
| TETRA | — | not supported by MMDVM (see TETRA FlowStation) | — |

How each path is built:

- **DMR** — voice LC header (full LC, BPTC(196,96), RS(12,9)), voice bursts A–F with three FEC-protected AMBE+2 frames each, terminator with LC. MMDVM-Host regenerates sync, slot type, EMB and embedded LC. DMR runs MMDVM-Host with `Duplex=1`, so it goes out like a repeater downlink (BS sync, CACH, both timeslots) and **TS1 and TS2** both work; program the radio with the frequency, color code and timeslot. (In simplex/DMO MMDVM-Host drops all network TS1 traffic.)
- **System Fusion** — DN (V/D mode 2) frames: FICH (Golay + K=5 convolution + interleave), callsign DCH, VCH with 27 bits ×3 repetition, whitening and interleaving; header and terminator with CSD1/CSD2. Source callsign, destination and DG-ID are configurable.
- **D-Star** — radio header with X.25 CRC (MY / suffix / YOUR / DIRECT), AMBE 2400 frames with Golay + PRNG FEC, slow-data sync and a 20-character text message.
- **NXDN** — VCALL header and TX_REL terminator in FACCH1, voice frames with four AMBE+2 frames and the VCALL message split over the SACCH superframe (MMDVM-Host adds the NXDN FEC).
- **FM** — PCM straight to MMDVM-Host's FM network (CTCSS, pre-emphasis and deviation applied by MMDVM-Host/modem).
- **P25** — unchanged IMBE path.

Long continuous audio is split into back-to-back transmissions every 150 s (below MMDVM-Host's 180 s timeout), for every mode.

### AMBE vocoder options

The default **software** encoder is OP25's AMBE encoder (`backend/native/ambe`, see its README for provenance and licensing), so no hardware is needed. For AMBE+2 modes (DMR, YSF, NXDN) a DVSI AMBE-3000 can be selected instead in the transmit mode settings (experimental, not yet validated with hardware):

- `dv3000_serial` — ThumbDV / DV3000 / DVstick on a serial port (e.g. `/dev/ttyUSB0`, 460800 baud),
- `ambeserver` — an AMBE-3000 behind AMBEServer on UDP (default port 2460).

## Remote SDR sources

**Remote SDR** in the UI (or `POST /api/sources` with `type: "remote_sdr"`) adds a receiver as a continuous source. A remote SDR is described by one URL:

| URL | Receiver |
|---|---|
| `rtl_tcp://host:1234?freq=145500000&mod=nfm&gain=auto&squelch=auto` | Any RTL-SDR shared with `rtl_tcp`. RF Gateway receives raw IQ (240 kS/s, tuned 60 kHz off-centre) and demodulates NFM or AM itself, with carrier squelch (`auto` = noise floor + 10 dB, `off`, or a dBFS level). Options: `ppm`, `bw` (channel width), `audio_gain`. |
| `kiwisdr://host:8073?freq=7100000&mod=lsb` | A public or private KiwiSDR (0–30 MHz) over its WebSocket API. Modes `am`, `amn`, `nbfm`, `usb`, `lsb`, `cw`; optional S-meter `squelch` in dBm. |
| `udp://0.0.0.0:7355?format=s16le&rate=48000` | Raw PCM pushed by GQRX ("UDP" audio), SDRangel or `rtl_fm \| nc -u`. RF Gateway listens. |
| `tcp://host:port?format=s16le&rate=48000` | Raw PCM from an SDR++ network sink (TCP). |
| `http(s)://…`, `rtsp://…`, `rtp://…`, `srt://…` | Compressed streams (OpenWebRX/Icecast/darkice set-ups), decoded with FFmpeg. |

`POST /api/sources/remote-sdr/probe` checks a URL (rtl_tcp handshake and tuner type, KiwiSDR `/status`, HTTP reachability) without saving it. Routes accept remote SDR sources exactly like Live Audio sources: activity gate, any supported protocol, TX rollover. Only retransmit receivers and audio you are authorized to use, on frequencies you are licensed for.

## Network SDR transmitters

A remote SDR can also be the **transmitter**. **RF Devices → Network SDR (TX)** (or `POST /api/devices/network`) registers a PlutoSDR, LibreSDR, LimeSDR / LimeSDR Mini or Ettus USRP with its SoapySDR URI (for example `ip:192.168.2.1`) and RX/TX gains. The device then appears in discovery and route setup like the SXceiver; when the runtime starts on it, RF Gateway writes `backend/data/runtime/mmdvm/MMDVM-IQ.ini` with the matching `[Soapy] Type/URI/RxGain/TxGain`.

- TX gain defaults to **0**; raise it deliberately while measuring output power.
- The SoapySDR module for the device must be installed on the gateway (SoapyPlutoSDR, SoapyLMS7, SoapyUHD); discovery reports a missing module or an unreachable `ip:` host (iiod port 30431) as a probe error.
- These devices are untested on air in this project; the generated configuration was checked with MMDVM-IQ only.

`config/mmdvm/MMDVM-IQ.ini` now uses the sections the current MMDVM-IQ reads (`[Host]`, `[Modem] Driver=Soapy`, `[Soapy]`). The previous file put the gains under `[Modem]`, which MMDVM-IQ ignores, so the SXceiver ran with RX gain 0 and TX gain 0. The new file keeps **TxGain=0** (same TX power as before) and applies the intended **RxGain=50**.

## Web UI

One screen does the job: **Transmit**.

- **Transmit mode** (right): pick DMR, P25, FM, YSF, D-Star or NXDN and set it up (frequency, slot, color code, talkgroup, NAC, …). This is the only place a mode lives; settings save automatically and apply immediately, also to what is on air.
- **Sources** (left): paste a Broadcastify Calls playlist, Broadcastify Live feed, HTTP/HLS stream or remote SDR URL and press **Add**. Press **▶ Transmit** on a source to put it on air in the current mode. One source is on air at a time: starting another takes the transmitter over. **■ Stop** / **Turn everything off** stops the source and MMDVM.

Other pages: **Remote SDR** (URL builder and probe for rtl_tcp / KiwiSDR / audio streams), **RF Devices** (SoapySDR and MMDVM modem discovery), **MMDVM Log**. The UI has Dark / Light / Blue themes and Polish / English labels.

The frontend calls the API on its own origin (`/api/...`); Vite proxies `/api`, `/docs` and `/openapi.json` to the backend (`RFGW_BACKEND_URL`, default `http://127.0.0.1:8000`) in both `npm run dev` and `npm run preview`. Set `VITE_API_BASE_URL` to call a backend directly instead.

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
│   ├── rf-gateway
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

RF Gateway supports two MMDVM hardware paths:

- **MMDVM UART/USB/GPIO** — conventional MMDVM-compatible modems such as MMDVM_HS, MMDVM_HS Dual Hat, ZUMspot, DVMEGA and generic MMDVM boards. MMDVM-Host talks directly to the modem using its `uart` backend.
- **MMDVM-IQ / SoapySDR** — SDR hardware supported by the installed SoapySDR driver and MMDVM-IQ. SXceiver/SoapySX is the first validated SDR path.

Hardware support is capability-driven. A detected device may still reject a frequency or mode that its RF hardware or modem firmware does not support.

---

# Hardware backends

## Conventional MMDVM modems

RF Gateway can discover serial MMDVM candidates from locations including:

```text
/dev/serial/by-id/*
/dev/ttyACM*
/dev/ttyUSB*
/dev/ttyAMA*
/dev/serial0
/dev/serial1
```

The first profile set is modeled after common Pi-Star hardware families:

```text
MMDVM_HS
MMDVM_HS Dual Hat
ZUMspot GPIO
ZUMspot USB
DVMEGA
generic MMDVM USB/UART
generic MMDVM GPIO/UART
```

These devices use the current MMDVM-Host UART configuration model:

```ini
[Modem]
Protocol=uart
UARTPort=/dev/ttyACM0
UARTSpeed=115200
```

Device names are treated as profiles/hints. Actual protocol and RF-band support is determined by the connected modem firmware and RF hardware.

## MMDVM-IQ / SoapySDR

SDR-backed devices use MMDVM-IQ and SoapySDR.

The RF Gateway MMDVM-IQ build currently allows these application-level amateur-band windows:

```text
144.000-148.000 MHz  US 2 m amateur profile
420.000-450.000 MHz  existing upstream UHF range
```

The build script is:

```bash
cd ~/rf-gateway
bash scripts/build-mmdvm-iq.sh
```

The patch is applied only for compilation and the checked-out MMDVM-IQ submodule source is restored afterward.

This does **not** imply that every SDR can transmit across those entire ranges. The selected SoapySDR hardware/driver must also support the requested frequency, and the operator remains responsible for legal band and emission use.

---

# Installation

## Quick start (Raspberry Pi)

The whole setup, in order. Every block can be pasted as is: each one starts with its own `cd`, so it does not matter which directory you are in.

```bash
git clone --recurse-submodules https://github.com/hbohatix/rf-gateway.git ~/rf-gateway
cd ~/rf-gateway
./scripts/install-debian.sh                 # packages, Python venv, MMDVM, vocoders, frontend
nano ~/rf-gateway/backend/.env              # Broadcastify Calls credentials, see below
./scripts/rf-gateway install                # adds the `rf-gateway` command
rf-gateway start --preview                  # start backend + UI
```

Then open `http://<pi-address>:5173`. Day to day you only need `rf-gateway start --preview`, `rf-gateway status` and `rf-gateway stop` (see [Running RF Gateway](#running-rf-gateway)).

> The paths in this README assume the repository is at `~/rf-gateway`. If you cloned it elsewhere, replace `~/rf-gateway` accordingly.

## 1. Clone the repository

```bash
git clone --recurse-submodules \
  https://github.com/hbohatix/rf-gateway.git ~/rf-gateway
```

If the repository was cloned without submodules:

```bash
cd ~/rf-gateway
git submodule sync --recursive
git submodule update --init --recursive
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
cd ~/rf-gateway
./scripts/install-debian.sh
```

The installer performs the main development setup:

- installs system packages,
- enables Mosquitto,
- installs/checks Node.js 22.x,
- initializes Git submodules,
- creates `backend/.venv`,
- installs Python dependencies,
- builds MMDVM-IQ with the RF Gateway amateur-band frequency profile,
- builds MMDVM-Host,
- builds the IMBE and AMBE vocoder wrappers,
- installs frontend dependencies,
- verifies the frontend production build,
- checks FFmpeg,
- checks SoapySDR,
- displays detected USB and PCI devices.

---

## 3. Build the native vocoder wrappers

The installer already builds both wrappers. To rebuild them (for example after updating the repository):

```bash
cd ~/rf-gateway
bash backend/native/build_imbe_wrapper.sh   # IMBE: P25
bash backend/native/build_ambe_wrapper.sh   # AMBE+2 / AMBE: DMR, YSF, NXDN, D-Star
```

They produce these libraries (the `.so` files are libraries, not commands, so they cannot be run):

```text
~/rf-gateway/backend/native/libimbe_vocoder_wrapper.so
~/rf-gateway/backend/native/libambe_vocoder_wrapper.so
```

Check that they exist and export their functions:

```bash
cd ~/rf-gateway
ls -l backend/native/*.so
nm -D backend/native/libimbe_vocoder_wrapper.so | grep rf_gateway_imbe_
nm -D backend/native/libambe_vocoder_wrapper.so | grep rf_gateway_ambe_
```

The UI shows the same thing per mode: a green dot on a mode card means its vocoder is ready.

---

# Broadcastify Calls configuration

Broadcastify Calls API credentials must be provided locally.

Create `~/rf-gateway/backend/.env`:

```bash
nano ~/rf-gateway/backend/.env
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
BROADCASTIFY_CALLS_LIVE_CALLS_PATH=https://api.bcfy.io/calls/v1/live/
BROADCASTIFY_CALLS_CALL_PATH=
BROADCASTIFY_CALLS_GROUP_ARCHIVE_PATH=
```

Use endpoint values and credentials appropriate for your approved Broadcastify Calls API access.

### Calls API developer JWT authentication

**Broadcastify Calls** uses the official `GET https://api.bcfy.io/calls/v1/live/` endpoint and an HS256 JWT (`kid`, `iss`, `iat`, `exp`) signed using `BROADCASTIFY_CALLS_SIGNING_SECRET`. RF Gateway signs calls automatically; it does **not** need, store or automate any website login cookie. The legacy `www.broadcastify.com/calls/apis/live-calls` AJAX endpoint has been removed from the Calls Worker; it returns `403 auth_required` without a website session.

If you set `BROADCASTIFY_CALLS_LIVE_CALLS_PATH` explicitly in your local `backend/.env`, update it to `https://api.bcfy.io/calls/v1/live/` (or remove the key entirely to use the new default). Keep `BASE_URL=https://api.bcfy.io`. Old web endpoints are rejected to prevent leaking a developer JWT to another origin. **Never post your key ID, secret, minted JWT, or `.env` contents in public logs or chat.**

Developer Calls polling now respects a **minimum five-second interval** and uses `playlist_uuid` plus a `pos` cursor; the server's `lastPos` advances the cursor. The web player's `doInit`, `sessionKey`, `systemId` and `sid=0` are not sent. HTTP 401/403 from the developer API requires checking credential configuration, issuer, entitlements or balance, not inventing a browser login flow.

Start by checking local status without showing credentials:

```bash
cd ~/rf-gateway/backend
.venv/bin/python - <<'PY'
# Load backend/.env before importing the cached API client.
import app.main
from app.broadcastify_calls_client import broadcastify_calls_client as client
s = client.configuration_status()
for k in ("configured", "key_id_configured", "signing_secret_configured", "issuer_configured"):
    print(k + ":", s.get(k))
print("live_endpoint_correct:", client.config.live_calls_path.rstrip("/") == "https://api.bcfy.io/calls/v1/live")
PY
```

This does not make a billable API call. Use a **single, deliberate** live query before activating a polling route.


Do **not** commit real secrets.

Recommended permissions:

```bash
chmod 600 ~/rf-gateway/backend/.env
```

The backend loads `backend/.env` at startup.

---

# Running RF Gateway

One command starts and stops both the FastAPI backend and the web UI. Install it once:

```bash
cd ~/rf-gateway
./scripts/rf-gateway install
```

This creates `~/.local/bin/rf-gateway`, a link to this checkout's script. If `rf-gateway` is not found afterwards, open a new login shell, or add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc`. `rf-gateway uninstall` removes the link.

Then, from any directory:

```bash
rf-gateway start --preview      # start backend + UI (built UI: recommended on the Pi)
rf-gateway status               # what is running, health, RF runtime, URLs
rf-gateway stop                 # stop both (and any transmission)
rf-gateway logs -f              # follow the logs
```

`rf-gateway start` without `--preview` runs the UI in Vite development mode (hot reload while editing the code). It is slower on the Pi, and after code updates the browser may need a hard refresh (Ctrl+F5); use `--preview` for normal operation.

**Use either `rf-gateway` or the manual commands below, not both:** they use the same ports (8000 and 5173).

## Updating

```bash
rf-gateway stop
cd ~/rf-gateway
git pull
git submodule update --init --recursive
./scripts/install-debian.sh     # only needed when dependencies or native code changed; safe to re-run
rf-gateway start --preview
```

Then reload the UI in the browser with Ctrl+F5.

## Sharing the SDR with other software

Only one program can use the SXceiver (or any SDR) at a time. Before using it with another application (for example FlowStation), stop RF Gateway:

```bash
rf-gateway stop
```

RF Gateway uses the SDR while transmitting, and probes it whenever the UI loads the device list, so stopping only the transmission is not enough. Start it again with `rf-gateway start --preview` when the SDR is free.

## Commands

| Command | What it does |
|---|---|
| `rf-gateway start` | Starts the backend (uvicorn with auto-reload) and the Vite dev server in the background, waits until both answer, then prints the URLs. Does nothing if RF Gateway is already running. |
| `rf-gateway start --preview` | Builds the frontend (`npm run build`) and serves the build with `vite preview` instead of the dev server; the backend runs without auto-reload. Use this for everyday operation on the Pi. |
| `rf-gateway stop` | Stops both. The backend gets SIGTERM, so FastAPI shuts down the MMDVM runtime and route pipelines cleanly before exiting; anything still running after 15 s is killed. |
| `rf-gateway restart [--preview]` | Stop, then start. Without an option it keeps the previous mode. |
| `rf-gateway status` | Process IDs, ports, `/api/health`, whether the RF runtime is active or transmitting, and the URLs. |
| `rf-gateway logs [backend\|frontend] [-f]` | Last 50 log lines; `-f` follows them. |
| `rf-gateway run [--preview]` | Foreground mode: starts both, shows the logs, and Ctrl+C stops both. `./scripts/run-dev.sh` does the same. |
| `rf-gateway install` / `uninstall` | Adds or removes `~/.local/bin/rf-gateway` (pointing at this checkout). |

After `start`, open the UI at `http://<pi-address>:5173`. The API docs are at `http://<pi-address>:5173/docs` (proxied to the backend).

Files written by the script (all under the git-ignored `backend/data/`):

```text
backend/data/runtime/run/backend.pid
backend/data/runtime/run/frontend.pid
backend/data/runtime/run/mode               dev or preview
backend/data/runtime/logs/backend.log
backend/data/runtime/logs/frontend.log
```

Settings, as environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `RFGW_BACKEND_PORT` | `8000` | FastAPI port |
| `RFGW_FRONTEND_PORT` | `5173` | UI port |
| `RFGW_HOST` | `0.0.0.0` | Address both servers listen on (use `127.0.0.1` to allow local access only) |

```bash
RFGW_FRONTEND_PORT=8080 rf-gateway start --preview
```

If a port is already taken, `start` stops and says by what. RF Gateway started from another checkout (for example a second clone or worktree), or whose PID files are gone, is recognized: `status` shows where it runs from and `stop` stops it. Anything else (for example a backend or Vite started by hand) is only reported; find it with `ss -ltnp | grep -E ':8000|:5173'`.

`rf-gateway install` points `~/.local/bin/rf-gateway` at the checkout it is run from, so run `./scripts/rf-gateway install` again after switching to another clone.

Stopping RF Gateway also stops any active transmission, because the backend shuts the MMDVM runtime down on exit.

---

## Start the backend manually

Only for debugging; normally use `rf-gateway start`. Stop it first (`rf-gateway stop`), because both use the same ports. In one terminal:

```bash
cd ~/rf-gateway/backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Add `--reload` to restart the backend automatically when its code changes. `python -m uvicorn` without `.venv/bin/` fails with `No module named uvicorn`: the packages are installed in the project's virtual environment, not system-wide.

---

## Start the frontend manually

In a second terminal:

```bash
cd ~/rf-gateway/frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

The installer already ran `npm install`; run it again (`cd ~/rf-gateway/frontend && npm install`) only if `package.json` changed. To serve the built UI instead of the development server:

```bash
cd ~/rf-gateway/frontend
npm run build
npm run preview -- --host 0.0.0.0 --port 5173
```

---

# MMDVM runtime

RF Gateway selects the MMDVM runtime path from the chosen RF device.

For an SDR device:

```text
RF Gateway
  -> MMDVM-Host
  -> UDP
  -> MMDVM-IQ
  -> SoapySDR
  -> SDR
  -> RF
```

For a conventional MMDVM modem:

```text
RF Gateway
  -> MMDVM-Host
  -> UART / USB / GPIO serial
  -> MMDVM modem
  -> RF
```

MMDVM-IQ is therefore required only for SDR-backed devices.

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
| 62032 / 62031 | UDP | DMR network (MMDVM-Host / RF Gateway) |
| 3200 / 4200 | UDP | System Fusion network (MMDVM-Host / RF Gateway) |
| 20011 / 20010 | UDP | D-Star network (MMDVM-Host / RF Gateway) |
| 14021 / 14020 | UDP | NXDN network (MMDVM-Host / RF Gateway) |
| 3810 / 4810 | UDP | FM network (MMDVM-Host / RF Gateway) |

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

The API version currently used by the backend is `0.13.x`.

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
ysf
dstar
nxdn
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

Discover currently available RF hardware, including SoapySDR devices and MMDVM-compatible UART/USB/GPIO modems.

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

Direct Soapy access is intentionally blocked while the MMDVM runtime owns the selected SDR hardware.

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

### Broadcastify sign-in / missing `hlsUrl`

Since October 2026, Broadcastify requires sign-in to listen to web feeds. A feed's public HTML may still be reachable, while its HLS session values are absent. An installed `curl` / FFmpeg pair is **not** proof that listening access is available.

For a `broadcastify_live_audio` route, `POST /api/routes/{route_id}/preflight` now tries to resolve the listening session. If no HLS session can be resolved, it reports `state: blocked`, `source_ready: false`, `blocked_reason: source_stream_unavailable`, and an explanatory `error` instead of indicating `SOURCE READY`. This validates session metadata, not continuous audio delivery.

A free Broadcastify login is not automatically an approved programmatic audio API. If direct integration is needed, use an access method explicitly provided/approved by Broadcastify; their static audio URL requires Premium, and the audio feed catalog API requires a license. Listening access alone does not authorize retransmitting a feed over RF. The current RF Gateway HLS client does not implement an authenticated Broadcastify login or the Premium static audio transport.

Run the no-network regression tests:

```bash
cd ~/rf-gateway/backend
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```


## Direct HTTP audio as an independent source

Routes → Add Route can also use a **Direct HTTP Audio (authorized)** URL when you own the source or have permission to programmatically process and transmit it. The existing P25 activity gate/IMBE pipeline is reused. FFmpeg decodes a continuous media stream to 8 kHz 16-bit mono PCM (320 bytes per 20 ms) and reconnects on failure; preflight probes for supported media MIME types. It does **not** unlock Broadcastify website HLS.

To create a direct source in a single unified route setup, use `source_type: "direct_audio"` with `source_url`, `device_id`, `protocol: "p25"`, and `start_now: false`. A running route should be stopped before changing sources. For manual control use **Advanced → Sources → Direct HTTP Audio**.

### `POST /api/sources/broadcastify/probe`

Probe a Broadcastify source URL.

### `GET /api/sources/broadcastify/api-status`

Return Broadcastify Calls API configuration status and Live Audio transport readiness.

### `POST /api/sources/{source_id}/probe`

Re-probe an existing source.

### `DELETE /api/sources/{source_id}`

Delete a source.

---

## Unified Route Setup (recommended)

**One transmitter, one transmit mode.** Routes no longer carry their own protocol. Every route is sent in the transmit mode chosen in the UI (`PUT /api/transmit/mode`, settings from `PUT /api/config/modes`):

- **Start** on a route stops whatever else is on air, then (re)starts MMDVM with exactly the current mode and settings (restarted if anything differs) and starts the source;
- **Stop** stops the route and MMDVM; `POST /api/rf/stop` and `POST /api/transmit/stop` turn everything off;
- changing the mode or its settings while on air restarts the running route in the new mode.

The UI uses the simpler `/api/transmit` API (`GET /api/transmit`, `PUT /api/transmit/mode`, `PUT /api/transmit/device`, `POST /api/transmit/start {source_id}`, `POST /api/transmit/stop`, `GET|POST /api/transmit/sources`, `DELETE /api/transmit/sources/{id}`); it creates one route per source behind the scenes. The route endpoints below remain for scripts.

`POST /api/routes/setup` registers a source and its route in one request (the `protocol` field is stored but the transmit mode decides what goes on air).

The backend preserves existing `sources.json`, `routes.yaml`, and old API endpoints; **no migration or duplicate manual activation** is necessary. An existing source with the same normalized URL is reused.

```bash
# Create/configure a Calls route in one request, without starting RF:
curl -sS -X POST http://127.0.0.1:8000/api/routes/setup \\
  -H 'Content-Type: application/json' \\
  -d '{
    "source_url":"https://www.broadcastify.com/calls/playlists/?uuid=YOUR_UUID",
    "device_id":"YOUR_RF_DEVICE_ID",
    "protocol":"p25",
    "start_now":false
  }' | jq
```

You can instead send `"source_id": "EXISTING_SOURCE_ID"` (not both) and an optional `name`. Source kind is detected from the URL. Setting `start_now: true` **may initiate a real RF transmission** and should only be used intentionally when the operator is authorized to transmit. If preflight fails, the route remains saved and the response includes `start.started: false` and the detailed runtime error.

Pressing **Start** on an existing disabled route now enables and starts it in the same operation. Broadcastify Live Audio sources that require browser sign-in remain blocked; use appropriately licensed Calls API access where applicable.

### Edit or delete routes (API)

`PUT /api/routes/{route_id}/setup` changes a stopped route's name, RF device and source, keeping its ID. `DELETE /api/routes/{route_id}?cleanup_source=true` removes a route and its source when no other route uses it. Deleting a source in the UI (`DELETE /api/transmit/sources/{id}`) stops it and removes its routes first.

**Data safety:** sources and routes are still stored in separate files. The server performs best-effort cleanup after partial failures; this is not a cross-file database transaction. Back up `backend/data/sources.json` and `backend/data/routes.yaml` before testing changes.


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

- React/Vite frontend (FlowStation-style shell, themes, PL/EN)
- FastAPI backend
- SoapySDR discovery
- SXceiver / SoapySX runtime
- MMDVM-IQ startup and telemetry
- MMDVM-Host startup and telemetry
- mode configuration persistence (FM, DMR, YSF, D-Star, NXDN, P25, TETRA)
- Route CRUD and preflight
- Broadcastify Calls source model, polling and queue processing
- FFmpeg audio decoding
- native IMBE wrapper, PCM -> IMBE -> P25 -> physical P25 RF (SXceiver)
- native AMBE+2/AMBE wrapper (OP25 software encoder)
- DMR, YSF DN, D-Star, NXDN and FM framing, accepted by the real MMDVM-Host binary with 0% loss / 0.0% BER (simulated modem, `tools/mmdvm_loopback.py`)
- DMR / YSF / D-Star frames validated with MMDVM-Host's own decoders and decoded back to audio with mbelib (`native/tools/*_frame_check`)
- Live Audio / HTTP / remote SDR -> PCM -> activity gate -> any supported mode
- TX rollover every 150 s for long continuous audio
- remote SDR sources: rtl_tcp (NFM/AM demodulation, squelch), KiwiSDR (validated with a public receiver), UDP/TCP/HTTP/RTSP audio

## In progress / experimental

- on-air validation of DMR / YSF / D-Star / NXDN / FM with real receiving radios
- DVSI AMBE-3000 (ThumbDV / DV3000 / AMBEServer) vocoder backend — implemented from the DVSI packet format, not yet validated with hardware
- YSF VW (full-rate IMBE) mode
- TETRA (not an MMDVM mode)
- authentication/login
- production deployment/service management

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
cd ~/rf-gateway/backend
.venv/bin/python -c 'from app.main import app; print("MAIN IMPORT OK")'
```

## Compile a backend module

```bash
cd ~/rf-gateway/backend
.venv/bin/python -m py_compile app/example.py
```

## Frontend build

```bash
cd ~/rf-gateway/frontend
npm run build
```

## Voice-path checks without RF

Validate the generated frames with MMDVM-Host's own decoders (builds `dmr_frame_check`, `ysf_frame_check`, `dstar_frame_check`):

```bash
cd ~/rf-gateway
bash backend/native/tools/build_frame_checks.sh
cd ~/rf-gateway/backend
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Run a complete transmission through the **real MMDVM-Host binary** with a simulated modem. Nothing is transmitted; MMDVM-Host must not already be running:

```bash
cd ~/rf-gateway/backend
.venv/bin/python -m tools.mmdvm_loopback dmr                 # also: ysf, dstar, nxdn, fm, p25
.venv/bin/python -m tools.mmdvm_loopback dmr --timeslot 1    # DMR frames must land in slot 1 only
.venv/bin/python -m tools.mmdvm_loopback dmr --source 36389d1b --seconds 120   # real audio of a saved source (id prefix), saved mode settings
```

The tool prints MMDVM-Host's log (e.g. `received network voice header … BER: 0.0%`) and the frames MMDVM-Host queued for the modem.

## Frontend lint

```bash
cd ~/rf-gateway/frontend
npm run lint
```

---

# Updating submodules

```bash
cd ~/rf-gateway
git submodule sync --recursive
git submodule update --init --recursive
```

To inspect current submodule revisions:

```bash
cd ~/rf-gateway
git submodule status
```

---

# Typical development startup sequence

```text
1. Start backend + frontend (rf-gateway start)
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
### Calls processing counters

The Calls queue distinguishes **Received / Enqueued / Duplicates** from **Completed / Dequeued / Dropped / Cleared**. Clearing the queue (for example on route stop) no longer makes calls silently disappear from accounting; `total_cleared` tracks removals from that point onward, not historical removals before this version. During a call, the *last P25 records* field reports the latest successful P25 **network handoff** to MMDVM, not proof of transmission on an RF antenna. Actual on-air TX should be checked at MMDVM/radio.

## Calls selectors directly in Routes

The **Routes → Add Route** form can now create/reuse a Calls source directly from:

- An existing saved source (including previously imported Calls playlists).
- A Calls playlist UUID (no Broadcastify webpage lookup).
- One to five Broadcastify Calls group identifiers, e.g. `2-3416,c-223312`.
- An advanced full source URL (legacy Calls, Live Audio, or authorized direct HTTP media).

`POST /api/routes/setup` and `PUT /api/routes/{id}/setup` accept exactly **one** of `source_id`, `source_url`, `playlist_uuid`, or `group_ids`. For group selection use an array of group strings: `"group_ids": ["2-3416", "c-223312"]`. The `broadcastify_calls` worker uses its existing JWT-authenticated `GET /calls/v1/live/` transport with the documented `groups` selector and `pos` cursor. Duplicate selections reuse the same persisted source.

A syntactically valid Calls selector can be saved **without any external request**. The new sources carry `remote_verified: false` because actual playlist/group visibility is confirmed only by a subsequent live API poll, which may be billed. Saving a route does not start the RF transmitter unless `start_now` is explicitly selected.

This does not yet provide a remote, searchable Broadcastify Calls catalog: the exact authenticated discovery endpoint schemas must be confirmed against the user's Developer Portal documentation before implementing listing by county/system. No undocumented API endpoints are invented here.

## Calls catalog and RF TX evidence

**Routes → Add Route → Browse Broadcastify Calls** searches public Calls playlists by
name, and samples of currently active talkgroups and nodes (system/site
coverage) from the public Calls landing page. Entries can be selected without
typing identifiers. The public-playlist listing is broad, but the live-sample
index is **not** a complete list of systems/groups; implementing licensed
full county discovery needs the exact endpoint definitions from
`https://bcfy.io/dev/docs/`. No undocumented Calls API paths are used.
The backend caches each public page for 10 minutes. Choosing a result creates
or reuses a Calls source and uses the already configured developer JWT
when the route subsequently polls for calls. Public discovery itself never
uses the JWT or reads paid Calls records.

**Routes → RF TX Monitor** reports:
- P25 network records and UDP datagrams handed to MMDVM (not proof of RF).
- Current MMDVM-IQ TX ON/OFF indication and per-call TX ON/OFF log event count.
- Runtime errors and MMDVM-Host error lines correlated with a call.
- Optional independent RF energy evidence from an external receiver.

If a separate, calibrated RF receiver or RF power sensor is present, it can
atomically update a JSON file configured via `RF_TX_EVIDENCE_FILE` in
`backend/.env`. Example **format only** (do not fabricate observations):

```json
{
  "observed_at_unix": 1792000000.0,
  "frequency_hz": 438825000,
  "rf_detected": true,
  "power_dbm": -48.2
}
```

The timestamp must be within the P25 handoff interval and the frequency
within 15 kHz of the configured channel to count as an independent RF-energy
observation. Until a real external measuring device is connected, RF is
**UNVERIFIED** even if the modem reports TX ON and UDP handoff succeeds.
An energy detector alone does not decode or verify the P25 modulation/audio.
An MMDVM UART backend may have no IQ TX ON/OFF indications.
