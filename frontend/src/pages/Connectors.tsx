/**
 * Connectors - what this agent is plugged into, and how to plug into it.
 *
 * The MCP panel is not a description of the connector; it speaks the protocol.
 * On load it runs a real initialize/tools-list handshake against /api/mcp with
 * the signed-in user's token, so what you read is what a client would get. If
 * the endpoint were broken this panel would say so rather than show a diagram.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { useMe } from "../lib/me";
import { Shell } from "../components/Shell";
import { Badge, Empty, Spinner, useToast } from "../components/ui";
import { ILayers, ILink, IShield, IGlobe, ICheck, IAlert } from "../components/Icons";
import { timeAgo } from "../lib/format";

type McpTool = { name: string; description: string; inputSchema: { properties?: Record<string, { type: string; description?: string }>; required?: string[] } };
type Handshake = { version: string; server: string; instructions: string; tools: McpTool[] };

const STATUS: Record<string, [string, string]> = {
  verified_live: ["Verified live", "mint"],
  test_environment: ["Test environment", "amber"],
  needs_setup: ["Needs setup", "cyan"],
  manual_handoff: ["Manual handoff", "violet"],
};

let rpcId = 0;
async function rpc(method: string, params?: Record<string, unknown>) {
  const res = await api<{ result?: any; error?: { message: string } }>("/api/mcp", {
    method: "POST",
    body: { jsonrpc: "2.0", id: ++rpcId, method, params },
  });
  if (res.error) throw new Error(res.error.message);
  return res.result;
}

export function ConnectorsPage() {
  const { me } = useMe();
  const toast = useToast();
  const [shake, setShake] = useState<Handshake | null>(null);
  const [mcpError, setMcpError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const connect = useCallback(async () => {
    setMcpError(null);
    setShake(null);
    try {
      const init = await rpc("initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "career-agent-web", version: "1.0.0" } });
      const listed = await rpc("tools/list");
      setShake({
        version: init.protocolVersion,
        server: `${init.serverInfo?.name} ${init.serverInfo?.version}`,
        instructions: init.instructions || "",
        tools: listed.tools || [],
      });
    } catch (e) {
      setMcpError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void connect();
  }, [connect]);

  const endpoint = useMemo(() => `${window.location.origin}/api/mcp`, []);
  const configSnippet = useMemo(
    () =>
      JSON.stringify(
        { mcpServers: { "career-agent": { command: "npx", args: ["-y", "mcp-remote", endpoint] } } },
        null,
        2,
      ),
    [endpoint],
  );

  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast(`${what} copied`, "success");
    } catch {
      toast("Clipboard is blocked here — select the text and copy it", "error");
    }
  }

  const sources = me?.sources ?? [];
  const registry = Object.entries(me?.connectors ?? {});

  return (
    <Shell title="Connectors">
      <section className="card rise glass-stripe">
          <div className="between">
            <div>
              <p className="eyebrow"><ILink /> Model Context Protocol</p>
              <h2 className="card-title">Use this agent from your own client</h2>
            </div>
            {shake ? <Badge tone="mint" live>Connected</Badge> : mcpError ? <Badge tone="rose">Unreachable</Badge> : <Badge tone="cyan">Connecting…</Badge>}
          </div>
          <p className="muted">
            Career Agent is an MCP server. The tools below are the same functions its own voice agent calls — one
            registry, two front doors — so a client you connect drives the real system, as you, under the same
            authorization.
          </p>

          {mcpError ? (
            <p className="banner"><IAlert /> The MCP endpoint did not answer: {mcpError}</p>
          ) : !shake ? (
            <Spinner />
          ) : (
            <>
              <div className="row tiny muted" style={{ gap: 16, flexWrap: "wrap" }}>
                <span><ICheck /> Handshake complete</span>
                <span>Protocol {shake.version}</span>
                <span>{shake.server}</span>
                <span>{shake.tools.length} tools</span>
              </div>

              <ul className="stack plain-list" style={{ marginTop: 14 }}>
                {shake.tools.map((t) => {
                  const params = Object.entries(t.inputSchema?.properties ?? {});
                  const required = t.inputSchema?.required ?? [];
                  const isOpen = open === t.name;
                  return (
                    <li key={t.name} className="list-row">
                      <button className="mcp-tool" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : t.name)}>
                        <span className="mcp-tool-head">
                          <code className="chip">{t.name}</code>
                          <span className="tiny muted">{params.length ? `${params.length} param${params.length > 1 ? "s" : ""}` : "no params"}</span>
                        </span>
                        <span className="small muted">{t.description}</span>
                      </button>
                      {isOpen && params.length > 0 && (
                        <div className="scroll-x">
                          <table className="table">
                            <thead>
                              <tr><th>Parameter</th><th>Type</th><th>Meaning</th></tr>
                            </thead>
                            <tbody>
                              {params.map(([name, prop]) => (
                                <tr key={name}>
                                  <td><code>{name}</code>{required.includes(name) && <span className="tiny muted"> required</span>}</td>
                                  <td className="tiny muted">{prop.type}</td>
                                  <td className="tiny">{prop.description || "—"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>

              <p className="hint" style={{ marginTop: 14 }}>
                <IShield /> Approving a submission is deliberately not served over MCP. It is the one irreversible
                action here, and it needs a person — you approve each packet in this app.
              </p>
            </>
          )}
        </section>

      <section className="card rise rise-1 glass-stripe">
        <p className="eyebrow">Set it up</p>
        <h3 className="card-title">Add the connector</h3>
        <p className="muted">
          Paste the endpoint into your client. It discovers the rest on its own, opens a browser so you can sign in,
          and keeps working after that — there is no token to copy and no token to re-copy in an hour.
        </p>
        <div className="field">
          <label className="label" htmlFor="mcp-endpoint">Endpoint</label>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <input id="mcp-endpoint" className="input input-glow" style={{ flex: "1 1 220px", minWidth: 0 }} readOnly value={endpoint}
              onFocus={(e) => e.currentTarget.select()} />
            <button className="btn ghost" onClick={() => copy(endpoint, "Endpoint")}>Copy</button>
          </div>
        </div>
        <div className="field">
          <label className="label" htmlFor="mcp-config">For a client that runs MCP servers locally</label>
          <textarea id="mcp-config" className="textarea" rows={8} readOnly value={configSnippet} spellCheck={false} />
          <div className="row" style={{ gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            <button className="btn ghost" onClick={() => copy(configSnippet, "Configuration")}>Copy configuration</button>
          </div>
        </div>
        <ol className="stack plain-list auth-steps">
          <li className="list-row"><strong>1.</strong> Your client registers itself and sends you here.</li>
          <li className="list-row"><strong>2.</strong> You sign in and see exactly what it is asking for.</li>
          <li className="list-row"><strong>3.</strong> It receives a code, exchanges it with a PKCE verifier, and connects.</li>
        </ol>
        <p className="hint"><IShield /> Signing out everywhere ends every connection you have granted.</p>
      </section>

      <section className="card rise rise-2 glass-stripe">
          <p className="eyebrow"><IGlobe /> Job sources</p>
          <h3 className="card-title">Where openings come from</h3>
          {sources.length === 0 ? (
            <Empty icon={<IGlobe />} title="No sources polled yet">Sources report in after their first run.</Empty>
          ) : (
            <div className="scroll-x">
            <table className="table">
              <thead>
                <tr><th>Source</th><th>Last success</th><th>Openings</th><th>Every</th></tr>
              </thead>
              <tbody>
                {sources.map((s: any) => (
                  <tr key={s.source}>
                    <td>
                      {s.source}
                      {s.environment === "test" && <Badge tone="amber">Test</Badge>}
                      {s.last_error && <p className="tiny" style={{ color: "var(--rose)" }}>{s.last_error}</p>}
                    </td>
                    <td className="tiny muted">{s.last_success_at ? timeAgo(s.last_success_at) : "never"}</td>
                    <td className="tiny">{s.job_count ?? "—"}</td>
                    <td className="tiny muted">{s.interval_minutes} min</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </section>

      <section className="card rise rise-3 glass-stripe">
          <p className="eyebrow"><ILayers /> Capabilities</p>
          <h3 className="card-title">What each connector may actually do</h3>
          <ul className="stack plain-list">
            {registry.map(([key, c]: [string, any]) => {
              const [label, tone] = STATUS[c.status] ?? [c.status, "cyan"];
              return (
                <li key={key} className="list-row">
                  <div className="between">
                    <strong>{c.label}</strong>
                    <Badge tone={tone}>{label}</Badge>
                  </div>
                  <div className="chips">
                    {(c.capabilities ?? []).map((cap: string) => (
                      <span key={cap} className="chip">{cap.replace(/_/g, " ")}</span>
                    ))}
                  </div>
                  <p className="tiny muted">{c.note}</p>
                </li>
              );
            })}
          </ul>
        </section>
    </Shell>
  );
}
