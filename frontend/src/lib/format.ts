import type { RFDevice } from "../types/rfDevice";

export function frequencyToHz(frequency: string): number {
  const mhz = Number(frequency);
  if (!Number.isFinite(mhz) || mhz <= 0) {
    throw new Error("Invalid frequency");
  }
  return Math.round(mhz * 1_000_000);
}

export function hzToMHzString(frequencyHz: number): string {
  return (frequencyHz / 1_000_000).toFixed(6);
}

export function formatFrequency(frequencyHz: number | null | undefined, digits = 4): string {
  if (frequencyHz === null || frequencyHz === undefined) {
    return "—";
  }
  return `${(frequencyHz / 1_000_000).toFixed(digits)} MHz`;
}

export function formatSignedFrequency(frequencyHz: number | null | undefined): string {
  if (frequencyHz === null || frequencyHz === undefined) {
    return "—";
  }
  const sign = frequencyHz > 0 ? "+" : "";
  if (Math.abs(frequencyHz) >= 1000) {
    return `${sign}${(frequencyHz / 1000).toFixed(3)} kHz`;
  }
  return `${sign}${frequencyHz.toFixed(0)} Hz`;
}

export function formatSampleRate(sampleRate: number | null | undefined): string {
  if (sampleRate === null || sampleRate === undefined) {
    return "—";
  }
  return `${(sampleRate / 1000).toFixed(0)} kS/s`;
}

export function optionalNumberToString(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

export function requiredInteger(value: string, fieldName: string): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) {
    throw new Error(`${fieldName} must be an integer`);
  }
  return parsed;
}

export function optionalNumber(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") {
    return null;
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    throw new Error(`Invalid numeric value: ${value}`);
  }
  return parsed;
}

export function getDeviceDisplayName(device: RFDevice): string {
  if (device.driver.toLowerCase() === "sx") {
    return "SXceiver";
  }
  return device.label.trim().length > 0 ? device.label : device.driver;
}

export function loadFromStorage<T>(key: string, defaultValue: T): T {
  try {
    const storedValue = localStorage.getItem(key);
    if (!storedValue) {
      return defaultValue;
    }
    const parsed = JSON.parse(storedValue) as T;
    if (parsed && typeof parsed === "object" && defaultValue && typeof defaultValue === "object") {
      // Fill in fields added after the value was stored.
      return { ...defaultValue, ...parsed };
    }
    return parsed;
  } catch {
    return defaultValue;
  }
}

export function saveToStorage(key: string, value: unknown): void {
  try {
    if (value === null || value === undefined) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, typeof value === "string" ? value : JSON.stringify(value));
    }
  } catch {
    // Storage can be unavailable (private mode); the UI still works.
  }
}

export function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
