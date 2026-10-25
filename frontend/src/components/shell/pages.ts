import type { TranslationKey } from "../../i18n";

export type PageId =
  | "dashboard"
  | "routes"
  | "telemetry"
  | "modes"
  | "devices"
  | "remote_sdr"
  | "sources"
  | "logs";

export type Theme = "dark" | "light" | "blue";

export const PAGE_TITLES: Record<PageId, { title: TranslationKey; sub: TranslationKey }> = {
  dashboard: { title: "page.dashboard", sub: "page.dashboard.sub" },
  routes: { title: "page.routes", sub: "page.routes.sub" },
  telemetry: { title: "page.telemetry", sub: "page.telemetry.sub" },
  modes: { title: "page.modes", sub: "page.modes.sub" },
  devices: { title: "page.devices", sub: "page.devices.sub" },
  remote_sdr: { title: "page.remote_sdr", sub: "page.remote_sdr.sub" },
  sources: { title: "page.sources", sub: "page.sources.sub" },
  logs: { title: "page.logs", sub: "page.logs.sub" },
};
