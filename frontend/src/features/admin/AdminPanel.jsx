import { useState } from "react";
import { api } from "../../lib/api.js";

export default function AdminPanel({ canIngest, canAudit }) {
  const [report, setReport] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function ingest() {
    setBusy(true);
    try { setReport(await api("/admin/policies/ingest", { method: "POST" })); setError(""); } catch { setError("Policy ingestion could not be started."); } finally { setBusy(false); }
  }
  async function loadAudit() {
    setBusy(true);
    try { setEvents(await api("/admin/audit-events?limit=100")); setError(""); } catch { setError("Audit events are unavailable for this account."); } finally { setBusy(false); }
  }
  if (!canIngest && !canAudit) return null;
  return <section className="workspace"><div className="panel-head"><div><p className="eyebrow">Restricted administration</p><h2>Policy and audit controls</h2></div></div>{error && <p className="error">{error}</p>}<div className="admin-actions">{canIngest && <button disabled={busy} onClick={ingest}>{busy ? "Working…" : "Ingest fictional policies"}</button>}{canAudit && <button disabled={busy} onClick={loadAudit}>Load redacted audit events</button>}</div>{report && <section className="report"><h3>Ingestion report</h3><p>Indexed: {report.ingested} · Quarantined: {report.quarantined}</p><table><thead><tr><th>Source</th><th>Result</th><th>Detail</th></tr></thead><tbody>{report.entries.map((entry) => <tr key={`${entry.path}-${entry.status}`}><td>{entry.path}</td><td>{entry.status}</td><td>{entry.detail}</td></tr>)}</tbody></table></section>}{events.length > 0 && <section className="report"><h3>Redacted audit explorer</h3><table><thead><tr><th>Time</th><th>Event</th><th>Decision</th><th>Reason</th><th>Trace</th></tr></thead><tbody>{events.map((event) => <tr key={event.event_id}><td>{new Date(event.occurred_at).toLocaleString()}</td><td>{event.event_type}</td><td>{event.decision}</td><td>{event.reason_code || "—"}</td><td className="trace-id" title={event.trace_id || ""}>{event.trace_id ? `${event.trace_id.slice(0, 12)}…` : "—"}</td></tr>)}</tbody></table></section>}</section>;
}
