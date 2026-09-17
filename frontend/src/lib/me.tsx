import { createContext, useContext, type ReactNode } from "react";
import { useApi } from "./hooks";

export type Connector = { label: string; environment: string; status: string; capabilities: string[]; note: string };
export type Me = {
  user_id: string;
  is_judge: boolean;
  example_workspace: boolean;
  email?: string | null;
  settings: {
    mode: "review" | "auto_above_80" | "auto_eligible";
    daily_cap: number;
    cooldown_seconds: number;
    timezone: string;
    notify_email?: string | null;
    notify_email_verified?: boolean;
    voice_enabled: boolean;
    preferences: { roles: string[]; locations: string[]; work_modes: string[]; excluded_companies: string[]; min_salary?: number | null };
    mandate?: { enabled: boolean; mode: string; expires_at: number; policy_version: string; created_at: string } | null;
    telegram_linked: boolean;
  };
  profile: null | { version: number; facts: any; created_at: string; source: string; saved_answers: Record<string, string>; has_resume: boolean };
  connectors: Record<string, Connector>;
  usage: { model_calls?: number; voice_seconds?: number; speech_chars?: number };
  limits: { model_calls: number; voice_seconds: number };
  inbox: { kind: string; subject: string; text: string; app_id?: string; read: boolean; at: string }[];
  sources: { source: string; last_success_at?: string; last_error?: string; job_count?: number; interval_minutes: number; environment: string }[];
  watches: { watch_id: string; keywords: string; interval_minutes: number; created_at: string }[];
};

const Ctx = createContext<{ me: Me | null; reload: () => Promise<void>; error: string | null }>({ me: null, reload: async () => {}, error: null });

export function MeProvider({ children }: { children: ReactNode }) {
  const { data, reload, error } = useApi<Me>("/api/me", [], 8000);
  return <Ctx.Provider value={{ me: data, reload, error }}>{children}</Ctx.Provider>;
}

export const useMe = () => useContext(Ctx);
