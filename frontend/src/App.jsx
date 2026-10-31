import { useEffect, useState } from "react";
import ChatPage from "./features/chat/ChatPage.jsx";
import ReviewInbox from "./features/review/ReviewInbox.jsx";
import AdminPanel from "./features/admin/AdminPanel.jsx";
import { initializeAuth, signIn, signOut } from "./lib/auth.js";
import { api } from "./lib/api.js";

export default function App() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [view, setView] = useState("chat");
  useEffect(() => { initializeAuth().then(async (keycloak) => { if (keycloak.authenticated) setUser(await api("/auth/me")); setReady(true); }).catch(() => setReady(true)); }, []);
  if (!ready) return <main className="shell"><p>Loading secure workspace…</p></main>;
  if (!user) return <main className="shell"><section className="hero"><p className="eyebrow">Fictional policy assistant</p><h1>Internal-Policy-Helpdesk</h1><p>Secure policy navigation for HR, IT Support, and Operations.</p><button onClick={signIn}>Sign in</button></section></main>;
  const roles = user.roles || [];
  const isSpecialist = roles.some((role) => role.endsWith("_specialist"));
  const isAdmin = roles.includes("policy_admin") || roles.includes("system_admin");
  return (
    <main className="shell">
      <header className="topbar"><div><p className="eyebrow">Signed in as {user.username || "user"}</p><h1>NodeSwarm</h1></div><button onClick={signOut}>Sign out</button></header>
      <nav className="tabs" aria-label="Workspace navigation"><button className={view === "chat" ? "selected" : ""} onClick={() => setView("chat")}>Policy support</button>{isSpecialist && <button className={view === "review" ? "selected" : ""} onClick={() => setView("review")}>Review inbox</button>}{isAdmin && <button className={view === "admin" ? "selected" : ""} onClick={() => setView("admin")}>Administration</button>}</nav>
      {view === "chat" && <ChatPage />}
      {view === "review" && isSpecialist && <ReviewInbox />}
      {view === "admin" && isAdmin && <AdminPanel canIngest={roles.includes("policy_admin")} canAudit={roles.includes("system_admin")} />}
    </main>
  );
}
