export type Protocol = "fm" | "dmr" | "p25" | "tetra";

export type FMConfig = {
  frequency: string;
  channelSpacing: "12.5" | "25";
  deviation: "2.5" | "5";
  txCtcss: string;
  rxCtcss: string;
  preEmphasis: "on" | "off";
};

export type DMRConfig = {
  frequency: string;
  colorCode: string;
  timeslot: "1" | "2";
  talkgroup: string;
  radioId: string;
};

export type P25Config = {
  frequency: string;
  nac: string;
  talkgroup: string;
  radioId: string;
  modulation: "c4fm" | "cqpsk";
};

export type TETRAConfig = {
  frequency: string;
  mode: "dmo" | "tmo";
  mcc: string;
  mnc: string;
  colorCode: string;
  gssi: string;
};