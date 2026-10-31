import { useEffect, useState } from "react";
import { api } from "../../lib/api.js";

export default function FeedbackControl({ threadId, responseKey, disabled }) {
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { setSent(false); setError(""); }, [responseKey]);

  async function send(helpful) {
    if (!threadId || sent) return;
    try {
      await api("/feedback", { method: "POST", body: JSON.stringify({ thread_id: threadId, helpful }) });
      setSent(true);
      setError("");
    } catch {
      setError("Feedback could not be saved.");
    }
  }

  return <div className="feedback" aria-label="Response feedback"><span>Was this response helpful?</span><button disabled={disabled || sent} onClick={() => send(true)}>Yes</button><button disabled={disabled || sent} onClick={() => send(false)}>No</button>{sent && <small>Thanks — feedback recorded.</small>}{error && <small className="error">{error}</small>}</div>;
}
