// Minimal stroke icon set (24x24 grid), styled through currentColor.
const PATHS: Record<string, string> = {
  dashboard: "M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-4H4zM14 7h6V4h-6z",
  routes: "M6 4v6a4 4 0 0 0 4 4h4a4 4 0 0 1 4 4v2M6 4 3 7M6 4l3 3M18 20l-3-3M18 20l3-3",
  telemetry: "M3 12h4l3-7 4 14 3-7h4",
  radio: "M4.9 19.1a10 10 0 0 1 0-14.2M19.1 4.9a10 10 0 0 1 0 14.2M7.8 16.2a6 6 0 0 1 0-8.4M16.2 7.8a6 6 0 0 1 0 8.4M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  device: "M5 7h14v10H5zM8 17v3M16 17v3M9 4l3 3 3-3M8.5 11h.01M12 11h3",
  source: "M4 6c0-1.1 3.6-2 8-2s8 .9 8 2-3.6 2-8 2-8-.9-8-2zM4 6v6c0 1.1 3.6 2 8 2s8-.9 8-2V6M4 12v6c0 1.1 3.6 2 8 2s8-.9 8-2v-6",
  sdr: "M3 20h18M7 20l5-14 5 14M9.5 13h5M12 6V3M8.5 4.5a5 5 0 0 1 7 0",
  log: "M6 4h9l3 3v13H6zM9 10h6M9 14h6M9 17h4",
  api: "M8 8l-4 4 4 4M16 8l4 4-4 4M14 5l-4 14",
  chevron_left: "M15 6l-6 6 6 6",
  chevron_right: "M9 6l6 6-6 6",
  menu: "M4 6h16M4 12h16M4 18h16",
  play: "M8 5v14l11-7z",
  stop: "M7 7h10v10H7z",
  refresh: "M20 11a8 8 0 0 0-14.9-3M4 5v3h3M4 13a8 8 0 0 0 14.9 3M20 19v-3h-3",
  wave: "M2 12c2-4 4-4 6 0s4 4 6 0 4-4 6 0 2 2 2 2",
  check: "M5 12l5 5 9-10",
  plus: "M12 5v14M5 12h14",
  search: "M11 18a7 7 0 1 1 0-14 7 7 0 0 1 0 14zM20 20l-4-4",
  calibrate: "M12 3v3M12 18v3M3 12h3M18 12h3M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
};

export type IconName = keyof typeof PATHS;

export default function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
