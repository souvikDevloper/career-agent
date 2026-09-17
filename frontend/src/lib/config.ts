export type AppConfig = { region: string; userPoolId: string; userPoolClientId: string; version?: string };

let cached: AppConfig | null = null;

export async function loadConfig(): Promise<AppConfig> {
  if (cached) return cached;
  const res = await fetch("/config.json", { cache: "no-store" });
  if (!res.ok) throw new Error("Configuration unavailable");
  cached = (await res.json()) as AppConfig;
  return cached;
}
