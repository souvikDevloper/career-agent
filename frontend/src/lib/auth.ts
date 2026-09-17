// Cognito User Pool authentication over its public JSON API (no SDK needed).
import { loadConfig } from "./config";

export type Session = { idToken: string; accessToken: string; refreshToken?: string; expiresAt: number; example?: boolean; email?: string };
const KEY = "career-agent.session";
type Listener = (s: Session | null) => void;
const listeners = new Set<Listener>();

function read(): Session | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

let current: Session | null = read();

export function getSession(): Session | null {
  return current;
}

export function setSession(s: Session | null) {
  current = s;
  try {
    if (s) localStorage.setItem(KEY, JSON.stringify(s));
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: session stays in memory */
  }
  listeners.forEach((l) => l(s));
}

export function onSession(l: Listener) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function claims(token: string): Record<string, unknown> {
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(decodeURIComponent(escape(atob(part))));
  } catch {
    return {};
  }
}

async function cognito<T>(target: string, body: object): Promise<T> {
  const cfg = await loadConfig();
  const res = await fetch(`https://cognito-idp.${cfg.region}.amazonaws.com/`, {
    method: "POST",
    headers: { "Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": `AWSCognitoIdentityProviderService.${target}` },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = (data as { message?: string }).message || "Authentication failed";
    throw new Error(msg);
  }
  return data as T;
}

type AuthResult = { AuthenticationResult: { IdToken: string; AccessToken: string; RefreshToken?: string; ExpiresIn: number } };

export async function signIn(email: string, password: string) {
  const cfg = await loadConfig();
  const r = await cognito<AuthResult>("InitiateAuth", {
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: cfg.userPoolClientId,
    AuthParameters: { USERNAME: email, PASSWORD: password },
  });
  const a = r.AuthenticationResult;
  setSession({ idToken: a.IdToken, accessToken: a.AccessToken, refreshToken: a.RefreshToken, expiresAt: Date.now() + a.ExpiresIn * 1000, email });
}

export async function signUp(email: string, password: string) {
  const cfg = await loadConfig();
  await cognito("SignUp", { ClientId: cfg.userPoolClientId, Username: email, Password: password, UserAttributes: [{ Name: "email", Value: email }] });
}

export async function confirmSignUp(email: string, code: string) {
  const cfg = await loadConfig();
  await cognito("ConfirmSignUp", { ClientId: cfg.userPoolClientId, Username: email, ConfirmationCode: code });
}

export async function refresh(): Promise<Session | null> {
  const s = current;
  if (!s?.refreshToken) return null;
  try {
    const cfg = await loadConfig();
    const r = await cognito<AuthResult>("InitiateAuth", {
      AuthFlow: "REFRESH_TOKEN_AUTH",
      ClientId: cfg.userPoolClientId,
      AuthParameters: { REFRESH_TOKEN: s.refreshToken },
    });
    const a = r.AuthenticationResult;
    const next = { ...s, idToken: a.IdToken, accessToken: a.AccessToken, expiresAt: Date.now() + a.ExpiresIn * 1000 };
    setSession(next);
    return next;
  } catch {
    setSession(null);
    return null;
  }
}

export async function startExampleWorkspace() {
  const res = await fetch("/api/public/demo-session", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error?.message || "Could not start the example workspace");
  setSession({ idToken: data.id_token, accessToken: data.access_token, refreshToken: data.refresh_token, expiresAt: Date.now() + data.expires_in * 1000, example: true });
}

export function signOut() {
  setSession(null);
}
