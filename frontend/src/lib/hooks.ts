import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

export function useApi<T>(path: string | null, deps: unknown[] = [], pollMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const alive = useRef(true);

  const load = useCallback(async () => {
    if (!path) return;
    try {
      const d = await api<T>(path);
      if (alive.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    } finally {
      if (alive.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);

  useEffect(() => {
    alive.current = true;
    setLoading(!!path);
    load();
    let timer: number | undefined;
    if (pollMs) {
      const tick = () => {
        timer = window.setTimeout(async () => {
          if (!document.hidden) await load();
          tick();
        }, pollMs);
      };
      tick();
    }
    return () => {
      alive.current = false;
      clearTimeout(timer);
    };
  }, [load, pollMs]);

  return { data, error, loading, reload: load, setData };
}
