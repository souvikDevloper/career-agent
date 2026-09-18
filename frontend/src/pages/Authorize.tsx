/**
 * Consent screen for an MCP client asking to connect.
 *
 * The request itself lives on the server under an opaque id; this page only
 * carries that id, so nothing a person can edit here changes where the
 * authorization code is delivered. The redirect at the end comes back from our
 * own API, which validated it against the client's registered URIs.
 *
 * The screen says what the client gets, what it cannot do, and - because the
 * refresh token handed over is the person's own session - how far that reach
 * goes. Consent that hides the cost is not consent.
 */
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "../lib/api";
import { getSession, onSession, type Session } from "../lib/auth";
import { useRouter } from "../lib/router";
import { BrandMark } from "../components/Shell";
import { Spinner } from "../components/ui";
import { ICheck, IShield, IAlert, ILink } from "../components/Icons";

type Consent = {
  client_name: string;
  redirect_host: string;
  grants: string[];
  withheld: string;
  caution: string;
};

export function AuthorizePage() {
  const { path, navigate } = useRouter();
  const [session, setSession] = useState<Session | null>(getSession());
  const [consent, setConsent] = useState<Consent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const requestId = new URLSearchParams(window.location.search).get("request") || "";

  useEffect(() => onSession(setSession), []);

  useEffect(() => {
    if (!requestId) {
      setError("This link is missing its authorization request. Start the connection again from your client.");
      return;
    }
    api<Consent>(`/api/public/oauth/request/${encodeURIComponent(requestId)}`)
      .then(setConsent)
      .catch((e) => setError(e instanceof ApiError ? e.message : "That authorization request could not be loaded."));
  }, [requestId]);

  const decide = useCallback(
    async (approve: boolean) => {
      setBusy(true);
      setError(null);
      try {
        const { redirect_to } = await api<{ redirect_to: string }>("/api/oauth/grant", {
          body: {
            request: requestId,
            approve,
            id_token: session?.idToken,
            refresh_token: session?.refreshToken,
          },
        });
        // Leaving the app entirely: the client's own callback, validated server-side.
        window.location.assign(redirect_to);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "That did not work. Start the connection again from your client.");
        setBusy(false);
      }
    },
    [requestId, session],
  );

  if (error) {
    return (
      <ConsentFrame>
        <p className="banner"><IAlert /> {error}</p>
      </ConsentFrame>
    );
  }

  if (!consent) {
    return (
      <ConsentFrame>
        <Spinner />
      </ConsentFrame>
    );
  }

  if (!session) {
    return (
      <ConsentFrame>
        <h1>Sign in to connect {consent.client_name}</h1>
        <p className="muted">You need to be signed in before you can connect a client to your account.</p>
        <button
          className="btn primary"
          onClick={() => navigate(`/login?next=${encodeURIComponent(path + window.location.search)}`)}
        >
          Sign in and continue
        </button>
      </ConsentFrame>
    );
  }

  return (
    <ConsentFrame>
      <p className="eyebrow"><ILink /> Connect a client</p>
      <h1>{consent.client_name} wants to use your Career Agent</h1>
      <p className="muted">
        Signed in as <strong>{session.email || "your account"}</strong>. It will be sent back to{" "}
        <code className="chip">{consent.redirect_host}</code>.
      </p>

      <ul className="stack plain-list" style={{ marginTop: 18 }}>
        {consent.grants.map((g) => (
          <li key={g} className="list-row">
            <span className="row" style={{ gap: 10, alignItems: "flex-start" }}>
              <ICheck size={15} /> <span>{g}</span>
            </span>
          </li>
        ))}
      </ul>

      <p className="hint" style={{ marginTop: 14 }}><IShield /> {consent.withheld}</p>
      <p className="banner" style={{ marginTop: 10 }}><IAlert /> {consent.caution}</p>

      <div className="row" style={{ gap: 10, marginTop: 20, flexWrap: "wrap" }}>
        <button className="btn primary" disabled={busy} onClick={() => decide(true)}>
          {busy ? "Connecting…" : `Connect ${consent.client_name}`}
        </button>
        <button className="btn ghost" disabled={busy} onClick={() => decide(false)}>
          Cancel
        </button>
      </div>
    </ConsentFrame>
  );
}

function ConsentFrame({ children }: { children: ReactNode }) {
  return (
    <div className="auth">
      <div className="card consent-card">
        <div className="row" style={{ gap: 10, marginBottom: 18 }}>
          <BrandMark />
          <strong>Career Agent</strong>
        </div>
        {children}
      </div>
    </div>
  );
}
