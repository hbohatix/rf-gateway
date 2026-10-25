export type Protocol = "fm" | "dmr" | "p25" | "ysf" | "dstar" | "nxdn" | "tetra";

export type FMConfig = {
  frequency: string;
  channelSpacing: "12.5" | "25";
  deviation: "2.5" | "5";
  txCtcss: string;
  rxCtcss: string;
  preEmphasis: "on" | "off";
  audioGain: string;
};

export type AmbeVocoder = "software" | "dv3000_serial" | "ambeserver";

export type DMRConfig = {
  frequency: string;
  colorCode: string;
  timeslot: "1" | "2";
  talkgroup: string;
  radioId: string;
  callType: "group" | "private";
  vocoder: AmbeVocoder;
  vocoderDevice: string;
  vocoderBaud: string;
  vocoderHost: string;
  vocoderPort: string;
  vocoderGainDb: string;
};

export type P25Config = {
  frequency: string;
  nac: string;
  talkgroup: string;
  radioId: string;
  modulation: "c4fm" | "cqpsk";
};

export type YSFConfig = {
  frequency: string;
  callsign: string;
  destination: string;
  dgId: string;
  lowDeviation: "on" | "off";
  vocoder: AmbeVocoder;
  vocoderDevice: string;
  vocoderBaud: string;
  vocoderHost: string;
  vocoderPort: string;
  vocoderGainDb: string;
};

export type DStarConfig = {
  frequency: string;
  callsign: string;
  suffix: string;
  yourCall: string;
  module: string;
  message: string;
  vocoderGainDb: string;
};

export type NXDNConfig = {
  frequency: string;
  ran: string;
  talkgroup: string;
  radioId: string;
  callType: "group" | "private";
  vocoder: AmbeVocoder;
  vocoderDevice: string;
  vocoderBaud: string;
  vocoderHost: string;
  vocoderPort: string;
  vocoderGainDb: string;
};

export type TETRAConfig = {
  frequency: string;
  mode: "dmo" | "tmo";
  mcc: string;
  mnc: string;
  colorCode: string;
  gssi: string;
};

export type VoiceCapability = {
  protocol: Protocol;
  audio_input_supported: boolean;
  bridge_state: string;
  blocking_reason: string | null;
  vocoder?: {
    name?: string;
    available?: boolean;
    backend?: string;
    error?: string | null;
  };
};

export type VoiceCapabilities = Partial<Record<Protocol, VoiceCapability>>;
