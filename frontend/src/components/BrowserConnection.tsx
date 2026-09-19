import { useEffect, useState } from "react";
import { api, requestId } from "../lib/api";
import { Badge, Spinner, useToast } from "./ui";

export function BrowserConnection() {
  const [state, setState] = useState<{ connected: boolean; expires_at?: number; last_seen_at?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const refresh = () => api("/api/browser-runner").then(setState).catch(() => {});
  useEffect(() => { refresh(); const timer = setInterval(refresh, 30000); return () => clearInterval(timer); }, []);

  async function connect() {
    setBusy(true);
    try {
      const { token, expires_at } = await api<{ token: string; expires_at: number }>("/api/browser-runner", { body: {} });
      const id = requestId("pair");
      await new Promise<void>((resolve, reject) => {
        const cleanup = () => { clearTimeout(timer); window.removeEventListener("message", receive); };
        const receive = (event: MessageEvent) => {
          if (event.source !== window || event.origin !== window.location.origin || event.data?.type !== "CAREER_AGENT_BROWSER_PAIRED" || event.data?.requestId !== id) return;
          cleanup();
          if (event.data.ok) resolve(); else reject(new Error(event.data.error || "Browser connection failed"));
        };
        const timer = setTimeout(() => { cleanup(); reject(new Error("Enable or reload the Career Agent Browser Companion extension, refresh this page, then connect again.")); }, 5000);
        window.addEventListener("message", receive);
        window.postMessage({ type: "CAREER_AGENT_PAIR_BROWSER", requestId: id, token, expires_at, api: window.location.origin }, window.location.origin);
      });
      toast("Browser connected. Authorized applications will open and run automatically while this browser is open.", "success");
    } catch (error) {
      await api("/api/browser-runner", { method: "DELETE" }).catch(() => {});
      toast((error as Error).message, "error");
    } finally { await refresh(); setBusy(false); }
  }

  return <div className="card pad glass-stripe">
    <div className="card-title"><h3>Automatic applications in this browser</h3><Badge tone={state?.connected ? "mint" : "amber"}>{state?.connected ? "Connected" : "Not connected"}</Badge></div>
    <p className="small muted">Connect the Browser Companion once to open and complete authorized employer applications automatically. Keep this browser open and stay signed in to employer sites. Your approval mode, eligibility checks and daily limits still apply.</p>
    <p className="small muted">Login, verification and missing required answers pause the affected application. Add reusable answers in Profile to reduce interruptions. Connecting lasts seven days; revoking your automatic mandate stops new automatic submissions.</p>
    {state?.last_seen_at && <p className="small muted">Last connected: {new Date(state.last_seen_at).toLocaleString()}</p>}
    <div className="row">
      <button className="btn primary" disabled={busy} onClick={connect}>{busy && <Spinner />}{state?.connected ? "Reconnect this browser" : "Connect this browser"}</button>
      {state?.connected && <button className="btn" disabled={busy} onClick={async () => { await api("/api/browser-runner", { method: "DELETE" }); await refresh(); }}>Disconnect</button>}
    </div>
  </div>;
}
