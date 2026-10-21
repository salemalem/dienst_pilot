import type { Api } from "@dienstpilot/api-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { useSession } from "./session";

export interface Query<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
}

/** Fetch with the signed-in client; reloads when the session or `deps` change. */
export function useQuery<T>(fetcher: (api: Api) => Promise<T>, deps: readonly unknown[]): Query<T> {
  const { api, version, me } = useSession();
  const [state, setState] = useState<{ data: T | null; error: Error | null; loading: boolean }>({
    data: null,
    error: null,
    loading: true,
  });
  const [tick, setTick] = useState(0);
  const ref = useRef(fetcher);
  ref.current = fetcher;

  useEffect(() => {
    if (me === null) return;
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    ref.current(api).then(
      (data) => {
        if (!cancelled) setState({ data, error: null, loading: false });
      },
      (error: unknown) => {
        if (!cancelled)
          setState({
            data: null,
            error: error instanceof Error ? error : new Error(String(error)),
            loading: false,
          });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, version, me, tick, ...deps]);

  const reload = useCallback(() => {
    setTick((n) => n + 1);
  }, []);
  return { ...state, reload };
}

/** Run an action once at a time, keeping its pending state and last error. */
export function useAction<A extends unknown[], R>(
  action: (...args: A) => Promise<R>,
): { run: (...args: A) => Promise<R | undefined>; pending: boolean; error: Error | null } {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const ref = useRef(action);
  ref.current = action;
  const run = useCallback(async (...args: A): Promise<R | undefined> => {
    setPending(true);
    setError(null);
    try {
      return await ref.current(...args);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
      return undefined;
    } finally {
      setPending(false);
    }
  }, []);
  return { run, pending, error };
}
