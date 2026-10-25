import type { DMRConfig, DStarConfig, FMConfig, NXDNConfig, P25Config, Protocol, TETRAConfig, YSFConfig } from "../types/radio";
import { frequencyToHz, hzToMHzString, optionalNumber, optionalNumberToString, requiredInteger } from "./format";

export const PROTOCOLS: Protocol[] = ["fm", "dmr", "ysf", "dstar", "nxdn", "p25", "tetra"];

export const STORAGE_KEYS = {
  activeProtocol: "rf-gateway.activeProtocol",
  selectedDeviceId: "rf-gateway.selectedDeviceId",
  fmConfig: "rf-gateway.fmConfig",
  dmrConfig: "rf-gateway.dmrConfig",
  p25Config: "rf-gateway.p25Config",
  tetraConfig: "rf-gateway.tetraConfig",
  ysfConfig: "rf-gateway.ysfConfig",
  dstarConfig: "rf-gateway.dstarConfig",
  nxdnConfig: "rf-gateway.nxdnConfig",
  page: "rf-gateway.page",
  theme: "rf-gateway.theme",
  lang: "rf-gateway.lang",
  sidebar: "rf-gateway.sidebarCollapsed",
} as const;

export const DEFAULT_FM_CONFIG: FMConfig = {
  frequency: "145.500000",
  channelSpacing: "12.5",
  deviation: "2.5",
  txCtcss: "",
  rxCtcss: "",
  preEmphasis: "on",
  audioGain: "1.0",
};

export const DEFAULT_DMR_CONFIG: DMRConfig = {
  frequency: "438.800000",
  colorCode: "1",
  timeslot: "2",
  talkgroup: "260",
  radioId: "2601292",
  callType: "group",
  vocoder: "software",
  vocoderDevice: "/dev/ttyUSB0",
  vocoderBaud: "460800",
  vocoderHost: "127.0.0.1",
  vocoderPort: "2460",
  vocoderGainDb: "0",
};

export const DEFAULT_P25_CONFIG: P25Config = {
  frequency: "145.500000",
  nac: "293",
  talkgroup: "260",
  radioId: "2601292",
  modulation: "c4fm",
};

export const DEFAULT_YSF_CONFIG: YSFConfig = {
  frequency: "438.800000",
  callsign: "SP5OPS",
  destination: "ALL",
  dgId: "0",
  lowDeviation: "off",
  vocoder: "software",
  vocoderDevice: "/dev/ttyUSB0",
  vocoderBaud: "460800",
  vocoderHost: "127.0.0.1",
  vocoderPort: "2460",
  vocoderGainDb: "0",
};

export const DEFAULT_DSTAR_CONFIG: DStarConfig = {
  frequency: "438.800000",
  callsign: "SP5OPS",
  suffix: "RFGW",
  yourCall: "CQCQCQ",
  module: "B",
  message: "RF Gateway",
  vocoderGainDb: "0",
};

export const DEFAULT_NXDN_CONFIG: NXDNConfig = {
  frequency: "438.800000",
  ran: "1",
  talkgroup: "65000",
  radioId: "1234",
  callType: "group",
  vocoder: "software",
  vocoderDevice: "/dev/ttyUSB0",
  vocoderBaud: "460800",
  vocoderHost: "127.0.0.1",
  vocoderPort: "2460",
  vocoderGainDb: "0",
};

export const DEFAULT_TETRA_CONFIG: TETRAConfig = {
  frequency: "430.000000",
  mode: "dmo",
  mcc: "901",
  mnc: "9999",
  colorCode: "1",
  gssi: "1",
};

export const PROTOCOL_INFO: Record<Protocol, { name: string; description: string; codec: string }> = {
  fm: { name: "FM", description: "Analog FM", codec: "PCM" },
  dmr: { name: "DMR", description: "Digital Mobile Radio", codec: "AMBE+2" },
  ysf: { name: "YSF", description: "Yaesu System Fusion (DN)", codec: "AMBE+2" },
  dstar: { name: "D-Star", description: "JARL D-Star DV", codec: "AMBE" },
  nxdn: { name: "NXDN", description: "NXDN 4800 (Kenwood/Icom)", codec: "AMBE+2" },
  p25: { name: "P25", description: "APCO Project 25", codec: "IMBE" },
  tetra: { name: "TETRA", description: "Terrestrial Trunked Radio", codec: "ACELP" },
};

export function isProtocol(value: unknown): value is Protocol {
  return typeof value === "string" && (PROTOCOLS as string[]).includes(value);
}

// ----------------------------------------------------------- API payloads

export function fmPayload(config: FMConfig) {
  return {
    protocol: "fm" as const,
    frequency_hz: frequencyToHz(config.frequency),
    channel_spacing_khz: Number(config.channelSpacing),
    deviation_khz: Number(config.deviation),
    tx_ctcss_hz: optionalNumber(config.txCtcss),
    rx_ctcss_hz: optionalNumber(config.rxCtcss),
    pre_emphasis: config.preEmphasis === "on",
    audio_gain: optionalNumber(config.audioGain) ?? 1.0,
  };
}

export function dmrPayload(config: DMRConfig) {
  return {
    protocol: "dmr" as const,
    frequency_hz: frequencyToHz(config.frequency),
    color_code: requiredInteger(config.colorCode, "Color Code"),
    timeslot: requiredInteger(config.timeslot, "Timeslot"),
    talkgroup: requiredInteger(config.talkgroup, "Talkgroup"),
    radio_id: requiredInteger(config.radioId, "Radio ID"),
    call_type: config.callType,
    vocoder: config.vocoder,
    vocoder_device: config.vocoderDevice.trim() || null,
    vocoder_baud: optionalNumber(config.vocoderBaud),
    vocoder_host: config.vocoderHost.trim() || null,
    vocoder_port: optionalNumber(config.vocoderPort),
    vocoder_gain_db: optionalNumber(config.vocoderGainDb) ?? 0,
  };
}

export function ysfPayload(config: YSFConfig) {
  const callsign = config.callsign.trim().toUpperCase();
  if (!callsign) {
    throw new Error("Callsign is required");
  }
  return {
    protocol: "ysf" as const,
    frequency_hz: frequencyToHz(config.frequency),
    callsign,
    destination: config.destination.trim().toUpperCase() || "ALL",
    dg_id: requiredInteger(config.dgId, "DG-ID"),
    low_deviation: config.lowDeviation === "on",
    vocoder: config.vocoder,
    vocoder_device: config.vocoderDevice.trim() || null,
    vocoder_baud: optionalNumber(config.vocoderBaud),
    vocoder_host: config.vocoderHost.trim() || null,
    vocoder_port: optionalNumber(config.vocoderPort),
    vocoder_gain_db: optionalNumber(config.vocoderGainDb) ?? 0,
  };
}

export function dstarPayload(config: DStarConfig) {
  const callsign = config.callsign.trim().toUpperCase();
  if (callsign.length < 3) {
    throw new Error("Callsign is required");
  }
  return {
    protocol: "dstar" as const,
    frequency_hz: frequencyToHz(config.frequency),
    callsign,
    suffix: config.suffix.trim().toUpperCase(),
    your_call: config.yourCall.trim().toUpperCase() || "CQCQCQ",
    module: (config.module.trim().toUpperCase() || "B").slice(0, 1),
    message: config.message.slice(0, 20),
    vocoder_gain_db: optionalNumber(config.vocoderGainDb) ?? 0,
  };
}

export function nxdnPayload(config: NXDNConfig) {
  return {
    protocol: "nxdn" as const,
    frequency_hz: frequencyToHz(config.frequency),
    ran: requiredInteger(config.ran, "RAN"),
    talkgroup: requiredInteger(config.talkgroup, "Talkgroup"),
    radio_id: requiredInteger(config.radioId, "Unit ID"),
    call_type: config.callType,
    vocoder: config.vocoder,
    vocoder_device: config.vocoderDevice.trim() || null,
    vocoder_baud: optionalNumber(config.vocoderBaud),
    vocoder_host: config.vocoderHost.trim() || null,
    vocoder_port: optionalNumber(config.vocoderPort),
    vocoder_gain_db: optionalNumber(config.vocoderGainDb) ?? 0,
  };
}

export function p25Payload(config: P25Config) {
  return {
    protocol: "p25" as const,
    frequency_hz: frequencyToHz(config.frequency),
    nac: config.nac.trim(),
    talkgroup: requiredInteger(config.talkgroup, "Talkgroup"),
    radio_id: requiredInteger(config.radioId, "Radio ID"),
    modulation: config.modulation,
  };
}

export function tetraPayload(config: TETRAConfig) {
  return {
    protocol: "tetra" as const,
    frequency_hz: frequencyToHz(config.frequency),
    mode: config.mode,
    mcc: config.mcc.trim(),
    mnc: config.mnc.trim(),
    color_code: requiredInteger(config.colorCode, "Color Code"),
    gssi: requiredInteger(config.gssi, "GSSI"),
  };
}

// ------------------------------------------------------- saved -> form

type Saved = Record<string, unknown>;

const str = (value: unknown, fallback: string) =>
  value === null || value === undefined || value === "" ? fallback : String(value);

export function fmFromSaved(saved: Saved): FMConfig {
  return {
    frequency: hzToMHzString(Number(saved.frequency_hz)),
    channelSpacing: Number(saved.channel_spacing_khz) === 25 ? "25" : "12.5",
    deviation: Number(saved.deviation_khz) === 5 ? "5" : "2.5",
    txCtcss: optionalNumberToString(saved.tx_ctcss_hz as number | null),
    rxCtcss: optionalNumberToString(saved.rx_ctcss_hz as number | null),
    preEmphasis: saved.pre_emphasis === false ? "off" : "on",
    audioGain: str(saved.audio_gain, DEFAULT_FM_CONFIG.audioGain),
  };
}

export function dmrFromSaved(saved: Saved): DMRConfig {
  const vocoder = str(saved.vocoder, "software");
  return {
    frequency: hzToMHzString(Number(saved.frequency_hz)),
    colorCode: str(saved.color_code, "1"),
    timeslot: Number(saved.timeslot) === 1 ? "1" : "2",
    talkgroup: str(saved.talkgroup, DEFAULT_DMR_CONFIG.talkgroup),
    radioId: str(saved.radio_id, DEFAULT_DMR_CONFIG.radioId),
    callType: saved.call_type === "private" ? "private" : "group",
    vocoder: vocoder === "dv3000_serial" || vocoder === "ambeserver" ? vocoder : "software",
    vocoderDevice: str(saved.vocoder_device, DEFAULT_DMR_CONFIG.vocoderDevice),
    vocoderBaud: str(saved.vocoder_baud, DEFAULT_DMR_CONFIG.vocoderBaud),
    vocoderHost: str(saved.vocoder_host, DEFAULT_DMR_CONFIG.vocoderHost),
    vocoderPort: str(saved.vocoder_port, DEFAULT_DMR_CONFIG.vocoderPort),
    vocoderGainDb: str(saved.vocoder_gain_db, "0"),
  };
}

export function ysfFromSaved(saved: Saved): YSFConfig {
  const vocoder = str(saved.vocoder, "software");
  return {
    frequency: hzToMHzString(Number(saved.frequency_hz)),
    callsign: str(saved.callsign, DEFAULT_YSF_CONFIG.callsign),
    destination: str(saved.destination, "ALL"),
    dgId: str(saved.dg_id, "0"),
    lowDeviation: saved.low_deviation ? "on" : "off",
    vocoder: vocoder === "dv3000_serial" || vocoder === "ambeserver" ? vocoder : "software",
    vocoderDevice: str(saved.vocoder_device, DEFAULT_YSF_CONFIG.vocoderDevice),
    vocoderBaud: str(saved.vocoder_baud, DEFAULT_YSF_CONFIG.vocoderBaud),
    vocoderHost: str(saved.vocoder_host, DEFAULT_YSF_CONFIG.vocoderHost),
    vocoderPort: str(saved.vocoder_port, DEFAULT_YSF_CONFIG.vocoderPort),
    vocoderGainDb: str(saved.vocoder_gain_db, "0"),
  };
}

export function dstarFromSaved(saved: Saved): DStarConfig {
  return {
    frequency: hzToMHzString(Number(saved.frequency_hz)),
    callsign: str(saved.callsign, DEFAULT_DSTAR_CONFIG.callsign),
    suffix: str(saved.suffix, DEFAULT_DSTAR_CONFIG.suffix),
    yourCall: str(saved.your_call, "CQCQCQ"),
    module: str(saved.module, "B"),
    message: str(saved.message, DEFAULT_DSTAR_CONFIG.message),
    vocoderGainDb: str(saved.vocoder_gain_db, "0"),
  };
}

export function nxdnFromSaved(saved: Saved): NXDNConfig {
  const vocoder = str(saved.vocoder, "software");
  return {
    frequency: hzToMHzString(Number(saved.frequency_hz)),
    ran: str(saved.ran, "1"),
    talkgroup: str(saved.talkgroup, DEFAULT_NXDN_CONFIG.talkgroup),
    radioId: str(saved.radio_id, DEFAULT_NXDN_CONFIG.radioId),
    callType: saved.call_type === "private" ? "private" : "group",
    vocoder: vocoder === "dv3000_serial" || vocoder === "ambeserver" ? vocoder : "software",
    vocoderDevice: str(saved.vocoder_device, DEFAULT_NXDN_CONFIG.vocoderDevice),
    vocoderBaud: str(saved.vocoder_baud, DEFAULT_NXDN_CONFIG.vocoderBaud),
    vocoderHost: str(saved.vocoder_host, DEFAULT_NXDN_CONFIG.vocoderHost),
    vocoderPort: str(saved.vocoder_port, DEFAULT_NXDN_CONFIG.vocoderPort),
    vocoderGainDb: str(saved.vocoder_gain_db, "0"),
  };
}

export function p25FromSaved(saved: Saved): P25Config {
  return {
    frequency: hzToMHzString(Number(saved.frequency_hz)),
    nac: str(saved.nac, "293"),
    talkgroup: str(saved.talkgroup, DEFAULT_P25_CONFIG.talkgroup),
    radioId: str(saved.radio_id, DEFAULT_P25_CONFIG.radioId),
    modulation: saved.modulation === "cqpsk" ? "cqpsk" : "c4fm",
  };
}

export function tetraFromSaved(saved: Saved): TETRAConfig {
  return {
    frequency: hzToMHzString(Number(saved.frequency_hz)),
    mode: saved.mode === "tmo" ? "tmo" : "dmo",
    mcc: str(saved.mcc, DEFAULT_TETRA_CONFIG.mcc),
    mnc: str(saved.mnc, DEFAULT_TETRA_CONFIG.mnc),
    colorCode: str(saved.color_code, "1"),
    gssi: str(saved.gssi, "1"),
  };
}
