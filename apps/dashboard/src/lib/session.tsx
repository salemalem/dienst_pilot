"use client";

import { createApi, unwrap, type Api, type components } from "@dienstpilot/api-client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type Me = components["schemas"]["Me"];
export type Role = Me["role"];

/** The demo personas the dashboard signs in as (UI_SPEC §1). Brandt is the default. */
export const PERSONAS = ["brandt", "vogel", "it-admin"] as const;
export type PersonaKey = (typeof PERSONAS)[number];

const TOKEN_KEY = "dp-token";
const PERSONA_KEY = "dp-persona";

function read(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string | null): void {
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, value);
  } catch {
    // Private mode: the session lasts until reload.
  }
}

interface Session {
  api: Api;
  me: Me;
  persona: PersonaKey;
  /** Changes whenever the identity or the demo clock does; queries depend on it. */
  version: number;
  switchPersona: (persona: PersonaKey) => Promise<void>;
  /** Sign in again (after the Administrator moved the demo clock). */
  refresh: () => Promise<void>;
}

const Ctx = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside SessionProvider");
  return s;
}

/** Signs in as a demo persona (Brandt by default) and exposes the typed API client. */
export function SessionProvider({
  children,
  loading,
  failed,
}: {
  children: ReactNode;
  loading: ReactNode;
  failed: ReactNode;
}): ReactNode {
  const token = useRef<string | null>(null);
  const [state, setState] = useState<{ me: Me; persona: PersonaKey; version: number } | null>(null);
  const [error, setError] = useState(false);
  const relogging = useRef<Promise<void> | null>(null);
  const persona = useRef<PersonaKey>("brandt");

  const login = useCallback(async (api: Api, key: PersonaKey, bump: boolean): Promise<void> => {
    const t = await unwrap(api.POST("/auth/demo-login", { body: { persona: key } }));
    token.current = t.access_token;
    persona.current = key;
    write(TOKEN_KEY, t.access_token);
    write(PERSONA_KEY, key);
    setState((prev) => ({
      me: t.user,
      persona: key,
      version: (prev?.version ?? 0) + (bump ? 1 : 0),
    }));
  }, []);

  const api = useMemo(
    () =>
      createApi({
        baseUrl: "/api",
        getToken: () => token.current,
        onUnauthorized: () => {
          // A demo token is bound to the demo clock: sign in again once, then queries reload.
          relogging.current ??= login(api, persona.current, true).finally(() => {
            relogging.current = null;
          });
        },
      }),
    [login],
  );

  useEffect(() => {
    const stored = read(PERSONA_KEY);
    const key = PERSONAS.find((p) => p === stored) ?? "brandt";
    token.current = read(TOKEN_KEY);
    login(api, key, false).catch(() => {
      setError(true);
    });
  }, [api, login]);

  const value = useMemo<Session | null>(
    () =>
      state && {
        api,
        me: state.me,
        persona: state.persona,
        version: state.version,
        switchPersona: (p) => login(api, p, true),
        refresh: () => login(api, persona.current, true),
      },
    [api, login, state],
  );

  if (error) return failed;
  if (!value) return loading;
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
