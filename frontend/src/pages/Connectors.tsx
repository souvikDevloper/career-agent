/**
 * Connectors & Model Context Protocol Hub.
 *
 * Implements a real MCP handshake with live RPC inspection, client configuration,
 * job source monitors, and Cedar authorization capabilities.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { useMe } from "../lib/me";
import { Shell } from "../components/Shell";
import { Badge, Empty, Spinner, useToast } from "../components/ui";
import {
  ILink,
  IShield,
  IGlobe,
  IAlert,
  ICode,
  IRefresh,
} from "../components/Icons";
import { timeAgo } from "../lib/format";

type McpTool = {
  name: string;
  description: string;
  inputSchema: {
    properties?: Record<string, { type: string; description?: string }>;
    required?: string[];
  };
};

type Handshake = {
  version: string;
  server: string;
  instructions: string;
  tools: McpTool[];
};

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
  const [openTool, setOpenTool] = useState<string | null>("search_jobs");
  const [activeTab, setActiveTab] = useState<"tools" | "setup" | "sources" | "capabilities">("tools");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedClient, setSelectedClient] = useState<"claude" | "cursor" | "cli">("claude");

  const connect = useCallback(async () => {
    setMcpError(null);
    setShake(null);
    try {
      const init = await rpc("initialize", {
        protocolVersion: "2025-06-18",
        capabilities: {},
        clientInfo: { name: "career-agent-web", version: "1.0.0" },
      });
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

  const configSnippets = useMemo(() => {
    return {
      claude: JSON.stringify(
        {
          mcpServers: {
            "career-agent": {
              command: "npx",
              args: ["-y", "mcp-remote", endpoint],
            },
          },
        },
        null,
        2
      ),
      cursor: JSON.stringify(
        {
          mcp: {
            servers: {
              "career-agent": {
                url: endpoint,
                transport: "http",
              },
            },
          },
        },
        null,
        2
      ),
      cli: `npx -y mcp-remote ${endpoint}`,
    };
  }, [endpoint]);

  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast(`${what} copied to clipboard`, "success");
    } catch {
      toast("Clipboard is blocked — select text and copy manually", "error");
    }
  }

  const sources = me?.sources ?? [];
  const registry = Object.entries(me?.connectors ?? {});

  const filteredTools = useMemo(() => {
    if (!shake?.tools) return [];
    if (!searchQuery.trim()) return shake.tools;
    const q = searchQuery.toLowerCase();
    return shake.tools.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        Object.keys(t.inputSchema?.properties ?? {}).some((p) => p.toLowerCase().includes(q))
    );
  }, [shake?.tools, searchQuery]);

  return (
    <Shell title="Connectors">
      <div className="connectors-page">
        {/* Top Hero Banner */}
        <div className="mcp-hero-card">
          <div className="between" style={{ flexWrap: "wrap", gap: 16, alignItems: "flex-start" }}>
            <div>
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: 12,
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                  color: "#c4b5fd",
                  fontWeight: 700,
                  marginBottom: 8,
                }}
              >
                <ILink size={14} /> Model Context Protocol (MCP) Server
              </div>
              <h2 style={{ fontSize: "clamp(22px, 2.5vw, 30px)", fontWeight: 800, margin: "0 0 8px 0" }}>
                Connect Your Client to Autonomous Job Search
              </h2>
              <p style={{ color: "var(--ink-2)", fontSize: 14.5, maxWidth: 680, lineHeight: 1.6, margin: 0 }}>
                Career Agent exposes its full reasoning toolkit via a standards-compliant Model Context Protocol server.
                Connect Claude Desktop, Cursor, or your personal AI to discover jobs, inspect fits, and draft verified
                applications.
              </p>
            </div>

            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
              {shake ? (
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <button
                    className="btn ghost sm"
                    onClick={connect}
                    title="Reconnect / Refresh Handshake"
                    style={{ gap: 6 }}
                  >
                    <IRefresh size={13} /> Refresh
                  </button>
                  <Badge tone="mint" live>
                    Connected · {shake.tools.length} Tools
                  </Badge>
                </div>
              ) : mcpError ? (
                <Badge tone="rose">Unreachable</Badge>
              ) : (
                <Badge tone="cyan">Connecting…</Badge>
              )}

              {shake && (
                <div className="tiny muted" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                  <span>Protocol {shake.version}</span>
                  <span>{shake.server}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Tabbed Navigation */}
        <div className="connector-tabs">
          <button
            className={`connector-tab-btn ${activeTab === "tools" ? "active" : ""}`}
            onClick={() => setActiveTab("tools")}
          >
            <ILink size={15} /> MCP Tools ({shake?.tools.length ?? "…"})
          </button>
          <button
            className={`connector-tab-btn ${activeTab === "setup" ? "active" : ""}`}
            onClick={() => setActiveTab("setup")}
          >
            <ICode size={15} /> Client Setup & Config
          </button>
          <button
            className={`connector-tab-btn ${activeTab === "sources" ? "active" : ""}`}
            onClick={() => setActiveTab("sources")}
          >
            <IGlobe size={15} /> Job Sources ({sources.length})
          </button>
          <button
            className={`connector-tab-btn ${activeTab === "capabilities" ? "active" : ""}`}
            onClick={() => setActiveTab("capabilities")}
          >
            <IShield size={15} /> Platform Capabilities & Cedar
          </button>
        </div>

        {/* ── TAB 1: TOOLS & SCHEMA ── */}
        {activeTab === "tools" && (
          <section className="card pad glass-stripe" style={{ padding: 24 }}>
            <div className="between" style={{ flexWrap: "wrap", gap: 14, marginBottom: 18 }}>
              <div>
                <h3 style={{ fontSize: 18, fontWeight: 700, margin: "0 0 4px 0" }}>Registered MCP Tools</h3>
                <p className="tiny muted">
                  Real tools exposed over JSON-RPC 2.0. Irreversible submission actions strictly require human in-app approval.
                </p>
              </div>

              <div style={{ position: "relative", minWidth: 260 }}>
                <input
                  type="text"
                  className="input input-glow"
                  placeholder="Search tools & params..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{ height: 38, fontSize: 13, paddingLeft: 12 }}
                />
              </div>
            </div>

            {mcpError ? (
              <div
                style={{
                  padding: 16,
                  borderRadius: 12,
                  background: "rgba(244, 114, 182, 0.1)",
                  border: "1px solid rgba(244, 114, 182, 0.3)",
                  color: "#f9a8d4",
                  display: "flex",
                  gap: 12,
                  alignItems: "center",
                }}
              >
                <IAlert size={20} />
                <div>
                  <strong>The MCP endpoint did not respond:</strong> {mcpError}
                </div>
              </div>
            ) : !shake ? (
              <div style={{ padding: 40, display: "flex", justifyContent: "center" }}>
                <Spinner />
              </div>
            ) : filteredTools.length === 0 ? (
              <Empty icon={<ILink />} title="No matching tools found">
                Try searching for a different keyword or function name.
              </Empty>
            ) : (
              <div className="mcp-tool-list">
                {filteredTools.map((t) => {
                  const params = Object.entries(t.inputSchema?.properties ?? {});
                  const required = t.inputSchema?.required ?? [];
                  const isOpen = openTool === t.name;

                  return (
                    <div key={t.name} className={`mcp-tool-card ${isOpen ? "is-open" : ""}`}>
                      <button
                        className="mcp-tool-header-btn"
                        onClick={() => setOpenTool(isOpen ? null : t.name)}
                        aria-expanded={isOpen}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                          <span className="mcp-tool-name-chip">
                            <ICode size={14} /> {t.name}
                          </span>
                          <span style={{ fontSize: 13.5, color: "var(--ink-2)", fontWeight: 500 }}>
                            {t.description}
                          </span>
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <span className="mcp-tool-param-pill">
                            {params.length === 0
                              ? "no params"
                              : `${params.length} param${params.length > 1 ? "s" : ""}${
                                  required.length > 0 ? ` · ${required.length} req` : ""
                                }`}
                          </span>
                          <span
                            style={{
                              fontSize: 12,
                              color: "var(--accent)",
                              fontWeight: 600,
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 4,
                            }}
                          >
                            {isOpen ? "Hide schema ▲" : "View schema ▼"}
                          </span>
                        </div>
                      </button>

                      {isOpen && params.length > 0 && (
                        <div className="mcp-schema-drawer">
                          <table className="mcp-schema-table">
                            <thead>
                              <tr>
                                <th style={{ width: "25%" }}>Parameter</th>
                                <th style={{ width: "15%" }}>Type</th>
                                <th style={{ width: "15%" }}>Requirement</th>
                                <th>Description / Schema Meaning</th>
                              </tr>
                            </thead>
                            <tbody>
                              {params.map(([pName, pProp]) => {
                                const isReq = required.includes(pName);
                                return (
                                  <tr key={pName}>
                                    <td>
                                      <code
                                        style={{
                                          fontFamily: "var(--mono)",
                                          fontSize: 12.5,
                                          fontWeight: 600,
                                          color: "#9fe0f7",
                                          background: "rgba(76, 201, 240, 0.08)",
                                          padding: "2px 6px",
                                          borderRadius: 5,
                                        }}
                                      >
                                        {pName}
                                      </code>
                                    </td>
                                    <td>
                                      <span
                                        style={{
                                          fontFamily: "var(--mono)",
                                          fontSize: 11.5,
                                          color: "#c4b5fd",
                                        }}
                                      >
                                        {pProp.type}
                                      </span>
                                    </td>
                                    <td>
                                      {isReq ? (
                                        <Badge tone="rose">Required</Badge>
                                      ) : (
                                        <span className="tiny muted">Optional</span>
                                      )}
                                    </td>
                                    <td style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.5 }}>
                                      {pProp.description || "—"}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            <div
              style={{
                marginTop: 20,
                padding: "14px 18px",
                borderRadius: 12,
                background: "linear-gradient(135deg, rgba(123, 92, 255, 0.08), rgba(99, 102, 241, 0.04))",
                border: "1px solid rgba(123, 92, 255, 0.2)",
                display: "flex",
                gap: 12,
                alignItems: "center",
              }}
            >
              <IShield size={18} style={{ color: "var(--accent)", flexShrink: 0 }} />
              <p style={{ margin: 0, fontSize: 13, color: "var(--ink-2)", lineHeight: 1.5 }}>
                <strong>Cedar Security Gate:</strong> Submissions and final clicks cannot be triggered directly over
                MCP. Each application packet requires your cryptographic consent in the Career Agent web app.
              </p>
            </div>
          </section>
        )}

        {/* ── TAB 2: CLIENT SETUP & CONFIG ── */}
        {activeTab === "setup" && (
          <section className="card pad glass-stripe" style={{ padding: 24 }}>
            <h3 style={{ fontSize: 18, fontWeight: 700, margin: "0 0 6px 0" }}>Connect Your Client</h3>
            <p className="muted" style={{ margin: "0 0 20px 0", fontSize: 14 }}>
              The server runs serverless on AWS Lambda behind this endpoint. Copy the URL or pre-formatted configuration
              block to connect your assistant.
            </p>

            <div style={{ marginBottom: 24 }}>
              <label className="label" style={{ fontWeight: 600 }}>
                Server Endpoint URL (HTTP POST JSON-RPC)
              </label>
              <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
                <input
                  className="input input-glow"
                  style={{ flex: "1 1 320px", fontFamily: "var(--mono)", fontSize: 13 }}
                  readOnly
                  value={endpoint}
                  onFocus={(e) => e.currentTarget.select()}
                />
                <button className="btn primary" onClick={() => copy(endpoint, "Endpoint")}>
                  Copy Endpoint
                </button>
              </div>
            </div>

            <div style={{ marginBottom: 20 }}>
              <div className="between" style={{ marginBottom: 10, alignItems: "center" }}>
                <label className="label" style={{ fontWeight: 600, margin: 0 }}>
                  Pre-configured Client Snippet
                </label>

                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    className={`btn sm ${selectedClient === "claude" ? "primary" : "ghost"}`}
                    onClick={() => setSelectedClient("claude")}
                  >
                    Claude Desktop
                  </button>
                  <button
                    className={`btn sm ${selectedClient === "cursor" ? "primary" : "ghost"}`}
                    onClick={() => setSelectedClient("cursor")}
                  >
                    Cursor IDE
                  </button>
                  <button
                    className={`btn sm ${selectedClient === "cli" ? "primary" : "ghost"}`}
                    onClick={() => setSelectedClient("cli")}
                  >
                    npx CLI
                  </button>
                </div>
              </div>

              <pre className="config-code-block">
                <code>{configSnippets[selectedClient]}</code>
              </pre>

              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                <button
                  className="btn ghost sm"
                  onClick={() => copy(configSnippets[selectedClient], "Configuration")}
                  style={{ border: "1px solid rgba(255, 255, 255, 0.12)" }}
                >
                  <ICode size={14} /> Copy snippet
                </button>
              </div>
            </div>

            {/* Visual Workflow Steps */}
            <div style={{ marginTop: 24, borderTop: "1px solid rgba(255, 255, 255, 0.08)", paddingTop: 20 }}>
              <div className="eyebrow" style={{ marginBottom: 14 }}>
                OAuth 2.0 PKCE Handshake Workflow
              </div>
              <div className="grid g3" style={{ gap: 14 }}>
                <div
                  style={{
                    padding: 16,
                    borderRadius: 12,
                    background: "rgba(255, 255, 255, 0.02)",
                    border: "1px solid rgba(255, 255, 255, 0.07)",
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 16,
                      fontWeight: 800,
                      color: "var(--accent)",
                      marginBottom: 6,
                    }}
                  >
                    01
                  </div>
                  <strong style={{ fontSize: 14, display: "block", marginBottom: 4 }}>Client Discovery</strong>
                  <p className="tiny muted" style={{ margin: 0, lineHeight: 1.5 }}>
                    Your client fetches <code>/api/mcp</code> with an <code>initialize</code> call to inspect tools and
                    protocol version.
                  </p>
                </div>

                <div
                  style={{
                    padding: 16,
                    borderRadius: 12,
                    background: "rgba(255, 255, 255, 0.02)",
                    border: "1px solid rgba(255, 255, 255, 0.07)",
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 16,
                      fontWeight: 800,
                      color: "var(--cyan)",
                      marginBottom: 6,
                    }}
                  >
                    02
                  </div>
                  <strong style={{ fontSize: 14, display: "block", marginBottom: 4 }}>Scope Consent</strong>
                  <p className="tiny muted" style={{ margin: 0, lineHeight: 1.5 }}>
                    You review the requested permissions in browser and grant scoped credentials for this session.
                  </p>
                </div>

                <div
                  style={{
                    padding: 16,
                    borderRadius: 12,
                    background: "rgba(255, 255, 255, 0.02)",
                    border: "1px solid rgba(255, 255, 255, 0.07)",
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 16,
                      fontWeight: 800,
                      color: "var(--mint)",
                      marginBottom: 6,
                    }}
                  >
                    03
                  </div>
                  <strong style={{ fontSize: 14, display: "block", marginBottom: 4 }}>PKCE Code Exchange</strong>
                  <p className="tiny muted" style={{ margin: 0, lineHeight: 1.5 }}>
                    Cryptographic tokens are returned directly to your client. Revoke access anytime with one click.
                  </p>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* ── TAB 3: JOB SOURCES ── */}
        {activeTab === "sources" && (
          <section className="card pad glass-stripe" style={{ padding: 24 }}>
            <div className="between" style={{ marginBottom: 20 }}>
              <div>
                <h3 style={{ fontSize: 18, fontWeight: 700, margin: "0 0 4px 0" }}>Configured Ingestion Sources</h3>
                <p className="tiny muted" style={{ margin: 0 }}>
                  EventBridge monitors poll these sources every 5 to 30 minutes without requiring local machines.
                </p>
              </div>
            </div>

            {sources.length === 0 ? (
              <Empty icon={<IGlobe />} title="No sources active">
                Sources will appear here after initial ingestion.
              </Empty>
            ) : (
              <div className="source-card-grid">
                {sources.map((s: any) => (
                  <div key={s.source} className="source-detail-card">
                    <div className="between" style={{ alignItems: "flex-start" }}>
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                          <span
                            style={{
                              width: 8,
                              height: 8,
                              borderRadius: "50%",
                              background: "var(--mint)",
                              boxShadow: "0 0 8px var(--mint)",
                            }}
                          />
                          <strong style={{ fontSize: 16, color: "var(--ink)" }}>{s.source}</strong>
                        </div>
                        <span className="tiny muted">
                          Polled every {s.interval_minutes} minutes via EventBridge
                        </span>
                      </div>

                      {s.environment === "test" ? (
                        <Badge tone="amber">Test Employer</Badge>
                      ) : (
                        <Badge tone="mint">Verified Live</Badge>
                      )}
                    </div>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: 10,
                        padding: "12px 14px",
                        background: "rgba(0,0,0,0.3)",
                        borderRadius: 10,
                        border: "1px solid rgba(255,255,255,0.06)",
                      }}
                    >
                      <div>
                        <span className="tiny muted" style={{ display: "block" }}>
                          Active Openings
                        </span>
                        <strong style={{ fontSize: 18, color: "var(--ink)" }}>{s.job_count ?? "—"}</strong>
                      </div>
                      <div>
                        <span className="tiny muted" style={{ display: "block" }}>
                          Last Sync
                        </span>
                        <span style={{ fontSize: 13, color: "var(--ink-2)", fontWeight: 600 }}>
                          {s.last_success_at ? timeAgo(s.last_success_at) : "never"}
                        </span>
                      </div>
                    </div>

                    {s.last_error && (
                      <p className="tiny" style={{ color: "var(--rose)", margin: 0 }}>
                        {s.last_error}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* ── TAB 4: PLATFORM CAPABILITIES ── */}
        {activeTab === "capabilities" && (
          <section className="card pad glass-stripe" style={{ padding: 24 }}>
            <h3 style={{ fontSize: 18, fontWeight: 700, margin: "0 0 6px 0" }}>Connector Capabilities & Policies</h3>
            <p className="muted" style={{ margin: "0 0 20px 0", fontSize: 14 }}>
              What this agent is legally and technically permitted to execute on each external portal.
            </p>

            <div className="source-card-grid">
              {registry.map(([key, c]: [string, any]) => {
                const [label, tone] = STATUS[c.status] ?? [c.status, "cyan"];
                return (
                  <div key={key} className="source-detail-card">
                    <div className="between" style={{ alignItems: "flex-start" }}>
                      <div>
                        <strong style={{ fontSize: 16, display: "block", marginBottom: 2 }}>{c.label}</strong>
                        <span className="tiny muted">{c.environment} environment</span>
                      </div>
                      <Badge tone={tone}>{label}</Badge>
                    </div>

                    <div>
                      <span className="tiny muted" style={{ display: "block", marginBottom: 6 }}>
                        Supported Actions
                      </span>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {(c.capabilities ?? []).map((cap: string) => (
                          <span key={cap} className="capability-chip">
                            {cap.replace(/_/g, " ")}
                          </span>
                        ))}
                      </div>
                    </div>

                    <p className="tiny muted" style={{ margin: 0, lineHeight: 1.5 }}>
                      {c.note}
                    </p>
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </div>
    </Shell>
  );
}
