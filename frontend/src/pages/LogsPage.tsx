import { useEffect, useRef, useState } from "react";
import Icon from "../components/Icon";
import { useI18n } from "../i18n";
import { apiFetch, errorMessage } from "../lib/api";

type LogsResponse = { mmdvm_iq: string; mmdvm_host: string };
type Source = "mmdvm_host" | "mmdvm_iq";

function levelOf(line: string): string {
  // MMDVM log lines start with "M: 2026-10-25 ..." (level letter).
  const match = /^([DMIWEF]):/.exec(line);
  return match ? match[1] : "M";
}

export default function LogsPage() {
  const { t } = useI18n();
  const [source, setSource] = useState<Source>("mmdvm_host");
  const [logs, setLogs] = useState<LogsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [auto, setAuto] = useState(true);
  const [filter, setFilter] = useState("");
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      apiFetch<LogsResponse>("/api/mmdvm/logs?lines=400")
        .then((data) => {
          if (!cancelled) {
            setLogs(data);
            setError(null);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            setError(errorMessage(err));
          }
        });
    void load();
    const timer = auto ? window.setInterval(() => void load(), 2000) : undefined;
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearInterval(timer);
      }
    };
  }, [auto, reloadKey]);

  const lines = (logs?.[source] ?? "")
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .filter((line) => !filter || line.toLowerCase().includes(filter.toLowerCase()));

  useEffect(() => {
    const wrap = wrapRef.current;
    if (wrap && auto) {
      wrap.scrollTop = wrap.scrollHeight;
    }
  }, [lines.length, auto]);

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-title">{t("page.logs")}</span>
        <div className="seg" style={{ marginLeft: 8 }}>
          {(["mmdvm_host", "mmdvm_iq"] as Source[]).map((option) => (
            <button key={option} type="button" className={source === option ? "active" : ""} onClick={() => setSource(option)}>
              {option === "mmdvm_host" ? "MMDVM-Host" : "MMDVM-IQ"}
            </button>
          ))}
        </div>
        <div className="card-actions">
          <input
            placeholder="filter…"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            style={{ width: 180, minHeight: 28 }}
          />
          <button type="button" className="btn btn-sm" onClick={() => setReloadKey((value) => value + 1)}>
            <Icon name="refresh" /> {t("logs.refresh")}
          </button>
        </div>
      </div>
      {error && (
        <div className="card-body" style={{ paddingBottom: 0 }}>
          <div className="banner banner-danger">{error}</div>
        </div>
      )}
      <div className="log-wrap" ref={wrapRef}>
        {lines.length === 0 ? (
          <span style={{ color: "var(--text3)" }}>{t("logs.empty")}</span>
        ) : (
          lines.map((line, index) => (
            <div key={index} className={`log-line lvl-${levelOf(line)}`}>
              {line}
            </div>
          ))
        )}
      </div>
      <div className="log-controls">
        <label style={{ display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
          <input type="checkbox" checked={auto} onChange={(event) => setAuto(event.target.checked)} />
          {t("logs.autorefresh")}
        </label>
        <span style={{ marginLeft: "auto" }}>{lines.length} lines</span>
      </div>
    </div>
  );
}
