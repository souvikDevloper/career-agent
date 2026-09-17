import { getSession, refresh, setSession } from "./auth";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function api<T = any>(path: string, init: { method?: string; body?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  let s = getSession();
  if (s && s.expiresAt - Date.now() < 60_000) s = (await refresh()) || s;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (s) headers.Authorization = `Bearer ${s.idToken}`;
  const res = await fetch(path, {
    method: init.method || (init.body ? "POST" : "GET"),
    headers,
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    signal: init.signal,
  });
  if (res.status === 204) return {} as T;
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && s) {
    setSession(null);
  }
  if (!res.ok) {
    const err = (data as any)?.error || {};
    throw new ApiError(res.status, err.code || "error", err.message || `Request failed (${res.status})`);
  }
  return data as T;
}

export function requestId(prefix = "req") {
  const rnd = crypto.getRandomValues(new Uint8Array(8));
  return `${prefix}-${Date.now().toString(36)}-${Array.from(rnd, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}

/** Poll an async operation. Backs off when the tab is hidden. */
export async function waitForOperation(opId: string, onUpdate: (op: Operation) => void, signal?: AbortSignal): Promise<Operation> {
  let delay = 900;
  for (let i = 0; i < 400; i++) {
    if (signal?.aborted) throw new Error("aborted");
    const { operation } = await api<{ operation: Operation }>(`/api/operations/${opId}`, { signal });
    onUpdate(operation);
    if (operation.status === "succeeded" || operation.status === "failed") return operation;
    await new Promise((r) => setTimeout(r, document.hidden ? 5000 : delay));
    delay = Math.min(2000, delay + 150);
  }
  throw new Error("Timed out waiting for the operation");
}

export type Operation = {
  op_id: string;
  kind: string;
  status: "accepted" | "running" | "succeeded" | "failed";
  progress: { at: string; message: string }[];
  results: MatchCard[];
  final?: any;
  created_at: string;
};

export type Filter = { check: string; status: "pass" | "fail" | "unknown"; detail: string; mandatory: boolean };
export type Skill = { skill: string; required: boolean; evidence: string | null };
export type Job = {
  job_key: string; source: string; company: string; title: string; location?: string; work_mode?: string; url?: string;
  published_at?: string; first_seen_at?: string; description?: string; test_environment?: boolean; environment?: string;
  requirements?: any; salary_min?: number; salary_max?: number; connector?: string;
};
export type MatchCard = {
  job_key: string; score: number; components: Record<string, number>; filters: Filter[]; skills: Skill[]; explanation?: string;
  unknowns: string[]; blocked: boolean; auto_eligible: boolean; extractor: string; rubric_version: string; job: Job; created_at: string;
  experience_evidence?: string[]; responsibilities_evidence?: string[];
};
export type Application = {
  app_id: string; job_key: string; company: string; title: string; location?: string; url?: string; source: string; connector: string;
  target_environment: "test" | "live"; action_state: string; recruitment_stage?: string | null; score: number; auto_eligible: boolean;
  packet_version: number; packet_hash?: string | null; approved_hash?: string | null; created_at: string; updated_at: string;
  receipt?: { reference: string; submitted_at?: string; user_reported?: boolean }; last_error?: string; unknown_required?: string[];
  last_decision?: { allowed: boolean; reasons: string[] }; paused?: boolean;
};
export type TimelineEvent = { type: string; at: string; data: any; app_id?: string; event_id: string };
