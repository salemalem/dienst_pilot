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

import { API_URL, PERSONAS, type PersonaKey } from "./config";
import { storage } from "./storage";
import { ThemeProvider, type ThemePref } from "./theme";

export type Me = components["schemas"]["Me"];
export type Settings = components["schemas"]["SettingsOut"];

const TOKEN_KEY = "dp-token";
const PERSONA_KEY = "dp-persona";

interface Session {
  api: Api;
  me: Me | null;
  persona: PersonaKey;
  settings: Settings | null;
  /** Changes whenever the identity or the demo clock does; queries depend on it. */
  version: number;
  ready: boolean;
  signIn: (persona: PersonaKey) => Promise<void>;
  signOut: () => void;
  saveSettings: (patch: Partial<Settings>) => Promise<void>;
}

const Ctx = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside SessionProvider");
  return s;
}

/** Demo sign-in as a persona (Kaya by default); the token lives in the storage helper. */
export function SessionProvider({ children }: { children: ReactNode }): ReactNode {
  const token = useRef<string | null>(storage.get(TOKEN_KEY));
  const persona = useRef<PersonaKey>(
    PERSONAS.find((p) => p === storage.get(PERSONA_KEY)) ?? "kaya",
  );
  const [me, setMe] = useState<Me | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [version, setVersion] = useState(0);
  const [ready, setReady] = useState(false);
  const relogging = useRef<Promise<void> | null>(null);

  const api = useMemo<Api>(
    () =>
      createApi({
        baseUrl: API_URL,
        getToken: () => token.current,
        onUnauthorized: () => {
          // A demo token is bound to the demo clock; after the clock moved, sign in again once.
          relogging.current ??= signInRef.current(persona.current).finally(() => {
            relogging.current = null;
          });
        },
      }),
    [],
  );

  const signIn = useCallback(
    async (key: PersonaKey): Promise<void> => {
      const t = await unwrap(api.POST("/auth/demo-login", { body: { persona: key } }));
      token.current = t.access_token;
      persona.current = key;
      storage.set(TOKEN_KEY, t.access_token);
      storage.set(PERSONA_KEY, key);
      setMe(t.user);
      setSettings(await unwrap(api.GET("/me/settings")));
      setVersion((v) => v + 1);
    },
    [api],
  );
  const signInRef = useRef(signIn);
  signInRef.current = signIn;

  useEffect(() => {
    // Restore a stored session; a stale or missing token leaves the person on the sign-in screen.
    if (token.current === null) {
      setReady(true);
      return;
    }
    unwrap(api.GET("/me"))
      .then(async (m) => {
        setMe(m);
        setSettings(await unwrap(api.GET("/me/settings")));
      })
      .catch(() => {
        token.current = null;
        storage.set(TOKEN_KEY, null);
      })
      .finally(() => {
        setReady(true);
      });
  }, [api]);

  const signOut = useCallback(() => {
    token.current = null;
    storage.set(TOKEN_KEY, null);
    setMe(null);
    setSettings(null);
    setVersion((v) => v + 1);
  }, []);

  const saveSettings = useCallback(
    async (patch: Partial<Settings>): Promise<void> => {
      if (!settings) return;
      const next = { ...settings, ...patch };
      setSettings(next);
      await unwrap(api.PUT("/me/settings", { body: next }));
    },
    [api, settings],
  );

  const value = useMemo<Session>(
    () => ({
      api,
      me,
      persona: persona.current,
      settings,
      version,
      ready,
      signIn,
      signOut,
      saveSettings,
    }),
    [api, me, settings, version, ready, signIn, signOut, saveSettings],
  );
  const pref: ThemePref = settings?.theme ?? "auto";
  return (
    <Ctx.Provider value={value}>
      <ThemeProvider
        initialPref={pref}
        onPref={(p) => {
          void saveSettings({ theme: p });
        }}
      >
        {children}
      </ThemeProvider>
    </Ctx.Provider>
  );
}
