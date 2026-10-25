import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { readStorage, saveToStorage } from "./lib/format";
import { STORAGE_KEYS } from "./lib/modes";

export type Lang = "en" | "pl";

const DICTIONARY = {
  // navigation
  "nav.monitor": { en: "Monitor", pl: "Monitor" },
  "nav.radio": { en: "Radio", pl: "Radio" },
  "nav.sources": { en: "Sources", pl: "Źródła" },
  "nav.system": { en: "System", pl: "System" },
  "page.transmit": { en: "Transmit", pl: "Nadawanie" },
  "page.devices": { en: "RF Devices", pl: "Urządzenia RF" },
  "page.remote_sdr": { en: "Remote SDR", pl: "Zdalne SDR" },
  "page.logs": { en: "MMDVM Log", pl: "Log MMDVM" },
  "page.api": { en: "API docs", pl: "Dokumentacja API" },
  "page.transmit.sub": { en: "Pick a mode, press play on a source", pl: "Wybierz mod, naciśnij ▶ przy źródle" },
  "page.devices.sub": { en: "Detected RF hardware", pl: "Wykryty sprzęt RF" },
  "page.remote_sdr.sub": { en: "rtl_tcp · KiwiSDR · SDR audio streams", pl: "rtl_tcp · KiwiSDR · strumienie audio z SDR" },
  "page.logs.sub": { en: "MMDVM-Host and MMDVM-IQ", pl: "MMDVM-Host i MMDVM-IQ" },
  // status
  "status.backend": { en: "Backend", pl: "Backend" },
  "status.online": { en: "ONLINE", pl: "ONLINE" },
  "status.offline": { en: "OFFLINE", pl: "OFFLINE" },
  "status.connecting": { en: "CONNECTING", pl: "ŁĄCZENIE" },
  "status.runtime": { en: "Runtime", pl: "Środowisko" },
  "status.active": { en: "ACTIVE", pl: "AKTYWNE" },
  "status.stopped": { en: "STOPPED", pl: "ZATRZYMANE" },
  "status.tx": { en: "TX", pl: "TX" },
  "status.ready": { en: "READY", pl: "GOTOWE" },
  "status.starting": { en: "STARTING", pl: "START" },
  "status.unavailable": { en: "UNAVAILABLE", pl: "NIEDOSTĘPNE" },
  "status.not_implemented": { en: "NOT IMPLEMENTED", pl: "BRAK" },
  // dashboard
  "dash.hero.idle": { en: "RF runtime stopped", pl: "Środowisko RF zatrzymane" },
  "dash.hero.idle.sub": { en: "Choose a protocol and RF device, then start the runtime.", pl: "Wybierz protokół i urządzenie RF, a potem uruchom środowisko." },
  "dash.hero.active": { en: "RF runtime active", pl: "Środowisko RF aktywne" },
  "dash.hero.tx": { en: "Transmitting", pl: "Nadawanie" },
  "dash.sources": { en: "Sources", pl: "Źródła" },
  "dash.sources.sub": { en: "audio sources", pl: "źródeł audio" },
  "dash.routes": { en: "Routes", pl: "Trasy" },
  "dash.routes.sub": { en: "source → RF", pl: "źródło → RF" },
  "dash.devices": { en: "RF devices", pl: "Urządzenia RF" },
  "dash.devices.sub": { en: "MMDVM / SDR", pl: "MMDVM / SDR" },
  "dash.mode": { en: "Mode", pl: "Tryb" },
  "dash.voice_paths": { en: "Voice paths", pl: "Ścieżki głosu" },
  "dash.voice_paths.sub": { en: "Which protocols can carry source audio", pl: "Które protokoły mogą przenosić audio ze źródeł" },
  "dash.quick": { en: "Quick actions", pl: "Szybkie akcje" },
  "dash.open_routes": { en: "Manage routes", pl: "Zarządzaj trasami" },
  "dash.add_sdr": { en: "Add remote SDR", pl: "Dodaj zdalne SDR" },
  "dash.configure_rf": { en: "Configure RF output", pl: "Konfiguruj wyjście RF" },
  // RF output
  "rf.protocol": { en: "Protocol", pl: "Protokół" },
  "rf.device": { en: "RF device", pl: "Urządzenie RF" },
  "rf.no_device": { en: "No RF device selected", pl: "Nie wybrano urządzenia RF" },
  "rf.disabled": { en: "RF output is disabled. Select a protocol to configure it.", pl: "Wyjście RF wyłączone. Wybierz protokół, aby go skonfigurować." },
  "rf.start": { en: "Start", pl: "Start" },
  "rf.stop": { en: "Stop", pl: "Stop" },
  "rf.calibrate": { en: "Calibrate", pl: "Kalibracja" },
  "rf.refresh": { en: "Refresh", pl: "Odśwież" },
  "rf.scanning": { en: "Scanning…", pl: "Skanowanie…" },
  "rf.no_devices": { en: "No RF devices detected.", pl: "Nie wykryto urządzeń RF." },
  "rf.autosave": { en: "Settings are saved automatically.", pl: "Ustawienia zapisują się automatycznie." },
  // telemetry
  "tel.channel": { en: "Channel", pl: "Kanał" },
  "tel.modem_mode": { en: "Modem mode", pl: "Tryb modemu" },
  "tel.sdr_center": { en: "SDR center", pl: "Środek SDR" },
  "tel.digital_if": { en: "Digital IF", pl: "Cyfrowa p.cz." },
  "tel.sample_rate": { en: "Sample rate", pl: "Próbkowanie" },
  "tel.iq_streams": { en: "IQ streams", pl: "Strumienie IQ" },
  "tel.processes": { en: "Processes", pl: "Procesy" },
  "tel.last_error": { en: "Last error", pl: "Ostatni błąd" },
  "logs.refresh": { en: "Refresh", pl: "Odśwież" },
  "logs.autorefresh": { en: "Auto-refresh", pl: "Auto-odświeżanie" },
  "logs.empty": { en: "No log lines yet — start the RF runtime.", pl: "Brak wpisów — uruchom środowisko RF." },
  // remote SDR
  "sdr.kind": { en: "Receiver type", pl: "Typ odbiornika" },
  "sdr.host": { en: "Host", pl: "Host" },
  "sdr.port": { en: "Port", pl: "Port" },
  "sdr.frequency": { en: "Frequency (MHz)", pl: "Częstotliwość (MHz)" },
  "sdr.modulation": { en: "Demodulation", pl: "Demodulacja" },
  "sdr.gain": { en: "Gain", pl: "Wzmocnienie" },
  "sdr.squelch": { en: "Squelch", pl: "Blokada szumów" },
  "sdr.audio_gain": { en: "Audio gain", pl: "Wzmocnienie audio" },
  "sdr.url": { en: "Stream URL", pl: "Adres strumienia" },
  "sdr.format": { en: "Raw PCM format", pl: "Format surowego PCM" },
  "sdr.rate": { en: "Sample rate", pl: "Częst. próbkowania" },
  "sdr.name": { en: "Source name", pl: "Nazwa źródła" },
  "sdr.probe": { en: "Probe", pl: "Sprawdź" },
  "sdr.save": { en: "Save as source", pl: "Zapisz jako źródło" },
  "sdr.saved": { en: "Saved. It is now on the Transmit page.", pl: "Zapisano. Jest teraz na stronie Nadawanie." },
  "sdr.preview": { en: "Generated URL", pl: "Wygenerowany adres" },
  "sdr.legal": {
    en: "Only retransmit receivers and audio you are authorized to use, on frequencies you are licensed for.",
    pl: "Retransmituj tylko odbiorniki i audio, do których masz prawo, i tylko na częstotliwościach, na które masz pozwolenie.",
  },
  // transmit page
  "tx.sources": { en: "Sources", pl: "Źródła" },
  "tx.sources.sub": { en: "One goes on air at a time", pl: "Na antenie jest jedno naraz" },
  "tx.url": { en: "Source URL", pl: "Adres źródła" },
  "tx.name_optional": { en: "Name (optional)", pl: "Nazwa (opcjonalnie)" },
  "tx.add": { en: "Add", pl: "Dodaj" },
  "tx.adding": { en: "Checking…", pl: "Sprawdzanie…" },
  "tx.added": { en: "Added", pl: "Dodano" },
  "tx.no_sources": { en: "No sources yet. Paste a Broadcastify, stream or remote SDR URL above.", pl: "Brak źródeł. Wklej wyżej adres Broadcastify, strumienia albo zdalnego SDR." },
  "tx.choose_mode": { en: "Choose a transmit mode on the right first.", pl: "Najpierw wybierz po prawej mod nadawania." },
  "tx.transmit": { en: "Transmit", pl: "Nadawaj" },
  "tx.starting": { en: "Starting…", pl: "Uruchamianie…" },
  "tx.delete": { en: "Delete source", pl: "Usuń źródło" },
  "tx.delete_confirm": { en: "Delete source", pl: "Usunąć źródło" },
  "tx.on_air": { en: "ON AIR", pl: "NA ANTENIE" },
  "tx.off": { en: "OFF", pl: "WYŁĄCZONY" },
  "tx.no_mode": { en: "No transmit mode", pl: "Brak modu nadawania" },
  "tx.nothing": { en: "Nothing on air", pl: "Nic nie nadaje" },
  "tx.stop_all": { en: "Turn everything off", pl: "Wyłącz wszystko" },
  "tx.mode": { en: "Transmit mode", pl: "Mod nadawania" },
  "tx.mode.sub": { en: "Every source is sent like this. Changes apply immediately.", pl: "Każde źródło idzie w tym modzie. Zmiany działają od razu." },
  "tx.device_auto": { en: "Automatic (first usable)", pl: "Automatycznie (pierwsze dostępne)" },
  "tx.legal": { en: "Operate only on frequencies you are licensed for.", pl: "Nadawaj tylko na częstotliwościach, na które masz pozwolenie." },
  // misc
  "theme.dark": { en: "Dark", pl: "Ciemny" },
  "theme.light": { en: "Light", pl: "Jasny" },
  "theme.blue": { en: "Blue", pl: "Niebieski" },
  "common.collapse": { en: "Collapse sidebar", pl: "Zwiń panel" },
} as const;

export type TranslationKey = keyof typeof DICTIONARY;

type I18nValue = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: TranslationKey) => string;
};

const I18nContext = createContext<I18nValue | null>(null);

function initialLang(): Lang {
  const stored = readStorage(STORAGE_KEYS.lang);
  if (stored === "en" || stored === "pl") {
    return stored;
  }
  return navigator.language?.toLowerCase().startsWith("pl") ? "pl" : "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    saveToStorage(STORAGE_KEYS.lang, next);
    document.documentElement.lang = next;
  }, []);

  const t = useCallback((key: TranslationKey) => DICTIONARY[key]?.[lang] ?? key, [lang]);

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (!value) {
    throw new Error("useI18n must be used inside I18nProvider");
  }
  return value;
}
