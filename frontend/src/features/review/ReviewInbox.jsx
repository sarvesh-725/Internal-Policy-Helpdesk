import { useEffect, useState } from "react";
import { api } from "../../lib/api.js";

export default function ReviewInbox() {
  const [tasks, setTasks] = useState([]);
  const [error, setError] = useState("");
  const [edits, setEdits] = useState({});

  async function refresh() {
    try { setTasks(await api("/review/tasks")); setError(""); } catch { setError("Unable to load review tasks."); }
  }
  useEffect(() => { refresh(); }, []);
  async function decide(taskId, decision) {
    try {
      const payload = { decision };
      if (decision === "edit") payload.edited_response = edits[taskId] || "";
      await api(`/review/tasks/${taskId}/decision`, { method: "POST", body: JSON.stringify(payload) });
      await refresh();
    } catch { setError("The decision could not be recorded."); }
  }
  return <section className="workspace"><div className="panel-head"><div><p className="eyebrow">Specialist workspace</p><h2>Review inbox</h2></div><button onClick={refresh}>Refresh</button></div>{error && <p className="error">{error}</p>}{tasks.length === 0 ? <p className="empty-state">No review tasks are assigned to your role.</p> : tasks.map((task) => <article className="task" key={task.task_id}><strong>{task.required_specialist_role.replaceAll("_", " ")}</strong><p>{task.safe_case_summary}</p><small>Expires {new Date(task.expires_at).toLocaleString()}</small><textarea value={edits[task.task_id] || ""} onChange={(event) => setEdits((current) => ({ ...current, [task.task_id]: event.target.value }))} placeholder="Optional process-status message; do not add policy claims or personal data" maxLength="8000" /><div className="row"><button onClick={() => decide(task.task_id, "approve")}>Approve</button><button onClick={() => decide(task.task_id, "edit")}>Approve edited message</button><button onClick={() => decide(task.task_id, "reject")}>Reject</button></div></article>)}</section>;
}
