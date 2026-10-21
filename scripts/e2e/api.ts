/** Scripted API calls play the other personas (staff, admin); the checks run in the UI. */
export function makeApi(apiUrl: string): {
  login: (persona: string) => Promise<string>;
  api: <T = unknown>(token: string, method: string, path: string, body?: unknown) => Promise<T>;
} {
  const login = async (persona: string): Promise<string> => {
    const r = await fetch(`${apiUrl}/auth/demo-login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ persona }),
    });
    if (!r.ok) throw new Error(`login ${persona}: ${String(r.status)}`);
    return ((await r.json()) as { access_token: string }).access_token;
  };
  const api = async <T = unknown>(
    token: string,
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> => {
    const r = await fetch(`${apiUrl}${path}`, {
      method,
      headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!r.ok) throw new Error(`${method} ${path}: ${String(r.status)} ${await r.text()}`);
    return (await r.json()) as T;
  };
  return { login, api };
}
