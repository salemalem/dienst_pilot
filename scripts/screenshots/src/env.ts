/** Ports and switches shared by the capture and the comparison run. */
export const API_PORT = 8100;
export const DASH_PORT = 3100;
export const APP_PORT = 8083;
export const REF_PORT = 8765;

export const API_URL = `http://localhost:${String(API_PORT)}`;
export const DASH_URL = `http://localhost:${String(DASH_PORT)}`;
export const APP_URL = `http://localhost:${String(APP_PORT)}`;
export const REF_URL = `http://localhost:${String(REF_PORT)}`;

/** One language per run; `make screenshots` runs German, then English, each on a fresh seed. */
export const LANG: "de" | "en" = process.env.E2E_LANG === "en" ? "en" : "de";
/** `capture` writes screenshots/; `compare` writes review/ (reference left, app right). */
export const MODE: "capture" | "compare" = process.env.MODE === "compare" ? "compare" : "capture";
