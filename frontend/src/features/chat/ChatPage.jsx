import { useEffect, useRef, useState } from "react";
import { api, streamEvents } from "../../lib/api.js";
import CitationDrawer from "../citations/CitationDrawer.jsx";
import FeedbackControl from "../feedback/FeedbackControl.jsx";

export default function ChatPage() {
  const [threadId, setThreadId] = useState(null);
  const [text, setText] = useState("");
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState("Ready");
  const [citations, setCitations] = useState([]);
  const [showSources, setShowSources] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [reviewStatus, setReviewStatus] = useState(null);
  const streamCursor = useRef(null);
  const cancellation = useRef(null);
  const latestAssistant = [...messages].reverse().find((message) => message.actor_type === "assistant");

  useEffect(() => () => cancellation.current?.abort(), []);

  async function refreshThread(activeThreadId) {
    const detail = await api(`/chat/threads/${activeThreadId}`);
    setMessages(detail.messages);
    const assistant = [...detail.messages].reverse().find((message) => message.actor_type === "assistant");
    setCitations(assistant?.citations || []);
    setProcessing(["processing", "awaiting_review"].includes(detail.status));
    setReviewStatus(detail.review_status || null);
    return detail;
  }

  async function send(event) {
    event.preventDefault();
    const content = text.trim();
    if (!content) return;
    setText("");
    setMessages((current) => [...current, { actor_type: "user", content }]);
    setStatus("Submitting request…");
    setProcessing(true);
    try {
      let activeThreadId = threadId;
      if (!activeThreadId) {
        const thread = await api("/chat/threads", { method: "POST", body: JSON.stringify({}) });
        activeThreadId = thread.thread_id;
        setThreadId(activeThreadId);
      }
      await api(`/chat/threads/${activeThreadId}/messages`, { method: "POST", body: JSON.stringify({ content }) });
      await consumeEvents(activeThreadId);
      await refreshThread(activeThreadId);
    } catch (error) {
      if (error?.name === "AbortError") return;
      setStatus("The request could not be completed.");
      setProcessing(false);
    }
  }

  async function consumeEvents(activeThreadId) {
    try {
      cancellation.current = new AbortController();
      await streamEvents(activeThreadId, async ({ id, event, data }) => {
        streamCursor.current = id || streamCursor.current;
        setStatus(event.replaceAll("_", " "));
        if (event === "awaiting_specialist_review") {
          setProcessing(true);
        }
        if (event === "completed") {
          await refreshThread(activeThreadId);
          setProcessing(false);
        }
      }, { lastEventId: streamCursor.current, signal: cancellation.current.signal });
    } catch (error) {
      if (error?.name === "AbortError") throw error;
      await refreshThread(activeThreadId);
      setStatus("Connection interrupted — status refreshed.");
    }
  }

  return (
    <section className="workspace">
      <div className="panel-head"><div><p className="eyebrow">Employee policy support</p><h2>Ask a policy question</h2></div><span className="status">{status}</span></div>
      <div className="messages" aria-live="polite">
        {messages.length === 0 && <p className="empty-state">Ask about HR, IT Support, or Operations policy. Do not include passwords, tokens, medical details, or other sensitive data.</p>}
        {messages.map((message, index) => <article className={`message ${message.actor_type}`} key={`${message.id || index}-${message.actor_type}`}><span>{message.actor_type === "assistant" ? "Support" : "You"}</span><p>{message.content}</p></article>)}
      </div>
      {reviewStatus && ["pending", "expired"].includes(reviewStatus.status) && <aside className="review-status" aria-live="polite"><strong>Specialist review: {reviewStatus.status.replaceAll("_", " ")}</strong><span>{reviewStatus.status === "pending" ? `A ${reviewStatus.required_specialist_role.replaceAll("_", " ")} is handling this mock review task. It expires ${new Date(reviewStatus.expires_at).toLocaleString()}.` : "This mock review task expired. Please submit a new support request."}</span></aside>}
      <form onSubmit={send} className="composer"><textarea value={text} onChange={(event) => setText(event.target.value)} maxLength="8000" disabled={processing} placeholder="Ask a general policy question…" /><div className="row"><button type="button" disabled={!citations.length} onClick={() => setShowSources(true)}>View sources</button><button type="submit" disabled={processing}>{processing ? "Working…" : "Send"}</button></div></form>
      <FeedbackControl threadId={threadId} responseKey={latestAssistant?.id || ""} disabled={!latestAssistant} />
      {showSources && <CitationDrawer citations={citations} onClose={() => setShowSources(false)} />}
    </section>
  );
}
