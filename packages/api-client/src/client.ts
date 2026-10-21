/** Runtime client over the generated types: `createApi` plus the error the API's 4xx answers become. */
import createClient, { type Client } from "openapi-fetch";

import type { components, paths } from "./schema.ts";

export type Api = Client<paths>;
export type Violation = components["schemas"]["ViolationOut"];

/** An API answer that is not 2xx. A rule violation (422) carries the violations and a message. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly violations: Violation[];

  constructor(status: number, detail: unknown) {
    const d =
      typeof detail === "object" && detail !== null ? (detail as Record<string, unknown>) : {};
    super(
      typeof detail === "string"
        ? detail
        : typeof d.message === "string"
          ? d.message
          : `HTTP ${status}`,
    );
    this.name = "ApiError";
    this.status = status;
    this.code = typeof d.code === "string" ? d.code : null;
    this.violations = Array.isArray(d.violations) ? (d.violations as Violation[]) : [];
  }
}

export interface ApiOptions {
  /** `/api` in the browser (the Next.js proxy), the backend's origin elsewhere. */
  baseUrl: string;
  getToken: () => string | null;
  /** Called on a 401 (a demo token expires when the demo clock moves). */
  onUnauthorized?: () => void;
}

/** Create a typed client that sends the bearer token on every request. */
export function createApi(options: ApiOptions): Api {
  const client = createClient<paths>({ baseUrl: options.baseUrl });
  client.use({
    onRequest({ request }) {
      const token = options.getToken();
      if (token) request.headers.set("authorization", `Bearer ${token}`);
      return request;
    },
    onResponse({ response }) {
      if (response.status === 401) options.onUnauthorized?.();
      return undefined;
    },
  });
  return client;
}

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Return the body of a 2xx answer, or throw an `ApiError`. */
export async function unwrap<T>(result: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await result;
  if (!response.ok) {
    const detail = (error as { detail?: unknown } | undefined)?.detail ?? error;
    throw new ApiError(response.status, detail);
  }
  return data as T;
}
