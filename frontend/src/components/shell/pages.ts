import type { TranslationKey } from "../../i18n";

export type PageId = "transmit" | "devices" | "remote_sdr" | "logs";

export type Theme = "dark" | "light" | "blue";

export const PAGE_TITLES: Record<PageId, { title: TranslationKey; sub: TranslationKey }> = {
  transmit: { title: "page.transmit", sub: "page.transmit.sub" },
  devices: { title: "page.devices", sub: "page.devices.sub" },
  remote_sdr: { title: "page.remote_sdr", sub: "page.remote_sdr.sub" },
  logs: { title: "page.logs", sub: "page.logs.sub" },
};
