import { getAccessToken } from "./auth.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export async function api(path, options = {}) {
  const token = await getAccessToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  });
  if (response.status === 204) return null;
  if (!response.ok) throw new Error("The request could not be completed.");
  return response.json();
}

export async function streamEvents(threadId, onEvent, { lastEventId = null, signal } = {}) {
  const token = await getAccessToken();
  const response = await fetch(`${API_BASE_URL}/chat/threads/${threadId}/events`, {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}) },
    signal,
  });
  if (!response.ok || !response.body) throw new Error("Unable to open the status stream.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const event = frame.match(/^event:\s*(.+)$/m)?.[1];
      const id = frame.match(/^id:\s*(.+)$/m)?.[1];
      const data = frame.match(/^data:\s*(.+)$/m)?.[1];
      if (event && data) await onEvent({ id, event, data: JSON.parse(data) });
    }
  }
}
